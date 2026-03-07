"""
Google Sheets integration — reads Maya AI leads from a configured spreadsheet.

Expected sheet columns (exact, case-sensitive):
    name, phone, model, intent, mileage,
    appointment_time, created_at, status, source, sms_sent, calendar_booked

Authentication uses a Service Account JSON key file. Steps:
  1. Enable Google Sheets API + Google Drive API in Google Cloud Console.
  2. Create a Service Account and download its JSON key.
  3. Share the target sheet with the service account's client_email.
  4. Set GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID in .env.
"""

import logging
import time
import traceback
from datetime import datetime
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from app.config.settings import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# ---------------------------------------------------------------------------
# Simple in-process cache
# ---------------------------------------------------------------------------
_cache: dict[str, Any] = {"data": None, "ts": 0.0}


def _is_truthy(value: Any) -> bool:
    """Return True for any value that represents a checked/yes state."""
    return str(value).strip().lower() in ("true", "yes", "כן", "1", "v", "✓", "x")


def _parse_date(raw: Any) -> str | None:
    """
    Try to parse a datetime string from Google Sheets into ISO format.
    Google Sheets commonly exports dates as DD/MM/YYYY HH:MM or YYYY-MM-DD.
    Returns None if the value is empty; returns raw string if unparseable.
    """
    s = str(raw).strip()
    if not s or s.lower() in ("none", "n/a", "-", ""):
        return None

    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue

    # Already ISO-ish (e.g. "2026-03-06T08:14:00Z")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass

    # Return as-is to avoid silently dropping data
    logger.warning("Could not parse date value: %r", s)
    return s


def _get(row: dict, col: str, default: str = "") -> str:
    """Safely read a column from a sheet row, returning default if missing/empty."""
    val = row.get(col)
    if val is None or str(val).strip() in ("", "None"):
        return default
    return str(val).strip()


def _parse_intents(row: dict) -> list[str]:
    """
    Read the `intents` column (pipe-separated), falling back to `intent`.
    Returns a list of trimmed, non-empty strings.
    e.g. "טיפול / מוסך | נסיעת מבחן" → ["טיפול / מוסך", "נסיעת מבחן"]
    """
    raw = _get(row, "intents") or _get(row, "intent")
    if not raw:
        return []
    return [v.strip() for v in raw.split("|") if v.strip()]


def _normalize_row(row: dict, index: int) -> dict:
    """Map an exact-column sheet row to the canonical Lead schema."""
    created_raw = _get(row, "created_at")
    appt_raw = _get(row, "appointment_time")

    return {
        "id": str(index + 1),
        # Required fields — fall back to a placeholder so the row is never dropped
        "name": _get(row, "name", f"לקוח {index + 1}"),
        "phone": _get(row, "phone"),
        "model": _get(row, "model"),
        "intents": _parse_intents(row),
        # Optional fields — explicit defaults when blank
        "mileage": _get(row, "mileage"),
        "appointment_time": _parse_date(appt_raw) if appt_raw else None,
        "created_at": _parse_date(created_raw) or datetime.utcnow().isoformat(),
        "status": _get(row, "status", "new"),
        "source": _get(row, "source", "maya"),
        "sms_sent": _is_truthy(_get(row, "sms_sent")),
        "calendar_booked": _is_truthy(_get(row, "calendar_booked")),
    }


def _fetch_from_sheets() -> list[dict]:
    """Open the configured spreadsheet and return normalized rows."""
    print(f"SHEETS: spreadsheet_id={settings.GOOGLE_SHEET_ID!r}", flush=True)
    print(f"SHEETS: worksheet_name={settings.GOOGLE_SHEET_NAME!r}", flush=True)
    print(f"SHEETS: service_account_json={settings.GOOGLE_SERVICE_ACCOUNT_JSON!r}", flush=True)
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(settings.GOOGLE_SHEET_ID)

    try:
        worksheet = spreadsheet.worksheet(settings.GOOGLE_SHEET_NAME)
        logger.info("Opened worksheet: %r", worksheet.title)
    except gspread.WorksheetNotFound:
        logger.warning(
            "Worksheet %r not found — falling back to first sheet", settings.GOOGLE_SHEET_NAME
        )
        worksheet = spreadsheet.sheet1

    # numericise_ignore=['all'] prevents gspread from converting values to int/float,
    # which can cause get_all_records() to raise on columns like sms_sent/calendar_booked.
    # expected_headers skips strict header validation so stray blank columns don't raise.
    try:
        records = worksheet.get_all_records(numericise_ignore=["all"], expected_headers=[])
    except TypeError:
        # older gspread versions don't support expected_headers — fall back
        records = worksheet.get_all_records(numericise_ignore=["all"])

    print(f"SHEETS: raw rows fetched = {len(records)}", flush=True)
    logger.info(
        "Fetched %d raw rows from sheet %r (spreadsheet: %s)",
        len(records), worksheet.title, settings.GOOGLE_SHEET_ID,
    )

    # Skip entirely empty rows (all values are blank/None)
    non_empty = [
        (i, row) for i, row in enumerate(records)
        if any(str(v).strip() for v in row.values())
    ]
    print(f"SHEETS: non-empty rows = {len(non_empty)}", flush=True)
    logger.info("%d non-empty rows after filtering", len(non_empty))

    result = [_normalize_row(row, i) for i, row in non_empty]
    print(f"SHEETS: parsed leads = {len(result)}", flush=True)
    return result


def get_leads() -> list[dict]:
    """
    Return leads from Google Sheets with in-process caching.
    Falls back to stale cache or empty list on error.
    """
    ttl = settings.GOOGLE_SHEETS_CACHE_TTL
    now = time.monotonic()

    if ttl > 0 and _cache["data"] is not None and (now - _cache["ts"]) < ttl:
        logger.debug("Returning %d cached leads", len(_cache["data"]))
        return _cache["data"]

    try:
        data = _fetch_from_sheets()
        _cache["data"] = data
        _cache["ts"] = now
        return data
    except FileNotFoundError:
        logger.error(
            "Service account JSON not found at '%s'. "
            "Set GOOGLE_SERVICE_ACCOUNT_JSON in .env.",
            settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        )
    except Exception as exc:
        print(f"SHEETS ERROR: {exc}", flush=True)
        print(traceback.format_exc(), flush=True)
        logger.error(
            "Failed to fetch leads from Google Sheets: %s\n%s",
            exc, traceback.format_exc(),
        )

    cached = _cache["data"]
    if cached is not None:
        logger.warning("Returning stale cache (%d leads)", len(cached))
        return cached
    return []

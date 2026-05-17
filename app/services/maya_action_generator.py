"""
app/services/maya_action_generator.py
=====================================
Phase 3.8B + 3.8F — Maya action suggestion generator.

Two public entry points:

  - generate_dry_run(briefing_id)         → READ-ONLY evaluation. Writes nothing.
                                            Returns a `would_create[]` preview plus
                                            a per-reason `skipped` breakdown.

  - create_one_from_briefing(briefing_id) → admin-only single-row INSERT path.
                                            Reuses generate_dry_run for evaluation,
                                            then calls the SQL validator and inserts
                                            at most ONE row into
                                            public.maya_action_suggestions.

Strict invariants
-----------------
1. generate_dry_run uses ONLY GET against PostgREST. Never insert/update/delete.
2. create_one_from_briefing is the ONLY write path in this module. It performs
   at most one INSERT into public.maya_action_suggestions and zero writes elsewhere.
3. No Twilio. No WhatsApp send. No RPC calls into approve/skip/edit/set_permission.
4. No execution. Created rows are pending proposals (status='suggested').
5. The mirrored Python validator (`_validate_message_he`) must stay byte-for-byte
   aligned with the SQL function `public.maya_validate_action_message_he`. The
   create path additionally invokes the SQL validator before insert as the
   canonical safety check; the Python mirror remains the hot path for dry-run.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)

# ── Supabase ──────────────────────────────────────────────────────────────────
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _is_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


def _headers() -> dict:
    return {
        "apikey":        _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
    }


# ── Constants (locked by Phase 3.8 design) ────────────────────────────────────
ACTION_TYPE = "send_followup_message"
MAX_SUGGESTIONS_PER_RUN = 1
SESSION_WINDOW = timedelta(hours=24)

# Message templates (Phase 3.8 locked copy)
_TEMPLATE_WITH_NAME = (
    "היי {first_name}, רק רציתי לוודא שלא פספסנו אותך. "
    "אם זה עדיין רלוונטי, אשמח לבדוק לך זמינות לשיעור ניסיון."
)
_TEMPLATE_WITHOUT_NAME = (
    "היי, רק רציתי לוודא שלא פספסנו אותך. "
    "אם זה עדיין רלוונטי, אשמח לבדוק לך זמינות לשיעור ניסיון."
)
_TEMPLATE_VERSION = "v1"

# Statuses that block a new suggestion for the same (lead_id, action_type).
_OPEN_STATUSES = ("suggested", "pending_approval", "approved", "edited")

# Hebrew letters + Latin letters only. Used to validate first_name extraction.
_FIRST_NAME_RE = re.compile(r"^[A-Za-z֐-׿]+$")

# Mirror of public.maya_validate_action_message_he. Keep in sync.
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")
_CURRENCY_RE    = re.compile(r"(₪|\bשח\b|\bשקל\b|\bשקלים\b)")
_CONTROL_RE     = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


# ── Errors ────────────────────────────────────────────────────────────────────
class BriefingNotFound(Exception):
    pass


class GeneratorAbort(Exception):
    """Whole-run abort with a structured reason (e.g., permission_disabled)."""
    def __init__(self, reason: str, error_he: str):
        super().__init__(reason)
        self.reason = reason
        self.error_he = error_he


# ── Public entry point ────────────────────────────────────────────────────────
async def generate_dry_run(briefing_id: str) -> dict:
    """
    Run the dry-run generator for one briefing.

    Returns the response shape documented in Phase 3.8B. No DB writes occur.
    Raises:
      - BriefingNotFound  → caller maps to 404
      - GeneratorAbort    → caller maps to 200-OK with abort summary
      - RuntimeError      → caller maps to 500
    """
    if not _is_configured():
        raise RuntimeError("supabase_not_configured")

    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)

    skipped: dict[str, int] = {
        "non_mvp_type":              0,
        "no_target_lead":            0,
        "phone_missing":             0,
        "session_status_unknown":    0,
        "outside_24h_window":        0,
        "duplicate_open_suggestion": 0,
        "permission_disabled":       0,
        "permission_drift":          0,
        "validation_failed":         0,
        "cap_reached":               0,
        "other":                     0,
    }
    would_create: list[dict] = []

    async with httpx.AsyncClient(timeout=10.0, headers=_headers()) as http:
        briefing = await _load_briefing(http, briefing_id)
        if briefing is None:
            raise BriefingNotFound(briefing_id)

        client_id = briefing["client_id"]
        agent_id  = briefing.get("agent_id")

        # 1) Permission snapshot
        perm_row = await _load_permission(http, client_id, ACTION_TYPE)
        perm_mode_at_creation = _resolve_permission_mode(perm_row, skipped)
        # _resolve_permission_mode raises GeneratorAbort on disabled / drift.

        # 2) Findings
        findings = await _load_findings(http, briefing_id)
        findings_total = len(findings)

        # 3) Iterate
        for finding in findings:
            if len(would_create) >= MAX_SUGGESTIONS_PER_RUN:
                # Only count cap_reached for findings that would otherwise have
                # been candidates; non-MVP types are counted under their own reason.
                if finding.get("finding_type") == "followup_gap":
                    skipped["cap_reached"] += 1
                else:
                    skipped["non_mvp_type"] += 1
                continue

            ftype = finding.get("finding_type")
            if ftype != "followup_gap":
                skipped["non_mvp_type"] += 1
                continue

            evidence = finding.get("evidence") or {}
            if (
                evidence.get("layer") != "L1"
                or evidence.get("table") != "leads"
                or not isinstance(evidence.get("ids"), list)
                or len(evidence["ids"]) == 0
            ):
                skipped["no_target_lead"] += 1
                continue

            # Load only leads belonging to the briefing's client.
            leads = await _load_leads(http, client_id, evidence["ids"])
            with_phone = [l for l in leads if (l.get("phone") or "").strip()]
            if not with_phone:
                skipped["phone_missing"] += 1
                continue

            picked, picked_reason = _pick_lead_for_followup(with_phone)
            if picked is None:
                # picked_reason is either session_status_unknown or outside_24h_window
                skipped[picked_reason] += 1
                continue

            # Dedup against existing open suggestions for this lead+action_type
            if await _has_open_suggestion(http, picked["id"]):
                skipped["duplicate_open_suggestion"] += 1
                continue

            # Build message
            first_name = _extract_first_name(picked.get("name"))
            if first_name:
                message_he = _TEMPLATE_WITH_NAME.format(first_name=first_name)
            else:
                message_he = _TEMPLATE_WITHOUT_NAME

            v = _validate_message_he(message_he)
            if not v["ok"]:
                logger.warning(
                    "maya_action_generator.validation_failed run_id=%s finding_id=%s code=%s",
                    run_id, finding["id"], v["error_code"],
                )
                skipped["validation_failed"] += 1
                continue

            now = datetime.now(timezone.utc)
            inbound = _parse_iso(picked["last_whatsapp_inbound_at"])
            # We already filtered for non-null + in-24h. Guard against drift.
            if inbound is None:
                skipped["session_status_unknown"] += 1
                continue
            expires_at = min(now + SESSION_WINDOW, inbound + SESSION_WINDOW)

            rationale_he = (
                "ליד שהתעניין ולא חזר לשיחה — מאיה הכינה הודעת בדיקה עדינה "
                "תוך 24 שעות מההודעה האחרונה."
            )

            payload_preview = {
                "message_he":   message_he,
                "first_name":   first_name or "",
                "language":     "he",
                "channel":      "whatsapp",
                "source": {
                    "briefing_id":  briefing_id,
                    "finding_id":   finding["id"],
                    "finding_type": "followup_gap",
                    "generated_at": now.isoformat(),
                },
                "context": {
                    "last_inbound_at": inbound.isoformat(),
                    "session_status":  "in_24h",
                },
                "safety": {
                    "no_price":         True,
                    "no_medical":       True,
                    "no_pressure":      True,
                    "template_version": _TEMPLATE_VERSION,
                },
            }

            would_create.append({
                "action_type":                 ACTION_TYPE,
                "lead_id":                     picked["id"],
                "lead_name_present":           bool(first_name),
                "message_he":                  message_he,
                "permission_mode_at_creation": perm_mode_at_creation,
                "expires_at":                  expires_at.isoformat(),
                "risk_level":                  "low",
                "source": {
                    "briefing_id":  briefing_id,
                    "finding_id":   finding["id"],
                    "finding_type": "followup_gap",
                },
                "rationale_he":                rationale_he,
                "payload":                     payload_preview,
            })

    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    # Single structured run summary — PII redacted (no phone, no message body)
    logger.info(
        "maya_action_generator.run run_id=%s briefing_id=%s client_id=%s "
        "findings_total=%d would_create_count=%d skipped=%s duration_ms=%d",
        run_id, briefing_id, client_id, findings_total, len(would_create),
        skipped, duration_ms,
    )

    return {
        "ok":                 True,
        "run_id":              run_id,
        "dry_run":             True,
        "briefing_id":         briefing_id,
        "client_id":           client_id,
        "agent_id":            agent_id,
        "findings_total":      findings_total,
        "would_create_count":  len(would_create),
        "would_create":        would_create,
        "skipped":             skipped,
        "duration_ms":         duration_ms,
    }


# ── Internal: PostgREST queries (READ-ONLY) ───────────────────────────────────
async def _load_briefing(http: httpx.AsyncClient, briefing_id: str) -> dict | None:
    url = f"{_SUPABASE_URL}/rest/v1/analyst_briefings"
    params = {
        "id":     f"eq.{briefing_id}",
        "select": "id,client_id,agent_id,period_start,period_end,status,"
                  "visibility,data_volume,volume_warning",
        "limit":  1,
    }
    r = await http.get(url, params=params)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


async def _load_findings(http: httpx.AsyncClient, briefing_id: str) -> list[dict]:
    url = f"{_SUPABASE_URL}/rest/v1/analyst_briefing_findings"
    params = {
        "briefing_id": f"eq.{briefing_id}",
        "select":      "id,finding_type,evidence,confidence,sample_size",
        "order":       "created_at.asc",
    }
    r = await http.get(url, params=params)
    r.raise_for_status()
    return r.json()


async def _load_permission(http: httpx.AsyncClient, client_id: str, action_type: str) -> dict | None:
    url = f"{_SUPABASE_URL}/rest/v1/maya_action_permissions"
    params = {
        "client_id":   f"eq.{client_id}",
        "action_type": f"eq.{action_type}",
        "select":      "id,mode,scope",
        "limit":       1,
    }
    r = await http.get(url, params=params)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


async def _load_leads(http: httpx.AsyncClient, client_id: str, ids: Iterable[str]) -> list[dict]:
    ids_filter = ",".join(str(i) for i in ids if isinstance(i, str))
    if not ids_filter:
        return []
    url = f"{_SUPABASE_URL}/rest/v1/leads"
    params = {
        "id":        f"in.({ids_filter})",
        "client_id": f"eq.{client_id}",
        "select":    "id,client_id,name,phone,last_whatsapp_inbound_at",
    }
    r = await http.get(url, params=params)
    r.raise_for_status()
    return r.json()


async def _has_open_suggestion(http: httpx.AsyncClient, lead_id: str) -> bool:
    now_iso = datetime.now(timezone.utc).isoformat()
    url = f"{_SUPABASE_URL}/rest/v1/maya_action_suggestions"
    params = {
        "lead_id":     f"eq.{lead_id}",
        "action_type": f"eq.{ACTION_TYPE}",
        "status":      f"in.({','.join(_OPEN_STATUSES)})",
        "expires_at":  f"gt.{now_iso}",
        "select":      "id",
        "limit":       1,
    }
    r = await http.get(url, params=params)
    r.raise_for_status()
    return bool(r.json())


# ── Internal: pure logic ──────────────────────────────────────────────────────
def _resolve_permission_mode(perm_row: dict | None, skipped: dict[str, int]) -> str:
    """
    Returns the permission_mode_at_creation to snapshot. Raises GeneratorAbort
    for `disabled` or `auto_execute_allowed` (treated as drift in MVP).
    """
    if perm_row is None:
        return "require_approval"
    mode = perm_row.get("mode")
    if mode in ("suggest_only", "require_approval"):
        return mode
    if mode == "disabled":
        skipped["permission_disabled"] += 1
        raise GeneratorAbort("permission_disabled", "סוג הפעולה הושבת על ידי הלקוח")
    if mode == "auto_execute_allowed":
        skipped["permission_drift"] += 1
        raise GeneratorAbort(
            "permission_drift",
            "מצב הרשאה לא תקין ל-MVP — auto_execute_allowed אינו נתמך",
        )
    # Unknown mode → treat as drift, safer than silently mapping.
    skipped["permission_drift"] += 1
    raise GeneratorAbort("permission_drift", "מצב הרשאה לא מוכר")


def _pick_lead_for_followup(leads: list[dict]) -> tuple[dict | None, str]:
    """
    Choose the single eligible lead. Returns (lead, '') on success,
    or (None, reason_code) when no lead is eligible.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - SESSION_WINDOW

    parsed: list[tuple[dict, datetime | None]] = []
    for l in leads:
        ts = _parse_iso(l.get("last_whatsapp_inbound_at"))
        parsed.append((l, ts))

    in_window = [(l, ts) for l, ts in parsed if ts is not None and ts > cutoff]
    if in_window:
        in_window.sort(key=lambda t: (-t[1].timestamp(), t[0]["id"]))
        return in_window[0][0], ""

    any_timestamp = any(ts is not None for _, ts in parsed)
    if any_timestamp:
        return None, "outside_24h_window"
    return None, "session_status_unknown"


def _extract_first_name(raw: str | None) -> str | None:
    if not raw:
        return None
    first = raw.strip().split()[0] if raw.strip() else ""
    if not first:
        return None
    if len(first) > 30:
        return None
    if not _FIRST_NAME_RE.match(first):
        return None
    return first


def _validate_message_he(message_he: str) -> dict:
    """Python mirror of public.maya_validate_action_message_he.
    Keep in sync byte-for-byte. See module docstring."""
    if message_he is None:
        return {"ok": False, "error_code": "invalid_payload", "error_he": "חסר טקסט הודעה"}
    trimmed = message_he.strip()
    n = len(trimmed)
    if n < 1 or n > 2000:
        return {"ok": False, "error_code": "invalid_payload",
                "error_he": "אורך ההודעה צריך להיות בין תו אחד ל-2000 תווים"}
    if _PLACEHOLDER_RE.search(message_he):
        return {"ok": False, "error_code": "invalid_payload",
                "error_he": "יש להחליף את כל המילים בסוגריים מרובעים לפני שליחה"}
    if _CURRENCY_RE.search(message_he):
        return {"ok": False, "error_code": "invalid_payload",
                "error_he": "אסור להזכיר מחיר בנוסח עד שאישור מחיר ייפתח בנפרד"}
    if _CONTROL_RE.search(message_he):
        return {"ok": False, "error_code": "invalid_payload",
                "error_he": "ההודעה מכילה תווים לא חוקיים"}
    return {"ok": True, "error_code": "ok", "error_he": None}


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    s = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ═════════════════════════════════════════════════════════════════════════════
# Phase 3.8F — single-row INSERT path. ONLY write path in this module.
# Reuses generate_dry_run as the shared evaluator (single source of truth).
# ═════════════════════════════════════════════════════════════════════════════

# Pre-insert guard: refuse to insert a suggestion whose expires_at is within
# this many seconds of now. Prevents the row from being marked 'expired' on
# the very next read.
_MIN_EXPIRY_HEADROOM = timedelta(minutes=1)


async def create_one_from_briefing(briefing_id: str) -> dict:
    """
    Phase 3.8F admin-only single-row INSERT path.

    Evaluates the briefing the exact same way generate_dry_run does, then
    inserts at most ONE row into public.maya_action_suggestions if (and only
    if) the SQL validator approves the message and no duplicate exists.

    Never sends WhatsApp. Never calls Twilio. Never executes the suggestion.
    Returns a structured dict; never raises GeneratorAbort upward (caught here
    and surfaced as `created: false, reason: …`).
    """
    if not _is_configured():
        raise RuntimeError("supabase_not_configured")

    started = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    # 1) Shared evaluation. Same code path the dry-run endpoint uses.
    try:
        eval_resp = await generate_dry_run(briefing_id)
    except GeneratorAbort as ab:
        # permission_disabled / permission_drift surface as no-insert reasons.
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        _log_create(run_id, briefing_id, None, None, None, None, None,
                    False, None, ab.reason, duration_ms)
        return {
            "ok": True,
            "run_id": run_id,
            "dry_run": False,
            "created": False,
            "reason": ab.reason,
            "error_he": ab.error_he,
            "briefing_id": briefing_id,
            "duration_ms": duration_ms,
        }

    candidates = eval_resp.get("would_create") or []
    skipped    = eval_resp.get("skipped") or {}
    client_id  = eval_resp.get("client_id")
    agent_id   = eval_resp.get("agent_id")

    # 2) Candidate count semantics
    if len(candidates) == 0:
        reason = _infer_no_insert_reason(skipped)
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        _log_create(run_id, briefing_id, client_id, agent_id, None, None, None,
                    False, None, reason, duration_ms)
        return {
            "ok": True,
            "run_id": run_id,
            "dry_run": False,
            "created": False,
            "reason": reason,
            "skipped": skipped,
            "briefing_id": briefing_id,
            "client_id": client_id,
            "duration_ms": duration_ms,
        }

    if len(candidates) > 1:
        # Hard invariant: generator's MAX_SUGGESTIONS_PER_RUN is 1. If this
        # ever produces more, it's a regression — fail closed, no insert.
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        logger.error(
            "maya_action_generator.invariant_violation run_id=%s briefing_id=%s candidates=%d",
            run_id, briefing_id, len(candidates),
        )
        return {
            "ok": False,
            "run_id": run_id,
            "dry_run": False,
            "created": False,
            "error": "invariant_error",
            "expected_len": 1,
            "got": len(candidates),
            "duration_ms": duration_ms,
        }

    cand = candidates[0]
    finding_id    = (cand.get("source") or {}).get("finding_id")
    lead_id       = cand.get("lead_id")
    message_he    = cand.get("message_he") or ""
    payload       = cand.get("payload") or {}
    rationale_he  = cand.get("rationale_he") or ""
    risk_level    = cand.get("risk_level") or "low"
    perm_mode     = cand.get("permission_mode_at_creation") or "require_approval"
    expires_at    = _parse_iso(cand.get("expires_at"))

    if expires_at is None:
        return _no_insert(run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
                          "expired_before_insert", started)

    # 3) Expiry headroom guard
    now = datetime.now(timezone.utc)
    if expires_at <= now + _MIN_EXPIRY_HEADROOM:
        return _no_insert(run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
                          "expired_before_insert", started)

    async with httpx.AsyncClient(timeout=10.0, headers=_headers()) as http:
        # 4) Finding-level dedup pre-check (lead-level was checked inside the
        # evaluator). Clean error before relying on the DB unique constraint.
        existing_finding_row = await _existing_finding_action(http, finding_id)
        if existing_finding_row is not None:
            return _no_insert(run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
                              "duplicate_finding_action", started,
                              existing_suggestion_id=existing_finding_row.get("id"))

        # 5) SQL validator (canonical safety check before insert).
        sql_v = await _sql_validate_message_he(http, message_he)
        if (sql_v or {}).get("ok") is not True:
            return _no_insert(run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
                              "validation_failed", started,
                              error_he=(sql_v or {}).get("error_he"))

        # 6) INSERT. Service-role bypasses RLS; no client-side INSERT policy exists.
        row = {
            "client_id":                   client_id,
            "agent_id":                    agent_id,
            "lead_id":                     lead_id,
            "briefing_id":                 briefing_id,
            "finding_id":                  finding_id,
            "action_type":                 ACTION_TYPE,
            "status":                      "suggested",
            "permission_mode_at_creation": perm_mode,
            "risk_level":                  risk_level,
            "payload":                     payload,
            "rationale_he":                rationale_he,
            "expires_at":                  expires_at.isoformat(),
        }
        inserted, race_err = await _insert_suggestion(http, row)
        if race_err is not None:
            return _no_insert(run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
                              "duplicate_finding_action_race", started)
        if inserted is None:
            return _no_insert(run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
                              "insert_failed", started)

    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    _log_create(run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
                perm_mode, True, inserted.get("id"), None, duration_ms,
                expires_at=expires_at.isoformat())

    return {
        "ok": True,
        "run_id": run_id,
        "dry_run": False,
        "created": True,
        "suggestion_id": inserted.get("id"),
        "briefing_id": briefing_id,
        "client_id": client_id,
        "lead_id": lead_id,
        "action_type": ACTION_TYPE,
        "status": inserted.get("status") or "suggested",
        "permission_mode_at_creation": perm_mode,
        "risk_level": risk_level,
        "expires_at": expires_at.isoformat(),
        "version": inserted.get("version") or 1,
        "message_preview": message_he,
        "duration_ms": duration_ms,
    }


def _no_insert(run_id: str, briefing_id: str, client_id: Any, agent_id: Any,
               finding_id: Any, lead_id: Any, reason: str, started: datetime,
               *, existing_suggestion_id: str | None = None,
               error_he: str | None = None) -> dict:
    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    _log_create(run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
                None, False, None, reason, duration_ms)
    out: dict = {
        "ok": True,
        "run_id": run_id,
        "dry_run": False,
        "created": False,
        "reason": reason,
        "briefing_id": briefing_id,
        "client_id": client_id,
        "lead_id": lead_id,
        "duration_ms": duration_ms,
    }
    if existing_suggestion_id:
        out["existing_suggestion_id"] = existing_suggestion_id
    if error_he:
        out["error_he"] = error_he
    return out


def _infer_no_insert_reason(skipped: dict[str, int]) -> str:
    """Pick the most informative skip reason when the evaluator produced zero
    candidates. Falls back to a generic code if nothing matched."""
    priority = [
        "duplicate_open_suggestion",
        "validation_failed",
        "outside_24h_window",
        "session_status_unknown",
        "phone_missing",
        "no_target_lead",
        "non_mvp_type",
        "cap_reached",
        "other",
    ]
    for key in priority:
        if skipped.get(key, 0) > 0:
            return key
    return "no_eligible_suggestion"


def _log_create(run_id: str, briefing_id: str, client_id: Any, agent_id: Any,
                finding_id: Any, lead_id: Any, perm_mode: Any,
                created: bool, created_suggestion_id: Any,
                reason: Any, duration_ms: int,
                *, expires_at: str | None = None) -> None:
    # Single structured event. PII-safe: no phone, no full payload, no message body.
    logger.info(
        "maya_action_generator.create run_id=%s briefing_id=%s client_id=%s "
        "agent_id=%s finding_id=%s lead_id=%s created=%s suggestion_id=%s "
        "perm_mode=%s reason=%s expires_at=%s template_version=%s duration_ms=%d",
        run_id, briefing_id, client_id, agent_id, finding_id, lead_id,
        created, created_suggestion_id, perm_mode, reason, expires_at,
        _TEMPLATE_VERSION, duration_ms,
    )


# ── Internal: PostgREST endpoints used only by the create path ───────────────
async def _existing_finding_action(http: httpx.AsyncClient, finding_id: str) -> dict | None:
    url = f"{_SUPABASE_URL}/rest/v1/maya_action_suggestions"
    params = {
        "finding_id":  f"eq.{finding_id}",
        "action_type": f"eq.{ACTION_TYPE}",
        "select":      "id,status",
        "limit":       1,
    }
    r = await http.get(url, params=params)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


async def _sql_validate_message_he(http: httpx.AsyncClient, message_he: str) -> dict:
    """Call public.maya_validate_action_message_he via PostgREST RPC.
    Service-role is granted EXECUTE on this function (3.7B grants check)."""
    url = f"{_SUPABASE_URL}/rest/v1/rpc/maya_validate_action_message_he"
    r = await http.post(url, json={"p_message_he": message_he})
    if r.status_code != 200:
        logger.warning(
            "maya_action_generator.sql_validator_unexpected_status status=%d body=%s",
            r.status_code, (r.text or "")[:200],
        )
        return {"ok": False, "error_code": "validator_unreachable",
                "error_he": "כשל בבדיקת ההודעה"}
    return r.json() if isinstance(r.json(), dict) else {
        "ok": False, "error_code": "validator_unreachable",
        "error_he": "כשל בבדיקת ההודעה",
    }


async def _insert_suggestion(http: httpx.AsyncClient, row: dict
                             ) -> tuple[dict | None, str | None]:
    """
    INSERT one row into public.maya_action_suggestions.

    Returns (inserted_row, None) on success.
    Returns (None, "unique_violation") on SQLSTATE 23505 (partial unique on
      finding_id+action_type). All other non-2xx return (None, "http_<code>").
    """
    url = f"{_SUPABASE_URL}/rest/v1/maya_action_suggestions"
    headers = dict(_headers())
    headers["Prefer"] = "return=representation"
    r = await http.post(url, json=row, headers=headers)
    if r.status_code in (200, 201):
        body = r.json()
        if isinstance(body, list) and body:
            return body[0], None
        if isinstance(body, dict):
            return body, None
        return None, "empty_representation"
    # PostgREST surfaces unique-violation as 409 with JSON body containing "code":"23505"
    try:
        err = r.json()
    except Exception:
        err = {}
    if r.status_code == 409 or (isinstance(err, dict) and err.get("code") == "23505"):
        return None, "unique_violation"
    logger.error(
        "maya_action_generator.insert_failed status=%d code=%s body=%s",
        r.status_code, (err or {}).get("code"), (r.text or "")[:300],
    )
    return None, f"http_{r.status_code}"

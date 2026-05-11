"""
app/services/lead_capture.py
=============================
Writes a lead row to public.leads in Supabase.

Used by:
  - app/routes/voice.py       (when voice lead is complete)
  - app/services/whatsapp_reply.py  (on first WhatsApp message)

Never raises — errors are logged so callers are not interrupted.
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_TABLE = "leads"


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


async def update_lead_name(phone: str, name: str) -> None:
    """
    Update the name on an existing lead (matched by phone) only if name is currently null.
    Never raises.
    """
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY or not phone or not name:
        return
    try:
        headers = {
            "apikey": _SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                params={"phone": f"eq.{phone}", "name": "is.null"},
                json={"name": name},
                headers=headers,
            )
            resp.raise_for_status()
        logger.info("[LEAD CAPTURE] Updated lead name for phone=%s name=%s", phone, name)
    except Exception as exc:
        logger.error("[LEAD CAPTURE] Failed to update lead name: %s", exc)


async def save_lead(data: dict) -> None:
    """
    Insert a row into public.leads.

    Accepted keys (all optional except phone and source):
        phone   : str  — required
        source  : str  — required, 'voice' or 'whatsapp'
        name    : str  — optional
        service : str  — optional
        status  : str  — optional, defaults to 'new' via DB default
        notes   : str  — optional
        agent_id: str  — optional UUID

    Never raises. Errors are logged.
    """
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        logger.warning("[LEAD CAPTURE] Supabase env vars not set — skipping lead save")
        return

    payload = {k: v for k, v in data.items() if v is not None}

    # Never let a new save overwrite an existing customer name.
    # If a row already exists for this phone with a non-null name, drop `name`
    # from the upsert payload — only fill name on first save or when previously null.
    if payload.get("name") and payload.get("phone"):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                    params={"phone": f"eq.{payload['phone']}", "select": "name", "limit": "1"},
                    headers=_headers(),
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    if rows and rows[0].get("name"):
                        payload.pop("name", None)
        except Exception as exc:
            logger.warning("[LEAD CAPTURE] name-preserve check failed (continuing): %s", exc)

    # Upsert on phone — if lead already exists (e.g. from WhatsApp), update it
    # instead of creating a duplicate. Requires unique constraint on leads.phone.
    upsert_headers = {
        **_headers(),
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                json=payload,
                headers=upsert_headers,
                params={"on_conflict": "phone"},
            )
            resp.raise_for_status()
        logger.info("[LEAD CAPTURE] Upserted lead phone=%s source=%s", data.get("phone"), data.get("source"))
    except Exception as exc:
        logger.error("[LEAD CAPTURE] Failed to save lead: %s | data=%s", exc, data)

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
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_TABLE = "leads"
_CALL_LOGS_TABLE = "call_logs"


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


async def _insert_call_log(
    *,
    agent_id: str | None,
    phone_number: str | None,
) -> None:
    """Insert one row into public.call_logs after a voice lead is saved.

    Minimal v0 payload — schema is (id, agent_id, phone_number, status,
    duration, created_at). duration is left null (call may still be in
    progress at save_lead time); status is a sentinel "captured" until a
    future end-of-call hook fills the real Twilio status.

    Never raises. Wrapped at the call site too; this helper is allowed to
    log and swallow any failure so the voice/lead flow proceeds.
    """
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        return
    if not agent_id:
        # call_logs.agent_id is required for tenant scoping (no client_id
        # column). Skip when missing rather than write an orphan row.
        return
    payload = {
        "agent_id": agent_id,
        "phone_number": phone_number or None,
        "status": "captured",
        "duration": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_CALL_LOGS_TABLE}",
                json=payload,
                headers=_headers(),
            )
            resp.raise_for_status()
        logger.info(
            "[CALL-LOG] inserted agent_id=%s phone=%s", agent_id, phone_number,
        )
    except Exception as exc:
        logger.warning("[CALL-LOG] insert skipped: %s", exc)


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
        # If the lead upsert itself failed, do NOT log a call row — keeps
        # call_logs aligned with what actually persisted in leads.
        return

    # Voice-only side-effect: write a minimal call_logs row so /home/calls
    # shows real activity. Wrapped here AND inside the helper — any failure
    # must never break the voice/lead capture flow.
    if data.get("source") in ("voice", "browser_voice"):
        try:
            await _insert_call_log(
                agent_id=data.get("agent_id"),
                phone_number=data.get("phone"),
            )
        except Exception as exc:
            logger.warning("[CALL-LOG] insert skipped (outer guard): %s", exc)

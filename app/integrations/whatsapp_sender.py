"""Shared WhatsApp send helpers for the assistant Telegram immediate-send pilot.

Self-contained, Twilio-backed. Mirrors the resolution + 24h-window + send logic
of ``app/routes/action_api.py`` (which is intentionally left untouched) so the
existing ``/api/actions/send-whatsapp`` endpoint keeps its exact behavior.

Hard rules baked in:
  * The 24h WhatsApp customer-service window is enforced here (``is_window_open``)
    and is NEVER bypassed.
  * Constructs NO Twilio client at import time — the client is built lazily
    inside ``twilio_send_whatsapp`` only when an actual send happens.
  * Never logs the message body, phone numbers in full, or Twilio credentials.

FUTURE (backlog — do not implement here yet): when the window is CLOSED, this is
where an approved WhatsApp *template* send (Twilio ContentSid + ContentVariables)
would branch in. For this pilot the caller returns a "please message first"
reply instead. See ``twilio_send_whatsapp`` TODO.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_TIMEOUT = 5.0
_WINDOW = timedelta(hours=24)


def _sb_headers() -> Dict[str, str]:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
    }


def config_ready() -> bool:
    return bool(_TWILIO_SID and _TWILIO_TOKEN and _SUPABASE_URL and _SUPABASE_SERVICE_KEY)


async def get_agent_whatsapp_number(agent_id: str) -> Optional[str]:
    """Fetch the Twilio-approved WhatsApp sender number for an agent."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/agents_config",
            params={"id": f"eq.{agent_id}", "select": "whatsapp_number", "limit": "1"},
            headers=_sb_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
    if not rows:
        return None
    return (rows[0].get("whatsapp_number") or "").strip() or None


async def get_leads_by_phone(phone: str, client_id: str) -> List[dict]:
    """All leads whose phone AND client_id both exactly match. The caller
    enforces exactly-one — no fuzzy/normalized matching here."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/leads",
            params={
                "phone": f"eq.{phone}",
                "client_id": f"eq.{client_id}",
                "select": "id,phone,last_whatsapp_inbound_at,client_id",
            },
            headers=_sb_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
    return list(rows or ())


def is_window_open(last_inbound: Optional[str]) -> bool:
    """True if the 24h WhatsApp customer-service window is open (recipient
    messaged within 24h). NULL/missing/unparseable -> closed (fail closed)."""
    if not last_inbound:
        return False
    try:
        ts = datetime.fromisoformat(str(last_inbound).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts) < _WINDOW
    except Exception:  # noqa: BLE001 — any parse issue -> treat as closed
        return False


async def twilio_send_whatsapp(*, sender_number: str, to_phone: str, body: str) -> Dict[str, Any]:
    """Send ONE free-text WhatsApp message via Twilio. Window must already be
    verified open by the caller — this does not itself send templates.

    Returns {"status": "sent"|"failed", "sid": str, "error": str}. Never raises.

    TODO (future template branch — do NOT implement in this pilot): when the
    window is closed, callers should route to an approved template send here via
    Twilio ``content_sid`` + ``content_variables`` (never bypass the window,
    never hardcode template text).
    """
    if not _TWILIO_SID or not _TWILIO_TOKEN:
        return {"status": "failed", "sid": "", "error": "twilio_not_configured"}
    try:
        from twilio.rest import Client  # lazy: no Twilio client at import time

        client = Client(_TWILIO_SID, _TWILIO_TOKEN)
        msg = await asyncio.to_thread(
            lambda: client.messages.create(
                from_=f"whatsapp:{sender_number}",
                to=f"whatsapp:{to_phone}",
                body=body,
            )
        )
        logger.info("[ASSISTANT-WA] sent sid=%s", msg.sid)
        return {"status": "sent", "sid": msg.sid, "error": ""}
    except Exception as exc:  # noqa: BLE001 — never crash the caller
        logger.warning("[ASSISTANT-WA] send failed: %s", type(exc).__name__)
        return {"status": "failed", "sid": "", "error": type(exc).__name__}

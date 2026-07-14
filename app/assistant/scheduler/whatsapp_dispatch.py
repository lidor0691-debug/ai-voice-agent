"""Scheduled WhatsApp dispatcher core (PR-B). Backend-direct send.

Sends DUE rows from ``assistant_scheduled_messages`` using the SAME server-side
gates as the immediate-send pilot (contact -> phone -> exactly-one lead -> 24h
window OPEN -> mapped agent -> Twilio free-text). The 24h WhatsApp window is
NEVER bypassed; a closed window fails the row (reason
``window_closed_needs_template``) and does not send.

Imported LAZILY by the scheduler route only when the dispatcher is enabled, so
importing the route pulls in no Twilio/data adapter. This module in turn imports
the data adapter + whatsapp_sender lazily inside its functions.

Duplicate-send protection: ``run_due`` first CLAIMS each row with an optimistic
single-winner lock (``data.claim_scheduled_message``) and only the winner sends.
A row that fails a gate or the Twilio send is marked ``failed`` (never retried
automatically — it leaves ``status=scheduled`` so the due query won't re-pick it).

FUTURE (backlog — NOT here): closed-window rows would route to an approved
WhatsApp *template* send. No template text, no ContentSid handling in this PR.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Gate outcomes surfaced to the owner/operator (never customer-facing).
REASON_CONTACT_NOT_FOUND = "contact_not_found"
REASON_MISSING_PHONE = "missing_phone"
REASON_NO_LEAD = "no_lead"
REASON_AMBIGUOUS_LEAD = "ambiguous_lead"
REASON_WINDOW_CLOSED = "window_closed_needs_template"
REASON_AGENT_NOT_CONFIGURED = "agent_not_configured"


async def _resolve_and_gate(
    row: Dict[str, Any], *, agent_map: Dict[str, str]
) -> Tuple[str, Any]:
    """Run every read-only gate for one due row. NO send, NO writes.

    Returns ("send", {"phone", "sender_number", "name"}) when eligible, or
    ("fail", <reason str>) otherwise. Reuses the immediate pilot's whatsapp_sender
    helpers so the two paths share identical gate semantics.
    """
    from app.assistant.data import supabase_adapter as data
    from app.integrations import whatsapp_sender as wa

    owner_id = row.get("owner_id")

    # 1) contact still exists + active
    contact = await data.get_contact_by_id(row.get("contact_id"))
    if not contact:
        return "fail", REASON_CONTACT_NOT_FOUND

    # 2) contact has a phone
    phone = (contact.get("phone") or "").strip()
    if not phone:
        return "fail", REASON_MISSING_PHONE

    # 3) exactly one matching lead (phone AND client_id==owner both exact)
    leads = await wa.get_leads_by_phone(phone, owner_id)
    if len(leads) == 0:
        return "fail", REASON_NO_LEAD
    if len(leads) > 1:
        return "fail", REASON_AMBIGUOUS_LEAD
    lead = leads[0]

    # 4) 24h WhatsApp window MUST be open — never bypassed.
    if not wa.is_window_open(lead.get("last_whatsapp_inbound_at")):
        return "fail", REASON_WINDOW_CLOSED

    # 5) mapped, approved WhatsApp agent for this owner
    agent_id = agent_map.get(owner_id)
    if not agent_id:
        return "fail", REASON_AGENT_NOT_CONFIGURED
    sender_number = await wa.get_agent_whatsapp_number(agent_id)
    if not sender_number:
        return "fail", REASON_AGENT_NOT_CONFIGURED

    return "send", {
        "phone": phone,
        "sender_number": sender_number,
        "name": contact.get("name"),
    }


async def evaluate_due(
    *, now: datetime, agent_map: Dict[str, str], limit: int = 200
) -> Dict[str, Any]:
    """Read-only: list due rows and each row's gate verdict. SENDS NOTHING and
    writes nothing (no claim, no status change, no Twilio)."""
    from app.assistant.data import supabase_adapter as data

    rows = await data.list_due_scheduled_messages(now.isoformat(), limit=limit)
    due: List[Dict[str, Any]] = []
    eligible = 0
    for row in rows:
        kind, info = await _resolve_and_gate(row, agent_map=agent_map)
        is_send = kind == "send"
        if is_send:
            eligible += 1
        due.append(
            {
                "message_id": row.get("id"),
                "owner_id": row.get("owner_id"),
                "scheduled_at": row.get("scheduled_at"),
                "eligible": is_send,
                "reason": None if is_send else info,
                "recipient": info.get("name") if is_send else None,
            }
        )
    return {"count": len(rows), "eligible": eligible, "due": due}


async def run_due(
    *, now: datetime, agent_map: Dict[str, str], limit: int = 200
) -> Dict[str, Any]:
    """Claim + send due rows. Returns {sent, failed, skipped, details}.

    Per row: claim (single winner) -> gate -> Twilio free-text send -> terminal
    status. A lost claim is skipped (never sent). A failed gate or Twilio error
    marks the row ``failed`` with a structured reason. NEVER bypasses the window,
    never sends templates, never sends twice.
    """
    from app.assistant.data import supabase_adapter as data
    from app.integrations import whatsapp_sender as wa

    rows = await data.list_due_scheduled_messages(now.isoformat(), limit=limit)
    sent = failed = skipped = 0
    details: List[Dict[str, Any]] = []

    for row in rows:
        mid = row.get("id")
        owner_id = row.get("owner_id")
        contact_id = row.get("contact_id")

        # Optimistic single-winner claim BEFORE any send.
        claimed = await data.claim_scheduled_message(mid, now=now)
        if not claimed:
            skipped += 1
            details.append({"message_id": mid, "outcome": "skipped",
                            "reason": "already_claimed_or_not_scheduled"})
            continue

        kind, info = await _resolve_and_gate(row, agent_map=agent_map)
        if kind != "send":
            await data.update_scheduled_status(mid, "failed")
            await data.log_activity(owner_id, "send_failed", scheduled_message_id=mid,
                                    contact_id=contact_id, detail={"reason": info})
            failed += 1
            details.append({"message_id": mid, "outcome": "failed", "reason": info})
            continue

        result = await wa.twilio_send_whatsapp(
            sender_number=info["sender_number"], to_phone=info["phone"], body=row.get("body")
        )
        if result.get("status") == "sent":
            await data.update_scheduled_status(mid, "sent", sent_at=now)
            await data.log_activity(owner_id, "sent", scheduled_message_id=mid,
                                    contact_id=contact_id, detail={"sid": result.get("sid")})
            sent += 1
            details.append({"message_id": mid, "outcome": "sent"})
        else:
            await data.update_scheduled_status(mid, "failed")
            await data.log_activity(owner_id, "send_failed", scheduled_message_id=mid,
                                    contact_id=contact_id,
                                    detail={"reason": "twilio_error", "error": result.get("error")})
            failed += 1
            details.append({"message_id": mid, "outcome": "failed", "reason": "twilio_error"})

    logger.info("[ASSISTANT-SCHED] run sent=%s failed=%s skipped=%s", sent, failed, skipped)
    return {"sent": sent, "failed": failed, "skipped": skipped, "details": details}

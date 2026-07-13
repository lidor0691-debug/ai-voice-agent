"""Scheduled Telegram -> WhatsApp job persistence (PR-A). PERSIST ONLY.

Imported LAZILY by the Telegram route only when a command is NOT immediate
(no עכשיו) AND the schedule flag is enabled. A FUTURE command that fully
resolves is written to ``assistant_scheduled_messages`` as a free-text job:

    send_plan = 'api_freeform', status = 'scheduled', body = text after "הודעה:"

This module NEVER sends. It imports no Twilio, no whatsapp_sender, no scheduler
— only the Supabase data adapter (lazily). Actual delivery (24h-window re-check,
Twilio send, status transitions) is a later dispatcher PR. Templates are out of
scope: closed-window handling belongs to the dispatcher, not here.

Gates (all must pass before one row is persisted; none of them send):
  1. parser produced a usable intent   -> else clarify (missing recipient/time)
  2. a send time is present            -> else missing-send-time clarification
  3. explicit body (after "הודעה:")     -> else reply_wa_no_body
  4. a recipient name from the parser
  5. EXACTLY ONE active assistant_contact -> 0: not_found, 2+: ambiguous
  6. that contact has a phone            -> else missing_phone (do NOT persist)
  7. persist the scheduled row (api_freeform / scheduled) + activity log
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.assistant.nlp.contract import ParseStatus, SendPlan
from app.assistant.telegram import replies
from app.assistant.telegram.intake import extract_body

logger = logging.getLogger(__name__)


def _intent_snapshot(intent: Any) -> Dict[str, Any]:
    """A JSON-safe snapshot of the parsed intent for the parsed_intent column.

    Enum members are reduced to their string values so PostgREST stores clean
    JSON. The message body is stored in its own column, not duplicated here.
    """
    return {
        "status": intent.status.value if intent.status else None,
        "recipient_name": intent.recipient_name,
        "recipient_type": intent.recipient_type.value if intent.recipient_type else None,
        "message_type": intent.message_type.value if intent.message_type else None,
        "scheduled_at_local": intent.scheduled_at_local,
        "is_explicit_time": intent.is_explicit_time,
        "related_event_date": intent.related_event_date,
        "inferred_notes": list(intent.inferred_notes or []),
    }


async def handle_scheduled_whatsapp(
    *,
    owner_id: str,
    intent: Any,
    raw_command: str,
) -> str:
    """Persist a FUTURE command as a scheduled free-text WhatsApp job.

    Returns the owner-facing Telegram reply. NEVER sends a message, never
    resolves a lead, never checks the 24h window (that is the dispatcher's job
    at send time), never touches Twilio. Only persists a durable row when every
    gate passes; otherwise replies with a clarification and persists nothing.
    """
    # Lazy import keeps the Telegram route's module import free of the data
    # adapter until an actual scheduled persist is attempted.
    from app.assistant.data import supabase_adapter as data

    # 1) Parser-level clarifications (no recipient named / incomplete). No persist.
    if intent.status == ParseStatus.NEEDS_CLARIFICATION:
        if not intent.recipient_name:
            return replies.reply_missing_recipient()
        return replies.reply_missing_send_time(
            recipient_name=intent.recipient_name,
            message_type=intent.message_type,
            related_event_date=intent.related_event_date,
        )

    # 2) A scheduled job REQUIRES an explicit send time. No time -> clarify.
    if not intent.scheduled_at_local:
        return replies.reply_missing_send_time(
            recipient_name=intent.recipient_name,
            message_type=intent.message_type,
            related_event_date=intent.related_event_date,
        )

    # 3) Explicit message body after "הודעה:". No body -> clarify, no persist.
    body = extract_body(raw_command)
    if not body:
        return replies.reply_wa_no_body()

    # 4) Recipient must be named.
    if not intent.recipient_name:
        return replies.reply_wa_contact_not_found()

    # 5) Exactly one active assistant_contact (exact name match, no fuzzy).
    candidates = await data.resolve_contact_candidates(
        owner_id, intent.recipient_name, intent.recipient_type
    )
    if len(candidates) == 0:
        return replies.reply_wa_contact_not_found()
    if len(candidates) > 1:
        return replies.reply_wa_ambiguous_contact()
    contact = candidates[0]
    name = contact.get("name") or intent.recipient_name

    # 6) Contact must have a phone. Decision: clarify NOW rather than persist an
    #    un-sendable job that would only fail later at dispatch. No persist.
    phone = (contact.get("phone") or "").strip()
    if not phone:
        return replies.reply_wa_missing_phone()

    # 7) Persist a scheduled free-text WhatsApp job. NO SEND happens here.
    smid = await data.insert_scheduled_message(
        owner_id,
        intent,
        raw_command=raw_command,
        contact_id=contact.get("id"),
        send_plan=SendPlan.API_FREEFORM.value,
        status="scheduled",
        body=body,
        parsed_intent=_intent_snapshot(intent),
    )
    if not smid:
        logger.warning("[ASSISTANT-WA-SCHED] persist failed for owner")
        return replies.reply_wa_schedule_save_failed()

    # Best-effort audit trail (mirrors command_core: resolved -> scheduled).
    contact_id = contact.get("id")
    await data.log_activity(
        owner_id,
        "resolved",
        scheduled_message_id=smid,
        contact_id=contact_id,
        detail={"send_plan": SendPlan.API_FREEFORM.value, "source": "telegram_schedule"},
    )
    await data.log_activity(
        owner_id, "scheduled", scheduled_message_id=smid, contact_id=contact_id
    )

    return replies.reply_scheduled(
        recipient_name=name,
        message_type=intent.message_type,
        scheduled_at_local=intent.scheduled_at_local,
        send_plan=SendPlan.API_FREEFORM,
    )

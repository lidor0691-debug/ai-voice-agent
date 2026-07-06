"""Immediate Telegram -> WhatsApp send flow (opt-in pilot). HEAVY module.

Imported LAZILY by the Telegram route only when a command is BOTH immediate
(contains עכשיו) AND the send flag is enabled — so a normal dry-run/preview
message never loads the data adapter or the WhatsApp/Twilio path.

Every gate must pass before one real WhatsApp message is sent:
  1. explicit body (after "הודעה:")            -> else reply_wa_no_body
  2. a recipient name from the parser
  3. EXACTLY ONE active assistant_contact       -> 0: not_found, 2+: ambiguous
  4. that contact has a phone                    -> else missing_phone
  5. EXACTLY ONE public.leads row with phone==contact.phone AND client_id==owner
                                                 -> 0: no_lead, 2+: ambiguous_lead
  6. the 24h WhatsApp window is OPEN (never bypassed) -> else window_closed
  7. an approved WhatsApp agent is mapped for the owner
  8. send exactly one free-text message via the shared Twilio helper

No scheduler, no bulk, no fuzzy matching, no templates (see whatsapp_sender TODO).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.assistant.telegram import replies

logger = logging.getLogger(__name__)


async def handle_immediate_whatsapp(
    *,
    owner_id: str,
    recipient_name: Optional[str],
    recipient_type: Any,
    body: Optional[str],
    agent_map: Dict[str, str],
) -> str:
    """Run all gates and, only if every one passes, send exactly one WhatsApp
    message. Returns the owner-facing Telegram reply. Never sends to a customer
    number, never bypasses the 24h window, never fuzzy-matches."""
    # Lazy imports keep the Telegram route's module import free of the data
    # adapter and Twilio until an actual immediate send is attempted.
    from app.assistant.data import supabase_adapter as data
    from app.integrations import whatsapp_sender as wa

    # 1) explicit message body
    if not body:
        return replies.reply_wa_no_body()

    # 2) recipient named by the parser
    if not recipient_name:
        return replies.reply_wa_contact_not_found()

    # 3) exactly one active assistant_contact (exact name match, no fuzzy)
    candidates = await data.resolve_contact_candidates(owner_id, recipient_name, recipient_type)
    if len(candidates) == 0:
        return replies.reply_wa_contact_not_found()
    if len(candidates) > 1:
        return replies.reply_wa_ambiguous_contact()
    contact = candidates[0]
    name = contact.get("name") or recipient_name

    # 4) contact must have a phone
    phone = (contact.get("phone") or "").strip()
    if not phone:
        return replies.reply_wa_missing_phone()

    # 5) exactly one matching lead (phone AND client_id both exact)
    leads = await wa.get_leads_by_phone(phone, owner_id)
    if len(leads) == 0:
        return replies.reply_wa_no_lead()
    if len(leads) > 1:
        return replies.reply_wa_ambiguous_lead()
    lead = leads[0]

    # 6) 24h WhatsApp window MUST be open — never bypassed.
    #    FUTURE (backlog): if closed, branch to an approved template send here
    #    (Twilio ContentSid + ContentVariables). For this pilot we stop.
    if not wa.is_window_open(lead.get("last_whatsapp_inbound_at")):
        return replies.reply_wa_window_closed(name)

    # 7) approved WhatsApp agent for this owner
    agent_id = agent_map.get(owner_id)
    if not agent_id:
        logger.info("[ASSISTANT-WA] no agent mapped for owner")
        return replies.reply_wa_not_configured()
    sender_number = await wa.get_agent_whatsapp_number(agent_id)
    if not sender_number:
        logger.info("[ASSISTANT-WA] agent has no whatsapp_number")
        return replies.reply_wa_not_configured()

    # 8) send exactly one free-text message
    result = await wa.twilio_send_whatsapp(sender_number=sender_number, to_phone=phone, body=body)
    if result.get("status") == "sent":
        return replies.reply_wa_sent(name)
    return replies.reply_wa_send_failed()

"""Assistant Command Core — parse -> resolve -> persist -> log. DORMANT (PR3).

One entry point, ``process_command``, turns a raw owner command into exactly one
durable outcome:
  * a SCHEDULED assistant message (status='scheduled' + resolved send_plan), or
  * a PENDING CLARIFICATION (missing_send_time | missing_recipient |
    unknown_recipient | ambiguous), plus an activity-log entry.

Key PR3 decisions:
  * Resolved commands persist status='scheduled' for ALL send plans. The core
    never writes 'reminded_manual' / 'waiting_for_approval' / 'approved' /
    'sent' / 'failed' — those transitions belong to a later dispatcher PR.
  * Recipient ambiguity is DB-driven (0 -> unknown, 1 -> resolve, 2+ -> ambiguous).
  * A PARSED intent with no send time is treated as a missing_send_time
    clarification rather than an invalid scheduled-row insert.

Nothing in the running service imports this module. No Telegram/Twilio/Make/
scheduler/route here. The Stage-1 parser is injected.
"""
from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any, List, Optional

from app.assistant.core.parser_port import CommandResult, ParserProtocol
from app.assistant.data import supabase_adapter as data
from app.assistant.nlp.contract import (
    Contact,
    ParsedIntent,
    ParseStatus,
    RecipientType,
)
from app.assistant.nlp.resolver import resolve_send_plan

_CLARIFY_PROMPTS = {
    "missing_send_time": "When should I send this?",
    "missing_recipient": "Who should this message go to?",
    "unknown_recipient": "I couldn't find that contact — what's their phone number so I can add them?",
    "ambiguous": "More than one contact matches — which one did you mean?",
}


def _parser_clarification_type(intent: ParsedIntent) -> str:
    """Map a parser NEEDS_CLARIFICATION intent to a clarification type."""
    if not intent.recipient_name:
        return "missing_recipient"
    return "missing_send_time"


async def _open_clarification(
    owner_id: str,
    raw_command: str,
    clarification_type: str,
    *,
    source: Optional[dict] = None,
    detail: Optional[dict] = None,
) -> CommandResult:
    prompt = _CLARIFY_PROMPTS[clarification_type]
    cid = await data.insert_pending_clarification(
        owner_id, raw_command, prompt, clarification_type, detail=detail
    )
    log_detail: dict = {"clarification_type": clarification_type}
    if source:
        log_detail["source"] = source
    await data.log_activity(owner_id, "clarification_opened", detail=log_detail)
    return CommandResult(
        kind="clarification",
        status="needs_clarification",
        clarification_id=cid,
        clarification_type=clarification_type,
        reason=prompt,
    )


async def process_command(
    owner_id: str,
    raw_command: str,
    *,
    parser: ParserProtocol,
    now: Optional[datetime] = None,
    source: Optional[dict] = None,
) -> CommandResult:
    """Process one owner command. See module docstring for the flow + decisions."""
    # ── Stage 1: parse (injected; sync or async) ─────────────────────────────
    intent = parser.parse(raw_command, now=now)
    if inspect.isawaitable(intent):
        intent = await intent

    # Parser-driven clarifications (no recipient named / no send time).
    if intent.status == ParseStatus.NEEDS_CLARIFICATION:
        return await _open_clarification(
            owner_id, raw_command, _parser_clarification_type(intent), source=source
        )

    # Safety: PARSED but no send time -> clarify, never insert an invalid row.
    if not intent.scheduled_at_local:
        return await _open_clarification(
            owner_id, raw_command, "missing_send_time", source=source
        )

    # ── DB-driven recipient resolution ───────────────────────────────────────
    candidates: List[dict] = await data.resolve_contact_candidates(
        owner_id, intent.recipient_name, intent.recipient_type
    )
    if len(candidates) == 0:
        return await _open_clarification(
            owner_id, raw_command, "unknown_recipient", source=source
        )
    if len(candidates) > 1:
        detail = {
            "candidates": [
                {"id": c.get("id"), "name": c.get("name")} for c in candidates
            ]
        }
        return await _open_clarification(
            owner_id, raw_command, "ambiguous", source=source, detail=detail
        )

    # ── Stage 2: resolve send plan for the single matched contact ────────────
    c = candidates[0]
    contact = Contact(
        name=c["name"],
        recipient_type=RecipientType(c["recipient_type"]),
        phone=c.get("phone"),
    )
    window = data.within_24h_window(c.get("last_inbound_at"), now=now)
    templates = await data.list_active_templates(owner_id)
    plan = resolve_send_plan(
        intent, contact, within_24h_window=window, active_templates=templates
    )

    # ── Persist scheduled work (status='scheduled' for every plan) ───────────
    contact_id: Any = c.get("id")
    smid = await data.insert_scheduled_message(
        owner_id,
        intent,
        raw_command=raw_command,
        contact_id=contact_id,
        send_plan=plan.send_plan.value,
        status="scheduled",
    )
    await data.log_activity(
        owner_id,
        "resolved",
        scheduled_message_id=smid,
        contact_id=contact_id,
        detail={"send_plan": plan.send_plan.value, "reason": plan.reason},
    )
    await data.log_activity(
        owner_id, "scheduled", scheduled_message_id=smid, contact_id=contact_id
    )
    return CommandResult(
        kind="scheduled",
        status="scheduled",
        send_plan=plan.send_plan,
        scheduled_message_id=smid,
        reason=plan.reason,
    )

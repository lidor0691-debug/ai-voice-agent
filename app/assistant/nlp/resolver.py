"""Stage-2 RESOLVE: deterministic send_plan decision tree.

This is REAL production logic. It is deliberately decoupled from any data
source: callers inject the looked-up ``Contact``, whether the contact is inside
the WhatsApp 24h customer-service window, and which message types currently
have an *active* template. There are NO Supabase reads, NO DB writes, and NO
network calls here.

Decision order (first match wins):

  1. Group recipient                         -> group_manual
  2. No contact / no phone on file           -> manual_fallback
  3. Inside the 24h service window           -> api_freeform
  4. Outside window, active template exists  -> api_template
  5. Outside window, no active template      -> manual_fallback
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Set

from app.assistant.nlp.contract import (
    Contact,
    MessageType,
    ParsedIntent,
    RecipientType,
    SendPlan,
)


@dataclass
class ResolvedPlan:
    """Result of Stage-2 resolution."""

    send_plan: SendPlan
    reason: str


def _normalize_active_templates(
    active_templates: Optional[Iterable[MessageType]],
) -> Set[MessageType]:
    """Coerce the injected active-template collection into a set of MessageType.

    Accepts MessageType members or their string values so callers (and tests)
    can pass either form.
    """
    result: Set[MessageType] = set()
    for item in active_templates or ():
        if isinstance(item, MessageType):
            result.add(item)
        else:
            result.add(MessageType(item))
    return result


def resolve_send_plan(
    intent: ParsedIntent,
    contact: Optional[Contact],
    *,
    within_24h_window: bool = False,
    active_templates: Optional[Iterable[MessageType]] = None,
) -> ResolvedPlan:
    """Decide how an already-parsed intent should be delivered.

    Args:
        intent: the Stage-1 ``ParsedIntent``.
        contact: the resolved recipient, or ``None`` if no contact is known.
        within_24h_window: True if the contact is inside the WhatsApp 24h
            customer-service window (free text allowed).
        active_templates: message types that currently have an ACTIVE template.

    Returns:
        A ``ResolvedPlan`` carrying the chosen ``SendPlan`` and a short reason.
    """
    templates = _normalize_active_templates(active_templates)

    # 1. Groups are always handled manually — no automated API send.
    recipient_type = contact.recipient_type if contact else intent.recipient_type
    if recipient_type == RecipientType.GROUP:
        return ResolvedPlan(SendPlan.GROUP_MANUAL, "group recipients are sent manually")

    # 2. No contact or no phone on file -> cannot use the API.
    if contact is None or not contact.phone:
        return ResolvedPlan(SendPlan.MANUAL_FALLBACK, "no phone on file")

    # 3. Inside the 24h service window -> free text via API.
    if within_24h_window:
        return ResolvedPlan(SendPlan.API_FREEFORM, "inside 24h service window")

    # 4. Outside the window -> an ACTIVE template is required to use the API.
    if intent.message_type is not None and intent.message_type in templates:
        return ResolvedPlan(SendPlan.API_TEMPLATE, "active template available")

    # 5. Outside the window with no active template -> manual fallback.
    return ResolvedPlan(SendPlan.MANUAL_FALLBACK, "no active template outside 24h window")

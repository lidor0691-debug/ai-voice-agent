"""LLM output schema + mapping to the assistant contract. DORMANT (PR4).

The Claude Stage-1 adapter (llm_parser.py) constrains Claude to emit
``LLMParseResult`` (structured outputs), then maps it into the production
``ParsedIntent`` here. This module is the pure, network-free seam unit tests
drive directly.

The LLM never emits ``send_plan`` and never resolves contacts — recipient
resolution (0/1/2+ candidates) stays in the Command Core, and send-plan
selection stays in the pure resolver.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

from app.assistant.nlp.contract import (
    MessageType,
    ParsedIntent,
    ParseStatus,
    RecipientType,
)

# Literal value sets — kept in lockstep with the contract enums by a test.
RECIPIENT_TYPE_VALUES = ("client", "teacher", "group")
MESSAGE_TYPE_VALUES = ("agreement", "deposit", "video", "lesson_coordination", "custom")
STATUS_VALUES = ("parsed", "needs_clarification")

# Safe-fallback reason recorded in inferred_notes when output is unusable.
UNCLEAR_INTENT = "unclear_intent"


class LLMParseResult(BaseModel):
    """Exactly what Claude is allowed to return. No send_plan, no contact id."""

    status: Literal["parsed", "needs_clarification"]
    recipient_name: Optional[str] = None
    recipient_type: Optional[Literal["client", "teacher", "group"]] = None
    message_type: Optional[
        Literal["agreement", "deposit", "video", "lesson_coordination", "custom"]
    ] = None
    scheduled_at_local: Optional[str] = None
    is_explicit_time: bool = False
    related_event_date: Optional[str] = None
    clarification: Optional[str] = None
    inferred_notes: Optional[List[str]] = None


def safe_clarification(
    reason: str = UNCLEAR_INTENT,
    message: str = "I couldn't understand that — could you rephrase?",
) -> ParsedIntent:
    """A safe NEEDS_CLARIFICATION result for malformed/invalid/refused output."""
    return ParsedIntent(
        status=ParseStatus.NEEDS_CLARIFICATION,
        clarification=message,
        inferred_notes=[reason],
    )


def _coerce_enums(r: "LLMParseResult"):
    """Coerce enum strings; raise ValueError on an invalid value."""
    rtype = RecipientType(r.recipient_type) if r.recipient_type else None
    mtype = MessageType(r.message_type) if r.message_type else None
    return rtype, mtype


def to_parsed_intent(r: Optional["LLMParseResult"]) -> ParsedIntent:
    """Map a validated LLM result into a ParsedIntent, failing safe.

    * None / unusable                          -> safe_clarification
    * invalid enum value                       -> safe_clarification
    * status='parsed' missing recipient/time   -> safe_clarification (incoherent)
    * status='needs_clarification'             -> preserved (with any partial fields)
    * status='parsed' (coherent)               -> mapped through
    """
    if r is None:
        return safe_clarification()

    try:
        rtype, mtype = _coerce_enums(r)
    except ValueError:
        return safe_clarification()

    if r.status == "needs_clarification":
        return ParsedIntent(
            status=ParseStatus.NEEDS_CLARIFICATION,
            recipient_name=r.recipient_name,
            recipient_type=rtype,
            message_type=mtype,
            scheduled_at_local=r.scheduled_at_local,
            related_event_date=r.related_event_date,
            clarification=r.clarification,
            inferred_notes=r.inferred_notes or [],
        )

    # status == 'parsed' — must be coherent (a recipient and a real send time).
    if not r.recipient_name or not r.scheduled_at_local:
        return safe_clarification()

    return ParsedIntent(
        status=ParseStatus.PARSED,
        recipient_name=r.recipient_name,
        recipient_type=rtype,
        message_type=mtype,
        scheduled_at_local=r.scheduled_at_local,
        is_explicit_time=bool(r.is_explicit_time),
        related_event_date=r.related_event_date,
        inferred_notes=r.inferred_notes or [],
    )

"""Shared vocabulary for the assistant NLP pipeline.

This is the *contract* — the enums and dataclasses that both Stage-1 (PARSE)
and Stage-2 (RESOLVE) agree on. It is pure data + stdlib only:

  * no Supabase / network / DB
  * no Twilio / Telegram / Make
  * no import of the test oracle parser, fixtures, or the frozen clock

Stage-1 (PARSE) turns natural language into a ``ParsedIntent``. In PRODUCTION
that stage is an LLM (Claude). The rule-based parser under tests/ is a TEST
ORACLE only and must never be wired as the live Stage-1.

Stage-2 (RESOLVE) is deterministic backend logic (see resolver.py) that turns a
``ParsedIntent`` + injected contact/template/window data into a ``SendPlan``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class RecipientType(str, Enum):
    """Who the message is going to."""

    CLIENT = "client"
    TEACHER = "teacher"
    GROUP = "group"


class MessageType(str, Enum):
    """What kind of message this is.

    NOTE: the old ``teacher`` type was renamed to ``lesson_coordination`` to
    avoid colliding with ``RecipientType.TEACHER``.
    """

    AGREEMENT = "agreement"
    DEPOSIT = "deposit"
    VIDEO = "video"
    LESSON_COORDINATION = "lesson_coordination"
    CUSTOM = "custom"


class ParseStatus(str, Enum):
    """Outcome of Stage-1 parsing."""

    PARSED = "parsed"
    NEEDS_CLARIFICATION = "needs_clarification"


class SendPlan(str, Enum):
    """Stage-2 decision: how the message will actually be delivered.

    * ``group_manual``    — group recipients are always sent by hand.
    * ``manual_fallback`` — no usable phone, or outside the 24h window with no
                            active template; the owner sends manually.
    * ``api_template``    — outside the 24h window, an active template exists.
    * ``api_freeform``    — inside the 24h customer-service window; free text.
    """

    GROUP_MANUAL = "group_manual"
    MANUAL_FALLBACK = "manual_fallback"
    API_TEMPLATE = "api_template"
    API_FREEFORM = "api_freeform"


# Message types that are template-backed (i.e. an approved WhatsApp template
# can exist for them). ``custom`` is intentionally absent: free text only.
TEMPLATE_TYPES = frozenset(
    {
        MessageType.AGREEMENT,
        MessageType.DEPOSIT,
        MessageType.VIDEO,
        MessageType.LESSON_COORDINATION,
    }
)


@dataclass
class Contact:
    """A resolved contact. In production this is hydrated from Supabase; here it
    is injected so the resolver stays decoupled from any data source.

    ``phone`` is ``None`` when no number is on file (forces manual fallback).
    """

    name: str
    recipient_type: RecipientType
    phone: Optional[str] = None


@dataclass
class ParsedIntent:
    """Structured output of Stage-1 (PARSE).

    ``scheduled_at_local`` is the SEND time (ISO local, Asia/Jerusalem wall
    clock). ``related_event_date`` is the date the message is ABOUT and does
    NOT by itself satisfy the send-time requirement — a parse with only an
    event date and no send time is ``needs_clarification``.
    """

    status: ParseStatus
    recipient_name: Optional[str] = None
    recipient_type: Optional[RecipientType] = None
    message_type: Optional[MessageType] = None
    scheduled_at_local: Optional[str] = None  # ISO datetime, the SEND time
    is_explicit_time: bool = False  # False when the time was inferred (10:00)
    related_event_date: Optional[str] = None  # ISO date the message is ABOUT
    body: Optional[str] = None
    clarification: Optional[str] = None  # set when status == NEEDS_CLARIFICATION
    inferred_notes: List[str] = field(default_factory=list)  # surfaced inferences

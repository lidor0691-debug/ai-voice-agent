"""Stage-1 parser seam + command result types for the Command Core.

The parser is INJECTED into the core — the core never imports the rule-based
test oracle, and PR3 ships no real LLM adapter. A conforming parser turns a raw
command into a ``ParsedIntent``; it may be sync or async (the core awaits the
result if it is awaitable).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Optional, Protocol, Union, runtime_checkable

from app.assistant.nlp.contract import ParsedIntent, SendPlan


@runtime_checkable
class ParserProtocol(Protocol):
    """Stage-1: natural language -> ParsedIntent. Sync or async."""

    def parse(
        self, raw_command: str, *, now: Optional[datetime] = None
    ) -> Union[ParsedIntent, Awaitable[ParsedIntent]]:
        ...


@dataclass
class CommandResult:
    """Outcome of Command Core processing.

    kind: 'scheduled' (a scheduled_messages row was created) or
          'clarification' (a pending_clarifications row was created).
    """

    kind: str
    status: Optional[str] = None              # 'scheduled' | 'needs_clarification'
    send_plan: Optional[SendPlan] = None      # set when kind == 'scheduled'
    scheduled_message_id: Optional[str] = None
    clarification_id: Optional[str] = None
    clarification_type: Optional[str] = None  # missing_send_time | missing_recipient | unknown_recipient | ambiguous
    reason: Optional[str] = None

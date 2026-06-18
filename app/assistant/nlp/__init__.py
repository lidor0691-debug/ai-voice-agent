"""Assistant NLP foundation: shared vocab (contract) + Stage-2 resolver.

Production-bound, but DORMANT in PR1 — no route/handler imports this.

Modules:
  - contract:  enums + dataclasses + TEMPLATE_TYPES (shared parse/resolve vocab)
  - resolver:  deterministic Stage-2 send_plan decision (decoupled from any
               fixtures/DB/network; takes injected contact/template/window data)

The deterministic rule-based parser is a TEST ORACLE only and lives under
tests/assistant/nlp/. It must NEVER be wired as the live Stage-1 parser.
"""
from app.assistant.nlp.contract import (
    Contact,
    MessageType,
    ParseStatus,
    ParsedIntent,
    RecipientType,
    SendPlan,
    TEMPLATE_TYPES,
)
from app.assistant.nlp.resolver import ResolvedPlan, resolve_send_plan

__all__ = [
    "Contact",
    "MessageType",
    "ParseStatus",
    "ParsedIntent",
    "RecipientType",
    "SendPlan",
    "TEMPLATE_TYPES",
    "ResolvedPlan",
    "resolve_send_plan",
]

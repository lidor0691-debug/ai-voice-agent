"""Assistant Command Core.

DORMANT as of PR3: nothing in the running service imports this package. It
orchestrates the existing foundations — Stage-1 parsing (injected via the
ParserProtocol seam), the pure Stage-2 resolver (app/assistant/nlp), and the
Supabase data adapter (app/assistant/data) — into a single command flow:
parse -> resolve -> persist -> log.

No Telegram, Twilio, Make, scheduler, or route wiring. No real LLM parser is
included here (the seam is inject-only); production Stage-1 lands in a later PR.
"""
from app.assistant.core.command_core import process_command
from app.assistant.core.parser_port import CommandResult, ParserProtocol

__all__ = ["process_command", "CommandResult", "ParserProtocol"]

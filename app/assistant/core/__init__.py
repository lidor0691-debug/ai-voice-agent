"""Assistant Command Core.

DORMANT: nothing in the running service imports this package. It orchestrates
the existing foundations — Stage-1 parsing (injected via the ParserProtocol
seam), the pure Stage-2 resolver (app/assistant/nlp), and the Supabase data
adapter (app/assistant/data) — into one flow: parse -> resolve -> persist -> log.

Imports are LAZY (PEP 562 ``__getattr__``): importing this package, or a leaf
module like ``app.assistant.core.llm_parser``, does NOT eagerly load
``command_core`` (and therefore does not pull in ``app.assistant.data``). The
public names below resolve only when explicitly accessed
(``from app.assistant.core import process_command``).

No Telegram, Twilio, Make, scheduler, or route wiring.
"""
from typing import TYPE_CHECKING

__all__ = ["process_command", "CommandResult", "ParserProtocol"]

if TYPE_CHECKING:  # for type checkers / IDEs only; not executed at runtime
    from app.assistant.core.command_core import process_command
    from app.assistant.core.parser_port import CommandResult, ParserProtocol


def __getattr__(name: str):
    if name == "process_command":
        from app.assistant.core.command_core import process_command

        return process_command
    if name in ("CommandResult", "ParserProtocol"):
        from app.assistant.core import parser_port

        return getattr(parser_port, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

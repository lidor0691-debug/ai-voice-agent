"""Pure parsing/auth helpers for Telegram intake. No I/O, no network.

These functions turn raw env strings + a raw Telegram update into validated,
typed values the route can trust. They never log secrets and never raise on
malformed input (bad entries are skipped, not fatal).
"""
from __future__ import annotations

import hmac
import re
import uuid
from typing import Dict, Optional, Set, TypedDict

# Lexical marker that a command means "send immediately / now" (vs a future
# scheduled command). Kept deliberately narrow for the immediate-send pilot.
_IMMEDIATE_MARKERS = ("עכשיו",)

# Body delimiter: the message content follows "הודעה:" (Hebrew "message:").
_BODY_RE = re.compile(r"הודעה\s*:\s*(.+)$", re.DOTALL)


class Update(TypedDict):
    update_id: Optional[int]
    user_id: int
    chat_id: int
    text: str


def parse_allowed_user_ids(raw: str) -> Set[int]:
    """CSV of numeric Telegram user ids -> set[int]. Empty/garbage -> empty set
    (which means deny-all). Non-numeric tokens are skipped silently."""
    out: Set[int] = set()
    for tok in (raw or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.add(int(tok))
        except ValueError:
            continue
    return out


def parse_owner_map(raw: str) -> Dict[int, str]:
    """CSV of ``<tg_user_id>:<owner_uuid>`` -> dict[int, str].

    Splits each pair on the FIRST ':'. A pair is kept only if the id is an int
    and the owner id parses as a UUID; malformed pairs are skipped.
    """
    out: Dict[int, str] = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        tg_raw, owner_raw = item.split(":", 1)
        tg_raw, owner_raw = tg_raw.strip(), owner_raw.strip()
        try:
            tg_id = int(tg_raw)
        except ValueError:
            continue
        try:
            uuid.UUID(owner_raw)
        except (ValueError, AttributeError, TypeError):
            continue
        out[tg_id] = owner_raw
    return out


def parse_owner_agent_map(raw: str) -> Dict[str, str]:
    """CSV of ``<owner_uuid>:<agent_uuid>`` -> dict[str, str] (owner -> WhatsApp
    agent). Splits on the FIRST ':'. Both sides must be UUIDs; bad pairs skipped.
    """
    out: Dict[str, str] = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        owner_raw, agent_raw = item.split(":", 1)
        owner_raw, agent_raw = owner_raw.strip(), agent_raw.strip()
        try:
            uuid.UUID(owner_raw)
            uuid.UUID(agent_raw)
        except (ValueError, AttributeError, TypeError):
            continue
        out[owner_raw] = agent_raw
    return out


def is_immediate_command(text: Optional[str]) -> bool:
    """True if the command clearly means "send now" (contains עכשיו). Purely
    lexical — future/scheduled commands (e.g. "מחר ב-10:00") return False."""
    if not text:
        return False
    return any(marker in text for marker in _IMMEDIATE_MARKERS)


def extract_body(text: Optional[str]) -> Optional[str]:
    """Extract the message body after the "הודעה:" delimiter, trimmed.

    Returns None when there is no delimiter or the body is empty. Deterministic;
    no NLP — the send path requires an explicit body.
    """
    if not text:
        return None
    m = _BODY_RE.search(text)
    if not m:
        return None
    body = m.group(1).strip()
    return body or None


def verify_secret(header_value: Optional[str], configured: Optional[str]) -> bool:
    """Constant-time compare of the Telegram secret header to the configured
    secret. Returns False if either side is empty/missing (fail closed)."""
    if not header_value or not configured:
        return False
    return hmac.compare_digest(str(header_value), str(configured))


def extract_update(update: object) -> Optional[Update]:
    """Pull (update_id, user_id, chat_id, text) from a Telegram update.

    Returns None for anything not a usable text *message* (edited messages,
    callbacks, non-text, or missing from/chat) — the caller treats None as a
    neutral no-op.
    """
    if not isinstance(update, dict):
        return None
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    frm = message.get("from")
    chat = message.get("chat")
    if not isinstance(frm, dict) or not isinstance(chat, dict):
        return None
    user_id = frm.get("id")
    chat_id = chat.get("id")
    if not isinstance(user_id, int) or not isinstance(chat_id, int):
        return None
    update_id = update.get("update_id")
    return Update(
        update_id=update_id if isinstance(update_id, int) else None,
        user_id=user_id,
        chat_id=chat_id,
        text=text,
    )

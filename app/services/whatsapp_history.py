"""
app/services/whatsapp_history.py
=================================
Supabase-backed conversation history for WhatsApp sessions.

Public API
----------
append_whatsapp_messages(phone, user_message, assistant_message) -> list[dict]
    Loads the existing messages_json from whatsapp_conversations,
    appends the new user + assistant turn, saves clean JSON back,
    and returns the full updated messages array.

Normalization rules:
    - null / missing  → treated as []
    - stringified JSON array (Make sometimes double-serializes) → parsed
    - any other invalid value → fall back to []
"""

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
_SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
_TABLE             = "whatsapp_conversations"


def _headers() -> dict:
    return {
        "apikey":        _SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {_SUPABASE_ANON_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _normalize_messages(raw) -> list[dict]:
    """
    Coerce whatever is stored in messages_json into a plain Python list.

    Handles:
      - None / missing                → []
      - already a list                → used as-is
      - stringified JSON (str)        → parsed; falls back to [] on error
      - anything else                 → []
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            logger.warning("[WHATSAPP HISTORY] Could not parse messages_json string — resetting to []")
            return []
    logger.warning("[WHATSAPP HISTORY] Unexpected messages_json type %s — resetting to []", type(raw))
    return []


async def _load_row(phone: str) -> Optional[dict]:
    """Return the existing whatsapp_conversations row for this phone, or None."""
    url = f"{_SUPABASE_URL}/rest/v1/{_TABLE}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            url,
            params={"phone": f"eq.{phone}", "limit": 1},
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None


async def _upsert_messages(phone: str, messages: list[dict]) -> None:
    """
    Insert or update the row for this phone with the new messages array.
    on_conflict=phone tells Supabase which column to use for conflict resolution.
    """
    url = f"{_SUPABASE_URL}/rest/v1/{_TABLE}?on_conflict=phone"
    headers = {**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            url,
            json={"phone": phone, "messages_json": messages},
            headers=headers,
        )
        resp.raise_for_status()


async def append_whatsapp_messages(
    phone: str,
    user_message: str,
    assistant_message: str,
) -> list[dict]:
    """
    Load, normalize, append, save, and return the full updated messages array.

    Appended turn format:
        {"role": "user",      "content": user_message}
        {"role": "assistant", "content": assistant_message}

    Always returns the updated list.  Never raises — on any error the
    in-memory updated list is still returned so Make can continue.
    """
    # Load existing row
    try:
        row = await _load_row(phone)
    except Exception as exc:
        logger.error("[WHATSAPP HISTORY] Failed to load row for %s: %s", phone, exc)
        row = None

    existing = _normalize_messages(row.get("messages_json") if row else None)

    updated = existing + [
        {"role": "user",      "content": user_message},
        {"role": "assistant", "content": assistant_message},
    ]

    # Persist clean JSON array back to Supabase
    try:
        await _upsert_messages(phone, updated)
        logger.info(
            "[WHATSAPP HISTORY] Saved %d messages for %s", len(updated), phone
        )
    except Exception as exc:
        logger.error("[WHATSAPP HISTORY] Failed to save messages for %s: %s", phone, exc)

    return updated

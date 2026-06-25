"""Telegram Bot API outbound helper. Owner-facing replies only.

The ONLY outbound side effect of the assistant Telegram intake. Sends a reply
back to the studio owner's chat after successful auth. No customer messaging,
no Twilio, no WhatsApp.

Constructs no client at import time (httpx client is created lazily per call).
Never logs the bot token or the message text.
"""
from __future__ import annotations

import logging

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"
_TIMEOUT = 10.0


async def send_message(chat_id: int, text: str) -> bool:
    """POST sendMessage to the owner's chat. Returns True on success.

    Fails closed (returns False) when no bot token is configured. The token is
    never logged; the message text is never logged.
    """
    token = settings.ASSISTANT_TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("[ASSISTANT-TG] no bot token configured — skipping reply.")
        return False
    url = f"{_API_BASE}/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
            resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — never crash the webhook on reply failure
        logger.warning("[ASSISTANT-TG] reply send failed: %s", type(exc).__name__)
        return False

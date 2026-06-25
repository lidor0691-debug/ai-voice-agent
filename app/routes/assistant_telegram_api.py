"""Owner-only Telegram intake webhook. Mounted only when intake is enabled.

Flow (after the master flag + secret + allowlist/owner-map gates pass):
    update -> ClaudeParser (Stage-1) -> reply
      * dry-run (default): build a preview reply from the parsed intent; NO DB.
      * persist (opt-in):  run Command Core (parse already done -> reuse it),
                           which writes only assistant_* tables; NO sending.

Hard safety:
  * Defensive re-check of ASSISTANT_TELEGRAM_INTAKE_ENABLED at request time.
  * Wrong/missing secret is rejected BEFORE body/owner-map/parser.
  * Unauthorized/unmapped users get a neutral 200 — no parser, no Command Core,
    no Supabase, no sendMessage.
  * ClaudeParser, Command Core, and the Supabase adapter are imported LAZILY,
    so importing this module touches none of them; the adapter loads only when
    the persist path runs.
  * Only owner-facing Telegram replies are ever sent. No Twilio/WhatsApp/
    scheduler/dispatcher. Secrets/tokens/customer text are never logged.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Request

from app.assistant.telegram import replies
from app.assistant.telegram.intake import (
    extract_update,
    parse_allowed_user_ids,
    parse_owner_map,
    verify_secret,
)
from app.config.settings import settings
from app.integrations import telegram_client

logger = logging.getLogger(__name__)

router = APIRouter()

WEBHOOK_PATH = "/assistant/telegram/webhook"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

# Best-effort in-memory idempotency (v1). Bounded LRU of seen update_ids.
_SEEN_UPDATE_IDS: "OrderedDict[int, None]" = OrderedDict()
_SEEN_MAX = 1024

_OK = {"ok": True}  # neutral 200 body for every branch (Telegram ignores it)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_parser() -> Any:
    """Construct the real Stage-1 parser. Lazy import so module import does not
    pull in Anthropic. Tests monkeypatch this to inject a fake parser."""
    from app.assistant.core.llm_parser import ClaudeParser

    return ClaudeParser()


class _PreparsedParser:
    """A ParserProtocol that returns an already-computed intent — lets Command
    Core run without a SECOND model call (we parsed once in the route)."""

    def __init__(self, intent: Any) -> None:
        self._intent = intent

    def parse(self, raw_command: str, *, now: Optional[datetime] = None) -> Any:
        return self._intent


def _already_seen(update_id: Optional[int]) -> bool:
    """Return True if this update_id was handled before (dedupe). None -> never
    deduped (we cannot key it)."""
    if update_id is None:
        return False
    if update_id in _SEEN_UPDATE_IDS:
        _SEEN_UPDATE_IDS.move_to_end(update_id)
        return True
    _SEEN_UPDATE_IDS[update_id] = None
    if len(_SEEN_UPDATE_IDS) > _SEEN_MAX:
        _SEEN_UPDATE_IDS.popitem(last=False)
    return False


def _dry_run_reply(intent: Any) -> str:
    from app.assistant.nlp.contract import ParseStatus

    if intent.status == ParseStatus.NEEDS_CLARIFICATION:
        if not intent.recipient_name:
            return replies.reply_missing_recipient(dry_run=True)
        return replies.reply_missing_send_time(
            recipient_name=intent.recipient_name,
            message_type=intent.message_type,
            related_event_date=intent.related_event_date,
            dry_run=True,
        )
    if not intent.scheduled_at_local:
        return replies.reply_missing_send_time(
            recipient_name=intent.recipient_name,
            message_type=intent.message_type,
            related_event_date=intent.related_event_date,
            dry_run=True,
        )
    return replies.reply_scheduled(
        recipient_name=intent.recipient_name,
        message_type=intent.message_type,
        scheduled_at_local=intent.scheduled_at_local,
        send_plan=None,  # dry-run does no contact resolution
        dry_run=True,
    )


def _persist_reply(intent: Any, result: Any) -> str:
    if result.kind == "scheduled":
        return replies.reply_scheduled(
            recipient_name=intent.recipient_name,
            message_type=intent.message_type,
            scheduled_at_local=intent.scheduled_at_local,
            send_plan=result.send_plan,
        )
    ct = result.clarification_type
    if ct == "missing_recipient":
        return replies.reply_missing_recipient()
    if ct == "unknown_recipient":
        return replies.reply_unknown_recipient(recipient_name=intent.recipient_name)
    if ct == "ambiguous":
        return replies.reply_ambiguous(recipient_name=intent.recipient_name)
    # default: missing_send_time
    return replies.reply_missing_send_time(
        recipient_name=intent.recipient_name,
        message_type=intent.message_type,
        related_event_date=intent.related_event_date,
    )


@router.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    # 0) Defensive master-gate re-check (independent of conditional mounting).
    if not settings.ASSISTANT_TELEGRAM_INTAKE_ENABLED:
        return _OK

    # 1) Secret header — before body parsing / owner-map / parser.
    secret = request.headers.get(SECRET_HEADER)
    if not verify_secret(secret, settings.ASSISTANT_TELEGRAM_WEBHOOK_SECRET):
        logger.info("[ASSISTANT-TG] reject: secret")
        return _OK

    # 2) Body -> usable text message (neutral no-op otherwise).
    try:
        update = await request.json()
    except Exception:  # noqa: BLE001 — malformed body is a neutral no-op
        return _OK
    extracted = extract_update(update)
    if extracted is None:
        return _OK

    user_id = extracted["user_id"]
    chat_id = extracted["chat_id"]
    text = extracted["text"]
    update_id = extracted["update_id"]

    # 3) Allowlist + owner-map (auth). Unknown -> neutral 200, no work, no reply.
    allowed = parse_allowed_user_ids(settings.ASSISTANT_TELEGRAM_ALLOWED_USER_IDS)
    owner_map = parse_owner_map(settings.ASSISTANT_TELEGRAM_OWNER_MAP)
    if user_id not in allowed or user_id not in owner_map:
        logger.info("[ASSISTANT-TG] reject: unauthorized user_id=%s", user_id)
        return _OK
    owner_id = owner_map[user_id]

    # 4) Idempotency (best-effort, in-memory) — dedupe retried deliveries.
    if _already_seen(update_id):
        logger.info("[ASSISTANT-TG] dedupe: update_id=%s", update_id)
        return _OK

    # 5) Parse ONCE (live Claude in prod; injected fake in tests).
    parser = _build_parser()
    intent = parser.parse(text, now=_now())
    import inspect

    if inspect.isawaitable(intent):
        intent = await intent

    # 6) Reply per mode.
    if settings.ASSISTANT_TELEGRAM_DRY_RUN:
        reply = _dry_run_reply(intent)
    else:
        # Persist path — lazy import so the adapter loads only when used.
        from app.assistant.core import command_core

        result = await command_core.process_command(
            owner_id,
            text,
            parser=_PreparsedParser(intent),
            now=_now(),
            source={"channel": "telegram", "tg_user_id": user_id},
        )
        reply = _persist_reply(intent, result)

    # 7) Owner-facing reply only.
    if reply:
        await telegram_client.send_message(chat_id, reply)
    return _OK

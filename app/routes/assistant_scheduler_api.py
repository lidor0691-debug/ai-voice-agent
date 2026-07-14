"""Protected scheduled-WhatsApp dispatcher API (PR-B). Mounted ONLY when enabled.

Two endpoints, both requiring the ``X-Assistant-Scheduler-Secret`` header:

  * GET  /assistant/scheduler/due  — read-only; lists due api_freeform rows and
                                      each row's gate verdict. Sends nothing.
  * POST /assistant/scheduler/run  — claims due rows and sends eligible ones via
                                      the backend Twilio helper; returns a summary.

Hard safety:
  * Router is only mounted when ASSISTANT_SCHEDULER_ENABLED (see main.py); a
    defensive re-check returns 404 if it is ever reached while disabled.
  * Wrong/missing secret -> 401 before any work (constant-time compare).
  * The heavy dispatcher core + Twilio/data path are imported LAZILY, so
    importing this module pulls in no Twilio and no data adapter.
  * Backend-direct send only: the 24h window is enforced server-side and never
    bypassed. No Make-driven Twilio send. No scheduler thread/cron here — an
    external cron may CALL these endpoints, but the logic lives in the backend.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException

from app.assistant.telegram.intake import parse_owner_agent_map, verify_secret
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

DUE_PATH = "/assistant/scheduler/due"
RUN_PATH = "/assistant/scheduler/run"
SECRET_HEADER = "X-Assistant-Scheduler-Secret"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _guard(secret: str) -> None:
    """Defensive enabled re-check + constant-time secret check. Raises 404 when
    disabled, 401 on a bad/missing secret. Runs before any lazy import."""
    if not settings.ASSISTANT_SCHEDULER_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    if not verify_secret(secret, settings.ASSISTANT_SCHEDULER_SECRET):
        logger.info("[ASSISTANT-SCHED] reject: secret")
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get(DUE_PATH)
async def scheduler_due(
    x_assistant_scheduler_secret: str = Header(default="", alias=SECRET_HEADER),
):
    _guard(x_assistant_scheduler_secret)
    from app.assistant.scheduler.whatsapp_dispatch import evaluate_due  # lazy

    agent_map = parse_owner_agent_map(settings.ASSISTANT_TELEGRAM_WHATSAPP_AGENT_MAP)
    result = await evaluate_due(now=_now(), agent_map=agent_map)
    return {"ok": True, "dry_run": True, **result}


@router.post(RUN_PATH)
async def scheduler_run(
    x_assistant_scheduler_secret: str = Header(default="", alias=SECRET_HEADER),
):
    _guard(x_assistant_scheduler_secret)
    from app.assistant.scheduler.whatsapp_dispatch import run_due  # lazy

    agent_map = parse_owner_agent_map(settings.ASSISTANT_TELEGRAM_WHATSAPP_AGENT_MAP)
    result = await run_due(now=_now(), agent_map=agent_map)
    return {"ok": True, **result}

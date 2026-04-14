# app/routes/dev_agent.py
"""
POST /agent/command
====================
Twilio sends WhatsApp messages here.
Only messages from OWNER_PHONE are accepted.
Incoming approvals (כן/לא) resolve pending approvals in the queue.
All other messages are enqueued as tasks for the daemon.
"""
import logging
import os
from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks, Form, Response

from agent.queue import TaskQueue

logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_queue() -> TaskQueue:
    return TaskQueue()


def _enqueue_command(sender: str, command: str) -> None:
    """Enqueue in background — called after Twilio already got the 200 response."""
    try:
        q = get_queue()
        if len(command) > 1500:
            logger.warning("Long message received (%d chars)", len(command))
        consumed = q.handle_incoming_message(command)
        if consumed:
            logger.info("Approval response received: %s", command)
        else:
            task_id = q.enqueue(command)
            logger.info("Task enqueued id=%s len=%d command=%r", task_id, len(command), command[:80])
    except Exception as e:
        logger.error("Failed to enqueue command from %s: %s", sender, e, exc_info=True)


@router.post("/agent/command")
async def agent_command(
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    Body: str = Form(...),
) -> Response:
    """Receive a WhatsApp message from Twilio. Returns immediately so Twilio never times out."""
    logger.info("WEBHOOK HIT from=%r body_len=%d body_preview=%r", From, len(Body), Body[:100])
    sender = From.replace("whatsapp:", "").strip()

    owner_phone = os.environ.get("OWNER_PHONE", "").strip()
    if sender.lstrip("+") != owner_phone.lstrip("+"):
        logger.warning("Ignored message from unknown sender: %s", sender)
        return Response(content="<Response/>", media_type="application/xml")

    # Return 200 to Twilio immediately, process in background
    background_tasks.add_task(_enqueue_command, sender, Body.strip())
    return Response(content="<Response/>", media_type="application/xml")

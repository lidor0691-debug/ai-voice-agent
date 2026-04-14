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

from fastapi import APIRouter, Form, Response

from agent.queue import TaskQueue

logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_queue() -> TaskQueue:
    return TaskQueue()


@router.post("/agent/command")
async def agent_command(
    From: str = Form(...),
    Body: str = Form(...),
) -> Response:
    """Receive a WhatsApp message from Twilio."""
    # Twilio sends From as "whatsapp:+972..."
    sender = From.replace("whatsapp:", "").strip()

    owner_phone = os.environ.get("OWNER_PHONE", "").strip()
    if sender.lstrip("+") != owner_phone.lstrip("+"):
        logger.warning("Ignored message from unknown sender: %s", sender)
        return Response(content="<Response/>", media_type="application/xml")

    try:
        q = get_queue()
        command = Body.strip()

        # Check if this is an approval response first
        consumed = q.handle_incoming_message(command)
        if consumed:
            logger.info("Approval response received: %s", command)
        else:
            task_id = q.enqueue(command)
            logger.info("Task enqueued id=%s command=%r", task_id, command)
    except Exception as e:
        logger.error("Failed to process command from %s: %s", sender, e, exc_info=True)

    return Response(content="<Response/>", media_type="application/xml")

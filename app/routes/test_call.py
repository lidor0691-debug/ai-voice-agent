import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from twilio.rest import Client
from app.config.settings import settings
from app.services.agent_config import get_agent_phone_number_by_id

logger = logging.getLogger(__name__)
router = APIRouter()


class TestCallRequest(BaseModel):
    agent_id: str
    to_phone: str


@router.post("/test-call")
async def start_test_call(body: TestCallRequest):
    if not body.agent_id or not body.to_phone:
        raise HTTPException(status_code=400, detail="agent_id and to_phone are required")

    agent_phone = await get_agent_phone_number_by_id(body.agent_id)
    if not agent_phone:
        raise HTTPException(status_code=404, detail="Agent not found or has no phone number configured")

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise HTTPException(status_code=503, detail="Twilio credentials not configured on this server")

    webhook_url = f"{settings.BASE_URL}/voice-ai/test-voice?agent_id={body.agent_id}"

    try:
        twilio = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        call = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: twilio.calls.create(
                to=body.to_phone,
                from_=agent_phone,
                url=webhook_url,
            ),
        )
        logger.info("[TEST CALL] initiated | to=%s | from=%s | sid=%s", body.to_phone, agent_phone, call.sid)
        return {"call_sid": call.sid, "status": "initiated"}
    except Exception as exc:
        logger.error("[TEST CALL] Failed to initiate call: %s", exc)
        raise HTTPException(status_code=502, detail=f"Failed to initiate call: {exc}")

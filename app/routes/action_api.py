"""
Action API — execute approved user actions (WhatsApp send, etc.)

All actions require explicit API call — nothing is auto-triggered.
"""

import os
import re
import logging
import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

_TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_WHATSAPP_FROM = os.getenv("AGENT_WHATSAPP_FROM", "")


class SendWhatsAppRequest(BaseModel):
    phone: str = Field(..., description="E.164 phone number, e.g. +972543033010")
    message: str = Field(..., min_length=1, max_length=1500)
    lead_name: str = Field(default="")
    agent_id: str = Field(default="")
    # Future: lead_id for server-side phone lookup
    lead_id: str | None = Field(default=None)


class SendWhatsAppResponse(BaseModel):
    status: str  # "sent" | "failed"
    sid: str = ""
    error: str = ""


def _validate_phone(phone: str) -> str:
    """Validate and normalize phone to E.164. Raises ValueError if invalid."""
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    if not cleaned.startswith("+"):
        raise ValueError(f"Phone must start with +, got: {phone}")
    if len(cleaned) < 10 or len(cleaned) > 16:
        raise ValueError(f"Phone length invalid: {phone}")
    return cleaned


@router.post("/api/actions/send-whatsapp", response_model=SendWhatsAppResponse)
async def send_whatsapp(req: SendWhatsAppRequest):
    """
    Send an approved WhatsApp message via Twilio.
    Called only after explicit user approval in ActionCard.
    """
    # ── Validate Twilio config ───────────────────────────────────────────
    if not _TWILIO_SID or not _TWILIO_TOKEN:
        logger.error("[ACTION] Twilio credentials not configured")
        raise HTTPException(status_code=503, detail="Twilio not configured")

    if not _WHATSAPP_FROM:
        logger.error("[ACTION] AGENT_WHATSAPP_FROM not configured")
        raise HTTPException(status_code=503, detail="WhatsApp sender not configured")

    # ── Validate phone ───────────────────────────────────────────────────
    try:
        phone = _validate_phone(req.phone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Future: resolve phone from lead_id if provided ───────────────────
    # if req.lead_id and not req.phone:
    #     phone = await _lookup_phone_by_lead_id(req.lead_id)

    # ── Send via Twilio ──────────────────────────────────────────────────
    logger.info(
        "[ACTION] Sending WhatsApp: to=%s lead=%s agent=%s len=%d",
        phone, req.lead_name, req.agent_id[:8] if req.agent_id else "-", len(req.message),
    )

    try:
        from twilio.rest import Client
        client = Client(_TWILIO_SID, _TWILIO_TOKEN)

        msg = await asyncio.to_thread(
            lambda: client.messages.create(
                from_=f"whatsapp:{_WHATSAPP_FROM}",
                to=f"whatsapp:{phone}",
                body=req.message,
            )
        )

        logger.info("[ACTION] WhatsApp sent: sid=%s to=%s", msg.sid, phone)
        return SendWhatsAppResponse(status="sent", sid=msg.sid)

    except Exception as exc:
        logger.error("[ACTION] WhatsApp failed: %s", exc)
        return SendWhatsAppResponse(status="failed", error=str(exc))

"""
Action API — execute approved user actions (WhatsApp send, etc.)

All actions require explicit API call — nothing is auto-triggered.
Sender and lead phone are resolved server-side from Supabase.
No global env fallback — each agent must have whatsapp_sender configured.
"""

import os
import re
import logging
import asyncio

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

_TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _sb_headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
    }


class SendWhatsAppRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    lead_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=1500)


class SendWhatsAppResponse(BaseModel):
    status: str  # "sent" | "failed"
    sid: str = ""
    error: str = ""


async def _get_agent_sender(agent_id: str) -> str | None:
    """Fetch whatsapp_sender from agents_config by agent_id."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/agents_config",
            params={"id": f"eq.{agent_id}", "select": "whatsapp_sender", "limit": "1"},
            headers=_sb_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        return (rows[0].get("whatsapp_sender") or "").strip() or None


async def _get_lead_phone(lead_id: str) -> str | None:
    """Fetch phone from leads by lead_id."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/leads",
            params={"id": f"eq.{lead_id}", "select": "phone", "limit": "1"},
            headers=_sb_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        return (rows[0].get("phone") or "").strip() or None


def _validate_phone(phone: str) -> str:
    """Validate E.164 format. Raises ValueError if invalid."""
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
    Resolves sender from agent config, phone from lead record.
    Called only after explicit user approval.
    """
    # ── Validate Twilio config ───────────────────────────────────────────
    if not _TWILIO_SID or not _TWILIO_TOKEN:
        raise HTTPException(status_code=503, detail="Twilio not configured")

    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Database not configured")

    # ── Resolve sender from agent ────────────────────────────────────────
    try:
        sender = await _get_agent_sender(req.agent_id)
    except Exception as exc:
        logger.error("[ACTION] Failed to lookup agent sender: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to lookup agent config")

    if not sender:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp sender not configured for this agent",
        )

    # ── Resolve phone from lead ──────────────────────────────────────────
    try:
        lead_phone = await _get_lead_phone(req.lead_id)
    except Exception as exc:
        logger.error("[ACTION] Failed to lookup lead: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to lookup lead")

    if not lead_phone:
        raise HTTPException(status_code=400, detail="Lead not found or has no phone number")

    try:
        phone = _validate_phone(lead_phone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Send via Twilio ──────────────────────────────────────────────────
    logger.info(
        "[ACTION] Sending WhatsApp: from=%s to=%s agent=%s lead=%s len=%d",
        sender, phone, req.agent_id[:8], req.lead_id[:8], len(req.message),
    )

    try:
        from twilio.rest import Client
        client = Client(_TWILIO_SID, _TWILIO_TOKEN)

        msg = await asyncio.to_thread(
            lambda: client.messages.create(
                from_=f"whatsapp:{sender}",
                to=f"whatsapp:{phone}",
                body=req.message,
            )
        )

        logger.info("[ACTION] WhatsApp sent: sid=%s", msg.sid)
        return SendWhatsAppResponse(status="sent", sid=msg.sid)

    except Exception as exc:
        logger.error("[ACTION] WhatsApp failed: %s", exc)
        return SendWhatsAppResponse(status="failed", error=str(exc))

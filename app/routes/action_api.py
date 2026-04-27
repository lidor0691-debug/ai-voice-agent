"""
Action API — execute approved user actions (WhatsApp send, etc.)

All actions require explicit API call — nothing is auto-triggered.
Sender and lead phone are resolved server-side from Supabase.
No global env fallback — each agent must have whatsapp_number configured.
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
    """Fetch whatsapp_number from agents_config by agent_id."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/agents_config",
            params={"id": f"eq.{agent_id}", "select": "whatsapp_number", "limit": "1"},
            headers=_sb_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        return (rows[0].get("whatsapp_number") or "").strip() or None


async def _get_lead(lead_id: str) -> dict | None:
    """Fetch phone + last_whatsapp_inbound_at from leads by lead_id."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/leads",
            params={"id": f"eq.{lead_id}", "select": "phone,last_whatsapp_inbound_at", "limit": "1"},
            headers=_sb_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        return rows[0]


def _is_window_open(last_inbound: str | None) -> bool:
    """Check if 24h WhatsApp conversation window is open."""
    if not last_inbound:
        return False
    try:
        from datetime import datetime, timezone, timedelta
        ts = datetime.fromisoformat(last_inbound.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts) < timedelta(hours=24)
    except Exception:
        return False


def _validate_phone(phone: str) -> str:
    """Validate and normalize to E.164 format. Raises ValueError if invalid."""
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    # Auto-add + if starts with country code digits
    if not cleaned.startswith("+") and len(cleaned) >= 10:
        cleaned = f"+{cleaned}"
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

    # ── Resolve lead ──────────────────────────────────────────────────────
    try:
        lead = await _get_lead(req.lead_id)
    except Exception as exc:
        logger.error("[ACTION] Failed to lookup lead: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to lookup lead")

    if not lead:
        raise HTTPException(status_code=400, detail="Lead not found")

    lead_phone = (lead.get("phone") or "").strip()
    if not lead_phone:
        raise HTTPException(status_code=400, detail="Lead has no phone number")

    try:
        phone = _validate_phone(lead_phone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Check 24h conversation window ────────────────────────────────────
    if not _is_window_open(lead.get("last_whatsapp_inbound_at")):
        logger.info(
            "[ACTION] 24h window closed for lead=%s (last_inbound=%s)",
            req.lead_id[:8], lead.get("last_whatsapp_inbound_at"),
        )
        return SendWhatsAppResponse(
            status="failed",
            error="24h WhatsApp window closed — template required",
        )

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

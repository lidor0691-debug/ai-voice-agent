"""
Maya Watch route — minimal endpoints for the thin-slice validation flow.

Endpoints:
    POST /maya-watch/inbound                 — webhook (Twilio form OR JSON)
    POST /maya-watch/tick                    — manual scan + act
    GET  /maya-watch/leads                   — list all leads + outcomes
    GET  /maya-watch/leads/{phone}           — single lead
    POST /maya-watch/leads/{phone}/mark-booked — manual booking confirmation
    GET  /maya-watch/health                  — alive

For wiring real Twilio: point your WhatsApp Sandbox / Business webhook at
    POST https://<host>/maya-watch/inbound
Twilio sends application/x-www-form-urlencoded with From / Body / ProfileName.
For testing without Twilio: POST JSON  {"phone": "+9725...", "body": "..."}
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Request

from app.services import maya_watch as svc

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/maya-watch/inbound")
async def inbound(request: Request):
    """Accept Twilio form-encoded WhatsApp webhook OR plain JSON for testing."""
    content_type = request.headers.get("content-type", "")
    phone = ""
    body = ""
    name = None

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        phone = svc.normalize_phone(str(form.get("From") or ""))
        body = str(form.get("Body") or "").strip()
        n = str(form.get("ProfileName") or "").strip()
        name = n or None
    else:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(400, "expected JSON or form-encoded payload")
        phone = svc.normalize_phone(str(data.get("phone", "")))
        body = str(data.get("body", "")).strip()
        n = data.get("name")
        name = str(n).strip() if isinstance(n, str) and n.strip() else None

    if not phone or not body:
        raise HTTPException(400, "phone and body are required")

    lead = svc.register_inbound(phone, body, name=name)
    return {
        "ok": True,
        "phone": phone,
        "status": svc.derive_status(lead),
    }


@router.post("/maya-watch/tick")
async def tick_endpoint():
    return await svc.tick()


@router.get("/maya-watch/leads")
def list_leads():
    return {"leads": [svc.serialize_lead(l) for l in svc.get_all_leads()]}


@router.get("/maya-watch/leads/{phone:path}")
def get_lead(phone: str):
    norm = svc.normalize_phone(phone)
    for lead in svc.get_all_leads():
        if lead.phone == norm:
            return svc.serialize_lead(lead)
    raise HTTPException(404, "lead not found")


@router.post("/maya-watch/leads/{phone:path}/mark-booked")
def mark_booked_endpoint(phone: str):
    lead = svc.mark_booked(phone)
    if not lead:
        raise HTTPException(404, "lead not found")
    return {"ok": True, "phone": lead.phone, "booked_at": lead.booked_at.isoformat()}


@router.get("/maya-watch/briefing")
def briefing():
    return svc.build_briefing()


@router.get("/maya-watch/health")
def health():
    return {
        "ok": True,
        "leads_in_memory": len(svc.get_all_leads()),
        "risk_after_minutes": svc.RISK_AFTER_MINUTES,
        "no_response_after_hours": svc.NO_RESPONSE_AFTER_HOURS,
    }

"""
app/routes/assets.py
====================
POST /assets/trigger — resolve client assets by trigger_key.

Returns a structured JSON payload of enabled assets for the given
client_id + trigger_key. Always 200 — count=0 is a valid empty result.
Make.com calls this endpoint and handles WhatsApp delivery.
"""

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.client_assets import get_assets_by_trigger

router = APIRouter()


class TriggerRequest(BaseModel):
    client_id:      str
    trigger_key:    str
    trigger_source: Optional[str] = None   # "voice" | "make" | "external"
    event_id:       Optional[str] = None   # caller-supplied idempotency key (echoed, not stored)
    context:        Optional[dict[str, Any]] = None  # free-form, passed through to response


@router.post("/trigger")
async def trigger_assets(req: TriggerRequest):
    """
    Resolve and return all enabled assets for a client + trigger key.
    Never 4xx for missing assets — count=0 means no assets configured.
    """
    assets = await get_assets_by_trigger(req.client_id, req.trigger_key)
    return {
        "client_id":      req.client_id,
        "trigger_key":    req.trigger_key,
        "trigger_source": req.trigger_source,
        "event_id":       req.event_id,
        "count":          len(assets),
        "assets":         assets,
        "context":        req.context or {},
    }

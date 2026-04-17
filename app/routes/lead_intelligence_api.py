"""
app/routes/lead_intelligence_api.py
=====================================
POST /lead-intelligence/test-extract

Internal endpoint for validating Lead Intelligence extraction and storage.
Accepts raw conversation text + context, runs heuristic extraction,
saves to lead_intelligence_insights, and returns both extracted and saved results.

Not wired into any live production flow. Call manually or from tests only.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.lead_intelligence import extract_insights, save_insights

logger = logging.getLogger(__name__)
router = APIRouter()


class TestExtractRequest(BaseModel):
    client_id:        str
    agent_id:         Optional[str] = None
    source_type:      Literal["whatsapp", "call", "chat"]
    source_record_id: Optional[str] = None
    text:             str


@router.post("/lead-intelligence/test-extract")
async def test_extract(req: TestExtractRequest):
    """
    Extract insights from raw text and save to lead_intelligence_insights.

    Returns:
        extracted: list of insight dicts produced by extract_insights (pre-save)
        saved:     list of rows returned by save_insights (upserted to DB)
    """
    extracted = extract_insights(req.text)

    saved = await save_insights(
        insights=extracted,
        client_id=req.client_id,
        agent_id=req.agent_id,
        source_type=req.source_type,
        source_record_id=req.source_record_id,
    )

    return {"extracted": extracted, "saved": saved}

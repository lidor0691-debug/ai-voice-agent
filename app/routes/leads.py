"""
Leads API routes — exposes Google Sheets lead data to the Next.js dashboard.
"""
import logging

from fastapi import APIRouter, HTTPException, Query

from app.integrations.google_sheets import get_leads

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("")
async def list_leads(
    status: str | None = Query(None, description="Filter by status"),
    intent: str | None = Query(None, description="Filter by intent/category"),
):
    """
    Return all leads from Google Sheets, with optional filtering.

    Query params:
      - status: e.g. "ליד חדש" or "תור נקבע"
      - intent: e.g. "נסיעת מבחן"  (matches if the lead's intents array contains it)
    """
    print("LEADS ENDPOINT HIT", flush=True)
    try:
        leads = get_leads()
    except Exception as exc:
        logger.error("Unexpected error fetching leads: %s", exc)
        raise HTTPException(status_code=503, detail="Google Sheets unavailable")

    print(f"LEADS RETURNED: {len(leads)}", flush=True)

    if status:
        leads = [l for l in leads if l.get("status") == status]
    if intent:
        leads = [l for l in leads if intent in l.get("intents", [])]

    return {"leads": leads, "total": len(leads)}


@router.get("/{lead_id}")
async def get_lead(lead_id: str):
    """Return a single lead by its row-based ID."""
    leads = get_leads()
    lead = next((l for l in leads if l["id"] == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead

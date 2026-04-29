"""
app/routes/attribution_api.py
==============================
Attribution Ledger v0 — Phase 2a API surface.

POST /attribution/run-batch
    Trigger the batch attribution worker. Idempotent.
    Manually before demos, or on a Make.com cron.

GET  /attribution/recovered?client_id=X[&since=ISO8601]
    Return recovered_total, attributed_count, unattributed_count.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.attribution import (
    compute_recovered_revenue,
    run_batch_attribution,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/attribution", tags=["Attribution"])


@router.post("/run-batch")
async def run_batch():
    """
    Process every unattributed outcome. Single-touch latest-in-window rule.
    """
    try:
        result = await run_batch_attribution()
        logger.info("[ATTRIBUTION] batch run %s", result)
        return result
    except Exception as exc:
        logger.error("[ATTRIBUTION] batch run failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/recovered")
async def recovered(
    client_id: str = Query(..., description="UUID of the client"),
    since: Optional[str] = Query(
        None,
        description="ISO8601 timestamp; only edges created at/after this are summed",
    ),
):
    """
    Recovered revenue summary for a client. Pair with an MRI scan by
    passing scan.created_at as `since` and scan.client_id as `client_id`
    to compare actual recovered vs. mri_scans.recoverable_monthly forecast.
    """
    try:
        return await compute_recovered_revenue(client_id, since)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[ATTRIBUTION] recovered read failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

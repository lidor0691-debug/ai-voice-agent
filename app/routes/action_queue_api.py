"""
app/routes/action_queue_api.py
================================
GET /api/action-queue/scan — trigger daily leak scan.

Make.com calls this endpoint on a cron (daily at 7:00 AM).
Protected by FOLLOWUP_SECRET (same secret as /followup/due).
Only scans clients listed in LEAK_SCAN_CLIENTS env var.
"""

import os
import logging

from fastapi import APIRouter, Header, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

_FOLLOWUP_SECRET = os.getenv("FOLLOWUP_SECRET", "")
_LEAK_SCAN_CLIENTS = os.getenv("LEAK_SCAN_CLIENTS", "")


@router.get("/api/action-queue/scan")
async def run_leak_scan(x_followup_secret: str = Header(default="")):
    if _FOLLOWUP_SECRET and x_followup_secret != _FOLLOWUP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    client_ids = [c.strip() for c in _LEAK_SCAN_CLIENTS.split(",") if c.strip()]
    if not client_ids:
        return {"error": "No clients configured", "scanned_clients": 0}

    from app.services.leak_scanner import scan_all
    result = await scan_all(client_ids)
    return result

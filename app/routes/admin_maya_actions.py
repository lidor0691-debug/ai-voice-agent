"""
app/routes/admin_maya_actions.py
================================
Phase 3.8B — admin-only DRY-RUN endpoint for the Maya action suggestion generator.

POST /admin/maya-actions/generate-from-briefing
Body: { "briefing_id": "<uuid>" }

Strict invariants
-----------------
- Admin only (Supabase JWT, user_metadata.role == "admin").
- DRY-RUN only. No DB writes. No insert path exists in the called service.
- No Twilio. No execution. No RPC calls into approve/skip/edit/set_permission.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.maya_action_generator import (
    BriefingNotFound,
    GeneratorAbort,
    generate_dry_run,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


class GenerateRequest(BaseModel):
    briefing_id: str = Field(..., min_length=8, max_length=64)


async def _require_admin(authorization: Optional[str]) -> str:
    """
    Validate the bearer token via Supabase auth and require admin role.
    Returns the admin user's id (uuid string). Raises HTTPException otherwise.

    Mirrors the inline pattern used in app/routes/voice_browser.py:430+.
    """
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        logger.error("[admin/maya-actions] Supabase env not configured")
        raise HTTPException(status_code=500, detail="server_misconfigured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="not_authenticated")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="not_authenticated")

    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{_SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey":        _SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("[admin/maya-actions] auth lookup failed: %s", exc)
        raise HTTPException(status_code=401, detail="not_authenticated")

    if r.status_code != 200:
        logger.warning("[admin/maya-actions] token validation failed: %d", r.status_code)
        raise HTTPException(status_code=401, detail="not_authenticated")

    data = r.json()
    meta = data.get("user_metadata") or {}
    if meta.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return data.get("id") or ""


@router.post("/admin/maya-actions/generate-from-briefing")
async def generate_from_briefing(
    body: GenerateRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """DRY-RUN: preview which maya_action_suggestions a real run would create.
    Writes nothing. See app/services/maya_action_generator.py."""
    admin_uid = await _require_admin(authorization)
    logger.info(
        "[admin/maya-actions] dry-run requested admin_uid=%s briefing_id=%s",
        admin_uid, body.briefing_id,
    )

    try:
        result = await generate_dry_run(body.briefing_id)
    except BriefingNotFound:
        raise HTTPException(status_code=404, detail="briefing_not_found")
    except GeneratorAbort as abort:
        return {
            "ok":         False,
            "dry_run":    True,
            "aborted":    True,
            "reason":     abort.reason,
            "error_he":   abort.error_he,
            "briefing_id": body.briefing_id,
        }
    except RuntimeError as exc:
        logger.error("[admin/maya-actions] runtime error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return result

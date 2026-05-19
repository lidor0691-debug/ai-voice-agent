"""
app/routes/maya_actions_execute.py
==================================
Phase 3.11C-5 — FastAPI route for executing one Maya action suggestion.

POST /maya-actions/{suggestion_id}/execute
Body: { "expected_version": <int> }

Auth contract
-------------
- Reads `Authorization: Bearer <token>` from the request header.
- Validates the token via Supabase Auth (`GET /auth/v1/user`), mirroring the
  inline pattern in `app/routes/admin_maya_actions.py:_require_admin`.
  The role check is intentionally NOT applied — any authenticated user may
  reach this endpoint. Tenant ownership is enforced inside the SECURITY
  DEFINER RPC `claim_action_for_execution` via the user JWT.
- The user JWT is forwarded into `execute_one(...)` and from there into
  the user-JWT Supabase RPC helper. The route never derives a `user_id`
  or `client_id` from the request body, and never logs or returns the JWT.

No admin override endpoint exists in 3.11 (per the locked design).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Path
from pydantic import BaseModel, Field, StrictInt

from app.services.maya_action_executor import execute_one

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth helper (mirrors app/routes/admin_maya_actions.py pattern) ──────────

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


async def _verify_bearer(authorization: Optional[str]) -> str:
    """Return the validated user JWT, or raise HTTPException(401).

    Uses Supabase Auth `GET /auth/v1/user` to verify the token. Does NOT
    check `user_metadata.role` — any authenticated user passes.
    """
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        logger.error("[maya-actions/execute] Supabase env not configured")
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
        logger.warning("[maya-actions/execute] auth lookup network error: %s",
                       type(exc).__name__)
        raise HTTPException(status_code=401, detail="not_authenticated")

    if r.status_code != 200:
        logger.warning("[maya-actions/execute] token validation failed: %d",
                       r.status_code)
        raise HTTPException(status_code=401, detail="not_authenticated")

    return token


# ── Request body ────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    # StrictInt rejects bool (which is an int subclass in Python) at parse time,
    # so True/False can never coerce silently into expected_version.
    expected_version: StrictInt = Field(...)


# ── HTTP status mapping ─────────────────────────────────────────────────────

# error_code → HTTP status. Codes not in this map → 200 with ok=false (the
# envelope itself carries the failure reason). This matches the 3.10 pattern
# where transport-class errors get HTTP status codes and domain errors flow
# through the JSON envelope.
_STATUS_BY_CODE = {
    "not_authenticated": 401,
    "forbidden":         403,
    "not_found":         404,
}


@router.post("/maya-actions/{suggestion_id}/execute")
async def execute_action(
    body: ExecuteRequest,
    suggestion_id: str = Path(..., min_length=1, max_length=64),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    # Reject booleans explicitly — pydantic treats bool as int by default.
    if isinstance(body.expected_version, bool):
        raise HTTPException(status_code=422, detail="invalid_input")

    user_jwt = await _verify_bearer(authorization)

    envelope = await execute_one(
        suggestion_id=suggestion_id,
        expected_version=body.expected_version,
        user_jwt=user_jwt,
    )

    if not isinstance(envelope, dict):
        # Defensive — execute_one is contracted to always return a dict
        logger.error("[maya-actions/execute] non-dict envelope from execute_one")
        raise HTTPException(status_code=500, detail="executor_invariant_violation")

    if envelope.get("ok") is True:
        return envelope

    code = envelope.get("error_code") or ""
    http_status = _STATUS_BY_CODE.get(code)
    if http_status is not None:
        # Surface the envelope at the mapped HTTP status. detail is a dict so
        # FastAPI returns it as JSON body.
        raise HTTPException(status_code=http_status, detail=envelope)
    return envelope

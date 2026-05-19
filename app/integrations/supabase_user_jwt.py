"""
app/integrations/supabase_user_jwt.py
=====================================
Helper for calling Supabase PostgREST RPCs with a verified user JWT.

Why this exists
---------------
SECURITY DEFINER RPCs that depend on `auth.uid()` and `public.maya_auth_client_id()`
must be invoked over a connection that carries the user's JWT. The rest of the
backend uses the service-role key for Supabase reads, which makes `auth.uid()`
NULL inside RPCs. For the Maya action executor (Phase 3.11), the claim and
finalize RPCs need the *caller's* identity to enforce tenant ownership — so
they must be reached through this helper, not through service-role.

Public API
----------
user_supabase_rpc(user_jwt, fn, params, *, timeout_s=5.0) -> dict
    Returns the RPC JSON envelope on 2xx, or a safe failure envelope on any
    other outcome. NEVER raises. NEVER logs or returns the JWT.

Security invariants
-------------------
- The JWT is read from the function argument, used once in the Authorization
  header, and not stored, logged, or returned.
- The service-role key is not read, not imported, not referenced.
- Returned `detail` strings are bounded to 500 chars and never contain
  the Authorization header value.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DETAIL_MAX_LEN = 500


def _bounded(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return text[:_DETAIL_MAX_LEN]


async def user_supabase_rpc(
    user_jwt: str,
    fn: str,
    params: dict,
    *,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Call a Supabase PostgREST RPC with the user's JWT.

    Inside the called RPC (SECURITY DEFINER):
      auth.uid()                    resolves to the JWT's `sub`
      public.maya_auth_client_id()  resolves to user_metadata.client_id

    Returns the RPC JSON envelope on HTTP 2xx, or a safe failure envelope
    on any other outcome.
    """
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")

    if not supabase_url or not supabase_anon_key:
        return {
            "ok": False,
            "error_code": "config_missing",
            "error_he": "תצורת Supabase חסרה.",
        }

    if not isinstance(user_jwt, str) or not user_jwt.strip():
        return {
            "ok": False,
            "error_code": "invalid_input",
            "error_he": "קלט לא תקין.",
        }

    if not isinstance(fn, str) or not fn.strip():
        return {
            "ok": False,
            "error_code": "invalid_input",
            "error_he": "קלט לא תקין.",
        }

    if not isinstance(params, dict):
        return {
            "ok": False,
            "error_code": "invalid_input",
            "error_he": "קלט לא תקין.",
        }

    url = f"{supabase_url.rstrip('/')}/rest/v1/rpc/{fn}"

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                url,
                headers={
                    "apikey":        supabase_anon_key,
                    "Authorization": f"Bearer {user_jwt}",
                    "Content-Type":  "application/json",
                },
                json=params,
            )
    except httpx.HTTPError as exc:
        logger.warning("[user_supabase_rpc] network error for fn=%s: %s",
                       fn, type(exc).__name__)
        return {
            "ok": False,
            "error_code": "supabase_rpc_network_error",
            "error_he": "לא ניתן להתחבר ל-Supabase.",
        }

    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
        except ValueError:
            return {
                "ok": False,
                "error_code": "supabase_rpc_error",
                "error_he": "פעולת Supabase נכשלה.",
                "status_code": resp.status_code,
                "detail": _bounded("non_json_success_body"),
            }
        if isinstance(data, dict):
            return data
        return {
            "ok": True,
            "data": data,
        }

    # Non-2xx. Bound the detail; never include the JWT or Authorization header.
    raw_body = ""
    try:
        raw_body = resp.text or ""
    except Exception:
        raw_body = ""
    return {
        "ok": False,
        "error_code": "supabase_rpc_error",
        "error_he": "פעולת Supabase נכשלה.",
        "status_code": resp.status_code,
        "detail": _bounded(raw_body),
    }

"""
app/services/client_assets.py
==============================
Supabase query service: resolve client_assets by trigger_key.

Public API
----------
get_assets_by_trigger(client_id, trigger_key) -> list[dict]
    Returns all enabled assets for a client + trigger, ordered by
    sort_order ASC, created_at ASC.  Never raises — returns [] on any failure.
"""

import os
import logging

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _is_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


def _headers() -> dict:
    return {
        "apikey":        _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
    }


async def get_assets_by_trigger(client_id: str, trigger_key: str) -> list[dict]:
    """
    Returns all enabled assets for client_id + trigger_key.
    Sorted by sort_order ASC, then created_at ASC.
    Returns [] on any error — never raises, never blocks the caller.
    """
    if not _is_configured():
        logger.warning("[ASSETS] Supabase not configured — skipping asset lookup")
        return []

    if not client_id or not trigger_key:
        logger.warning(
            "[ASSETS] get_assets_by_trigger called with empty client_id=%r or trigger_key=%r",
            client_id, trigger_key,
        )
        return []

    url = f"{_SUPABASE_URL}/rest/v1/client_assets"
    params = {
        "client_id":   f"eq.{client_id}",
        "trigger_key": f"eq.{trigger_key}",
        "enabled":     "eq.true",
        "order":       "sort_order.asc,created_at.asc",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params, headers=_headers())
            resp.raise_for_status()
            assets = resp.json()
            logger.info(
                "[ASSETS] Trigger '%s' → %d assets found for client %s",
                trigger_key, len(assets), client_id,
            )
            return assets
    except Exception as exc:
        logger.error(
            "[ASSETS] Error fetching assets for client %s: %s",
            client_id, exc,
        )
        return []

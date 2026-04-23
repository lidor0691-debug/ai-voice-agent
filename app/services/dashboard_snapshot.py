"""
Dashboard data service for assistant mode.

Provides:
- fetch_dashboard_snapshot(): initial context loaded on connect
- fetch_leads_detail(): live data for mid-conversation injection
- fetch_calls_detail(): live data for mid-conversation injection
- fetch_daily_summary(): combined summary for injection
"""

import os
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _is_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


# ── Snapshot (loaded once on connect) ────────────────────────────────────────

async def fetch_dashboard_snapshot(client_id: str | None) -> str:
    """
    Build a short text snapshot of current business state.
    Returns formatted string ready to inject into system prompt.
    """
    if not _is_configured():
        return "(אין חיבור לנתונים)"

    parts = []

    try:
        parts.append(await _snapshot_leads(client_id))
    except Exception as exc:
        logger.warning("[SNAPSHOT] leads query failed: %s", exc)

    try:
        parts.append(await _snapshot_calls(client_id))
    except Exception as exc:
        logger.warning("[SNAPSHOT] calls query failed: %s", exc)

    try:
        parts.append(await _snapshot_agents(client_id))
    except Exception as exc:
        logger.warning("[SNAPSHOT] agents query failed: %s", exc)

    return "\n".join(parts) if parts else "(אין נתונים זמינים)"


async def _snapshot_leads(client_id: str | None) -> str:
    """Top 5 recent leads with status."""
    params: dict = {
        "select": "name,phone,status,source,last_call_topic,last_call_at",
        "order": "last_call_at.desc.nullslast",
        "limit": "5",
    }
    if client_id:
        params["client_id"] = f"eq.{client_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/leads",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    _SOURCE_LABELS = {"voice": "שיחה", "whatsapp": "וואטסאפ", "browser_voice": "דשבורד", "web": "אתר"}
    new_count = sum(1 for r in rows if r.get("status") == "new")
    lines = [f"לידים: {len(rows)} אחרונים, {new_count} חדשים"]
    for r in rows[:3]:
        name = r.get("name") or r.get("phone") or "ללא שם"
        topic = r.get("last_call_topic") or ""
        status = r.get("status") or ""
        source = _SOURCE_LABELS.get(r.get("source", ""), r.get("source", ""))
        detail = f" — {topic}" if topic else ""
        src = f", מקור: {source}" if source else ""
        lines.append(f"  - {name} ({status}{src}){detail}")

    return "\n".join(lines)


async def _snapshot_calls(client_id: str | None) -> str:
    """Today's call count."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/call_logs",
            params={
                "select": "id,status",
                "created_at": f"gte.{today}",
            },
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    total = len(rows)
    completed = sum(1 for r in rows if r.get("status") == "completed")
    return f"שיחות היום: {total} ({completed} הושלמו)"


async def _snapshot_agents(client_id: str | None) -> str:
    """Active agents with names and IDs."""
    params: dict = {
        "select": "id,agent_name,phone_number",
        "is_active": "eq.true",
        "order": "created_at.desc",
    }
    if client_id:
        params["client_id"] = f"eq.{client_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/agents_config",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    lines = [f"סוכנים פעילים: {len(rows)}"]
    for r in rows:
        name = r.get("agent_name") or "ללא שם"
        agent_id = r.get("id") or ""
        phone = r.get("phone_number") or ""
        lines.append(f"  - {name} (id: {agent_id[:8]}..., טלפון: {phone})")
    return "\n".join(lines)


# ── Live data queries (for mid-conversation injection) ───────────────────────

async def fetch_leads_detail(client_id: str | None) -> str:
    """Top 5 leads with details — injected when user asks about leads."""
    if not _is_configured():
        return "אין חיבור לנתונים"

    params: dict = {
        "select": "name,phone,status,source,last_call_topic,last_call_at,notes",
        "order": "last_call_at.desc.nullslast",
        "limit": "5",
    }
    if client_id:
        params["client_id"] = f"eq.{client_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/leads",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        return "אין לידים כרגע"

    _SOURCE_LABELS = {"voice": "שיחה", "whatsapp": "וואטסאפ", "browser_voice": "דשבורד", "web": "אתר"}
    lines = ["=== לידים עדכניים ==="]
    for r in rows:
        name = r.get("name") or r.get("phone") or "ללא שם"
        status = r.get("status") or ""
        source = _SOURCE_LABELS.get(r.get("source", ""), r.get("source", ""))
        topic = r.get("last_call_topic") or ""
        notes = r.get("notes") or ""
        detail = topic or notes
        src = f", מקור: {source}" if source else ""
        lines.append(f"- {name} ({status}{src}): {detail[:60]}")
    return "\n".join(lines)


async def fetch_calls_detail(client_id: str | None) -> str:
    """Today's calls summary — injected when user asks about calls."""
    if not _is_configured():
        return "אין חיבור לנתונים"

    today = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/call_logs",
            params={
                "select": "id,status,created_at",
                "created_at": f"gte.{today}",
                "order": "created_at.desc",
                "limit": "10",
            },
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        return "אין שיחות היום"

    total = len(rows)
    completed = sum(1 for r in rows if r.get("status") == "completed")
    return f"=== שיחות היום ===\nסה\"כ: {total}, הושלמו: {completed}"


async def fetch_daily_summary(client_id: str | None) -> str:
    """Combined leads + calls — for 'what happened today' questions."""
    leads = await fetch_leads_detail(client_id)
    calls = await fetch_calls_detail(client_id)
    return f"{leads}\n\n{calls}"

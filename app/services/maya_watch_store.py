"""
Maya Watch — Supabase persistence layer.

Thin async store backed by the Supabase REST API (same httpx pattern as
app/services/attribution.py and app/services/agent_config.py — no new
deps, no Supabase Python client).

Two tables (created by supabase/migrations/create_maya_watch_tables.sql):
    public.maya_watch_leads     — per-phone state with denormalized
                                  latest-followup snapshot
    public.maya_watch_messages  — every inbound + outbound body, with
                                  delivery state on the outbound rows

Multi-tenant ready:
    client_id (uuid, nullable) and agent_id (text, nullable) are stored on
    every row. v0 leaves them null (single-client pre-routing). When tenant
    routing lands, callers pass real ids — no schema change required.

Public surface (all coroutines):
    upsert_lead(...)               — create-or-update lead row
    append_message(...)            — append one message (in/out)
    update_outbound_status(...)    — Twilio status_callback handler
    update_lead_followup(...)      — denormalize latest followup onto lead
    mark_booked(...)               — flip booked + booked_at
    get_all_leads_with_messages()  — list leads + their messages (one shot)
    get_lead_with_messages(phone)  — single lead lookup

All methods log + swallow errors with [MAYA-WATCH] prefix and return a
sensible falsy value, matching the resilience contract of the existing
service so a transient Supabase blip can't 500 the request path.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Supabase wiring (same env vars as the rest of the backend) ────────────
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_TABLE_LEADS = "maya_watch_leads"
_TABLE_MESSAGES = "maya_watch_messages"

_TIMEOUT = 5.0


def env_ready() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


def _headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _read_headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
    }


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ── Lead lookup ──────────────────────────────────────────────────────────


async def _find_lead_id(phone: str, client_id: Optional[str] = None) -> Optional[str]:
    """Return the leads.id (uuid) for a phone within a tenant scope, or None."""
    if not env_ready() or not phone:
        return None
    params: dict = {"phone": f"eq.{phone}", "select": "id", "limit": "1"}
    # Match the same coalesce semantics as the unique index: NULL client_id
    # behaves like the sentinel — Supabase REST has no easy coalesce filter,
    # so for v0 we just filter by phone (one row per phone is fine until
    # multi-tenant lands and adds client_id filtering).
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params=params,
                headers=_read_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
        if not rows:
            return None
        return rows[0].get("id")
    except Exception as exc:
        logger.warning("[MAYA-WATCH] lead lookup failed phone=%s: %s", phone, exc)
        return None


# ── Public API ───────────────────────────────────────────────────────────


async def upsert_lead(
    phone: str,
    *,
    name: Optional[str] = None,
    client_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Optional[str]:
    """
    Create the lead row if missing, otherwise patch name (only when blank).
    Returns the lead's uuid id, or None on failure.
    """
    if not env_ready() or not phone:
        return None
    existing_id = await _find_lead_id(phone, client_id)
    if existing_id:
        # Patch the name only if currently null — don't clobber a known name.
        if name:
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    await client.patch(
                        f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                        params={"id": f"eq.{existing_id}", "name": "is.null"},
                        json={"name": name},
                        headers=_headers("return=minimal"),
                    )
            except Exception as exc:
                logger.warning("[MAYA-WATCH] lead name patch failed id=%s: %s", existing_id, exc)
        return existing_id

    payload = {
        "phone": phone,
        "name": name,
        "client_id": client_id,
        "agent_id": agent_id,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                json=payload,
                headers=_headers("return=representation"),
            )
            resp.raise_for_status()
            rows = resp.json()
        if not rows:
            return None
        new_id = rows[0].get("id")
        logger.info("[MAYA-WATCH] lead inserted id=%s phone=%s", new_id, phone)
        return new_id
    except Exception as exc:
        logger.error("[MAYA-WATCH] lead insert failed phone=%s: %s", phone, exc)
        return None


async def append_message(
    phone: str,
    direction: str,
    body: str,
    *,
    ts: Optional[datetime] = None,
    sid: Optional[str] = None,
    client_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> bool:
    """Insert one in/out message row. Returns True on success."""
    if not env_ready() or not phone or direction not in ("in", "out"):
        return False
    lead_id = await upsert_lead(phone, client_id=client_id, agent_id=agent_id)
    if not lead_id:
        return False
    payload: dict[str, Any] = {
        "lead_id": lead_id,
        "client_id": client_id,
        "agent_id": agent_id,
        "direction": direction,
        "body": body,
        "ts": _iso(ts) if ts else None,
        "sid": sid,
    }
    # Drop None-valued ts so DB default (now()) kicks in.
    if payload["ts"] is None:
        del payload["ts"]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_MESSAGES}",
                json=payload,
                headers=_headers("return=minimal"),
            )
            resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("[MAYA-WATCH] message insert failed phone=%s dir=%s: %s", phone, direction, exc)
        return False


async def update_lead_followup(
    phone: str,
    *,
    sid: str,
    body: str,
    sent_at: datetime,
    status: str = "queued",
    client_id: Optional[str] = None,
) -> bool:
    """
    Patch the lead row's denormalized followup fields after _send_followup
    succeeds. Status is set to "queued" initially; the Twilio status callback
    progresses it via update_outbound_status.
    """
    if not env_ready() or not phone:
        return False
    lead_id = await _find_lead_id(phone, client_id)
    if not lead_id:
        logger.warning("[MAYA-WATCH] update_lead_followup: lead not found phone=%s", phone)
        return False
    payload = {
        "followup_sid": sid,
        "followup_body": body,
        "followup_sent_at": _iso(sent_at),
        "followup_status": status,
        "followup_status_at": _iso(sent_at),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params={"id": f"eq.{lead_id}"},
                json=payload,
                headers=_headers("return=minimal"),
            )
            resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("[MAYA-WATCH] followup patch failed phone=%s: %s", phone, exc)
        return False


async def update_outbound_status(
    sid: str,
    status: str,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> bool:
    """
    Twilio status_callback handler. Updates the matching outbound message
    row AND mirrors the latest state onto the parent lead row's
    denormalized followup_* fields. Returns True if a matching row was
    updated, False if the SID is unknown (orphan callback).
    """
    if not env_ready() or not sid:
        return False
    now = datetime.now(timezone.utc)
    msg_payload = {
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
        "status_at": _iso(now),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Update the message row by SID, ask for the lead_id back.
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_MESSAGES}",
                params={"sid": f"eq.{sid}", "select": "lead_id"},
                json=msg_payload,
                headers=_headers("return=representation"),
            )
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                logger.warning("[MAYA-WATCH] orphan status_callback sid=%s status=%s", sid, status)
                return False
            lead_id = rows[0].get("lead_id")

            # Mirror latest state onto the lead row only if THIS sid is the
            # one currently denormalized — avoids out-of-order callbacks
            # for older sids overwriting newer state.
            lead_payload = {
                "followup_status": status,
                "followup_error_code": error_code,
                "followup_error_message": error_message,
                "followup_status_at": _iso(now),
            }
            await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params={"id": f"eq.{lead_id}", "followup_sid": f"eq.{sid}"},
                json=lead_payload,
                headers=_headers("return=minimal"),
            )
        logger.info(
            "[MAYA-WATCH] delivery_update_persisted sid=%s status=%s error_code=%s",
            sid, status, error_code or "-",
        )
        return True
    except Exception as exc:
        logger.error("[MAYA-WATCH] status_callback persist failed sid=%s: %s", sid, exc)
        return False


async def mark_booked(phone: str, *, client_id: Optional[str] = None) -> bool:
    """Set booked=true and booked_at=now() on the lead row."""
    if not env_ready() or not phone:
        return False
    lead_id = await _find_lead_id(phone, client_id)
    if not lead_id:
        return False
    payload = {"booked": True, "booked_at": _iso(datetime.now(timezone.utc))}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params={"id": f"eq.{lead_id}"},
                json=payload,
                headers=_headers("return=minimal"),
            )
            resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("[MAYA-WATCH] mark_booked failed phone=%s: %s", phone, exc)
        return False


async def get_all_leads_with_messages(
    client_id: Optional[str] = None,
) -> list[dict]:
    """
    Return all leads (for the tenant scope, NULL = no scope filter for v0)
    each augmented with `messages: list[dict]` chronologically.

    Each lead dict matches the `maya_watch_leads` row schema. Each message
    dict matches the `maya_watch_messages` row schema. The caller (service
    layer) reconstructs Lead/Message dataclasses for compatibility.

    On failure returns an empty list — callers should treat that as
    "no data right now" rather than an error.
    """
    if not env_ready():
        return []
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            leads_params: dict = {"select": "*", "order": "created_at.asc"}
            if client_id is not None:
                leads_params["client_id"] = f"eq.{client_id}"
            leads_resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params=leads_params,
                headers=_read_headers(),
            )
            leads_resp.raise_for_status()
            leads = leads_resp.json()
            if not leads:
                return []

            lead_ids = [l["id"] for l in leads]
            # PostgREST `in` filter: in.(id1,id2,...)
            in_filter = "in.(" + ",".join(lead_ids) + ")"
            msgs_resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_MESSAGES}",
                params={
                    "lead_id": in_filter,
                    "select": "*",
                    "order": "ts.asc",
                },
                headers=_read_headers(),
            )
            msgs_resp.raise_for_status()
            messages = msgs_resp.json()

        by_lead: dict[str, list[dict]] = {}
        for m in messages:
            by_lead.setdefault(m["lead_id"], []).append(m)
        for l in leads:
            l["messages"] = by_lead.get(l["id"], [])
        return leads
    except Exception as exc:
        logger.error("[MAYA-WATCH] get_all_leads_with_messages failed: %s", exc)
        return []


async def get_lead_with_messages(
    phone: str,
    client_id: Optional[str] = None,
) -> Optional[dict]:
    """Single-lead variant of get_all_leads_with_messages by phone."""
    if not env_ready() or not phone:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            leads_resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params={"phone": f"eq.{phone}", "select": "*", "limit": "1"},
                headers=_read_headers(),
            )
            leads_resp.raise_for_status()
            leads = leads_resp.json()
            if not leads:
                return None
            lead = leads[0]
            msgs_resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_MESSAGES}",
                params={
                    "lead_id": f"eq.{lead['id']}",
                    "select": "*",
                    "order": "ts.asc",
                },
                headers=_read_headers(),
            )
            msgs_resp.raise_for_status()
            lead["messages"] = msgs_resp.json()
        return lead
    except Exception as exc:
        logger.error("[MAYA-WATCH] get_lead_with_messages failed phone=%s: %s", phone, exc)
        return None

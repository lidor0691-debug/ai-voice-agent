"""Supabase data adapter for the studio assistant. DORMANT (PR2).

Thin async layer over the Supabase REST API (PostgREST), using the same env
vars + httpx pattern as app/services/maya_watch_store.py — no Supabase Python
client, no new runtime deps. Errors are logged and swallowed; reads return a
sensible falsy value so a transient blip can't crash a caller.

Nothing in the running service imports this module yet. There is no route, no
scheduler, no Twilio/Telegram/Make here. Backend writes assume the service-role
key (BYPASSRLS).

All HTTP goes through the single private `_rest_request` coroutine, which is the
seam unit tests monkeypatch with seeded rows (no live DB).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

import httpx

from app.assistant.nlp.contract import Contact, MessageType, ParsedIntent, RecipientType
from app.assistant.nlp.resolver import ResolvedPlan, resolve_send_plan

logger = logging.getLogger(__name__)

# ── Supabase wiring (same env vars as the rest of the backend) ────────────────
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

TABLE_CONTACTS = "assistant_contacts"
TABLE_TEMPLATES = "assistant_message_templates"
TABLE_SCHEDULED = "assistant_scheduled_messages"
TABLE_ACTIVITY = "assistant_activity_log"
TABLE_CLARIFICATIONS = "assistant_pending_clarifications"

_TIMEOUT = 5.0
_WINDOW = timedelta(hours=24)
_TZ = ZoneInfo("Asia/Jerusalem")  # studio-local timezone for scheduled_at


def env_ready() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


def _headers(prefer: str = "return=representation") -> Dict[str, str]:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _local_to_utc_iso(local_iso: Optional[str]) -> Optional[str]:
    """Convert an Asia/Jerusalem wall-clock ISO string to a correct UTC instant.

    ``intent.scheduled_at_local`` is a NAIVE local wall-clock value (e.g.
    "2026-06-30T10:00:00" = 10:00 in Israel). The ``scheduled_at`` column is
    ``timestamptz``; writing a naive value lets Postgres assume UTC, shifting it
    by the IDT/IST offset. Here we attach the Asia/Jerusalem zone (DST-aware)
    and convert to UTC so the stored instant is correct:

        "2026-06-30T10:00:00" (IDT, +03) -> "2026-06-30T07:00:00+00:00"
        "2026-01-15T10:00:00" (IST, +02) -> "2026-01-15T08:00:00+00:00"

    None/empty -> None. An already tz-aware string is converted to UTC as-is
    (never double-localized).
    """
    if not local_iso:
        return None
    try:
        dt = datetime.fromisoformat(local_iso)
    except ValueError:
        return local_iso  # leave unparseable values untouched (fail safe)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ)
    return dt.astimezone(timezone.utc).isoformat()


async def _rest_request(
    method: str,
    table: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Any] = None,
    prefer: str = "return=representation",
) -> Optional[List[dict]]:
    """Single HTTP seam to PostgREST. Returns the parsed rows, or None on error.

    Unit tests monkeypatch this coroutine to serve seeded rows without a DB.
    """
    if not env_ready():
        return None
    url = f"{_SUPABASE_URL}/rest/v1/{table}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(
                method, url, params=params, json=json, headers=_headers(prefer)
            )
            resp.raise_for_status()
            if resp.content:
                data = resp.json()
                return data if isinstance(data, list) else [data]
            return []
    except Exception as exc:  # noqa: BLE001 — resilience contract: log + swallow
        logger.warning("[ASSISTANT-DATA] %s %s failed: %s", method, table, exc)
        return None


# ── row mappers ───────────────────────────────────────────────────────────────

def _row_to_contact(row: dict) -> Contact:
    return Contact(
        name=row["name"],
        recipient_type=RecipientType(row["recipient_type"]),
        phone=row.get("phone"),
    )


def within_24h_window(
    last_inbound_at: Optional[Any], *, now: Optional[datetime] = None
) -> bool:
    """True if the contact's last inbound message is within the WhatsApp 24h window.

    Accepts a datetime, an ISO string, or None (no inbound -> outside window).
    `now` is injectable for deterministic tests; defaults to UTC now.
    """
    if last_inbound_at is None:
        return False
    if isinstance(last_inbound_at, str):
        try:
            ts = datetime.fromisoformat(last_inbound_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    elif isinstance(last_inbound_at, datetime):
        ts = last_inbound_at
    else:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current - ts) < _WINDOW


# ── reads ───────────────────────────────────────────────────────────────────

async def _get_contact_row(owner_id: str, name: Optional[str]) -> Optional[dict]:
    if not name:
        return None
    rows = await _rest_request(
        "GET",
        TABLE_CONTACTS,
        params={
            "owner_id": f"eq.{owner_id}",
            "name": f"eq.{name}",
            "status": "eq.active",
            "select": "*",
            "limit": "1",
        },
    )
    if not rows:
        return None
    return rows[0]


async def get_contact_by_name(owner_id: str, name: Optional[str]) -> Optional[Contact]:
    row = await _get_contact_row(owner_id, name)
    return _row_to_contact(row) if row else None


async def resolve_contact_candidates(
    owner_id: str,
    recipient_raw: Optional[str],
    recipient_type_hint: Optional[Any] = None,
) -> List[dict]:
    """Return all active contacts matching ``recipient_raw`` for an owner.

    DB-driven recipient resolution. Matching is owner-scoped, exact on ``name``
    (deterministic), active-only, optionally narrowed by ``recipient_type_hint``
    (a RecipientType or its string value). The caller decides:
      * 0 candidates  -> unknown recipient
      * 1 candidate   -> proceed to resolve_send_plan
      * 2+ candidates -> ambiguous recipient
    Each candidate dict carries: id, name, recipient_type, phone, last_inbound_at.
    """
    if not recipient_raw:
        return []
    params: Dict[str, Any] = {
        "owner_id": f"eq.{owner_id}",
        "name": f"eq.{recipient_raw}",
        "status": "eq.active",
        "select": "id,name,recipient_type,phone,last_inbound_at",
    }
    if recipient_type_hint is not None:
        hint = (
            recipient_type_hint.value
            if isinstance(recipient_type_hint, RecipientType)
            else str(recipient_type_hint)
        )
        params["recipient_type"] = f"eq.{hint}"
    rows = await _rest_request("GET", TABLE_CONTACTS, params=params)
    return list(rows or ())


async def list_active_templates(owner_id: str) -> Set[MessageType]:
    rows = await _rest_request(
        "GET",
        TABLE_TEMPLATES,
        params={
            "owner_id": f"eq.{owner_id}",
            "status": "eq.active",
            "select": "message_type",
        },
    )
    result: Set[MessageType] = set()
    for r in rows or ():
        try:
            result.add(MessageType(r["message_type"]))
        except (KeyError, ValueError):
            continue
    return result


# ── Stage-2 resolver seam (injects real data into the pure resolver) ──────────

async def resolve_with_data(
    intent: ParsedIntent, owner_id: str, *, now: Optional[datetime] = None
) -> ResolvedPlan:
    """Fetch contact + window + active templates, then call the pure resolver.

    The resolver itself imports no data source; this is the only DB-touching
    seam. Returns the ResolvedPlan (resolver handles a missing contact ->
    manual_fallback).
    """
    row = await _get_contact_row(owner_id, intent.recipient_name)
    contact = _row_to_contact(row) if row else None
    window = within_24h_window(row.get("last_inbound_at") if row else None, now=now)
    templates = await list_active_templates(owner_id)
    return resolve_send_plan(
        intent, contact, within_24h_window=window, active_templates=templates
    )


# ── writes (service-role path; dormant — not called by any route in PR2) ──────

async def insert_scheduled_message(
    owner_id: str,
    intent: ParsedIntent,
    *,
    raw_command: Optional[str] = None,
    contact_id: Optional[str] = None,
    send_plan: Optional[str] = None,
    status: str = "needs_clarification",
    body: Optional[str] = None,
    parsed_intent: Optional[dict] = None,
) -> Optional[str]:
    """Persist a parsed intent as a scheduled-message row. Returns the new id.

    ``raw_command`` is the original natural-language command; when omitted it
    falls back to ``intent.body`` for backward compatibility. ``parsed_intent``
    is an optional JSON-safe snapshot stored in the ``parsed_intent`` column.
    """
    payload = {
        "owner_id": owner_id,
        "contact_id": contact_id,
        "recipient_type": intent.recipient_type.value if intent.recipient_type else None,
        "message_type": intent.message_type.value if intent.message_type else None,
        "raw_command": raw_command if raw_command is not None else (intent.body or ""),
        "scheduled_at": _local_to_utc_iso(intent.scheduled_at_local),
        "is_explicit_time": intent.is_explicit_time,
        "related_event_date": intent.related_event_date,
        "send_plan": send_plan,
        "status": status,
        "body": body,
        "parsed_intent": parsed_intent,
        "inferred_notes": intent.inferred_notes or None,
    }
    rows = await _rest_request("POST", TABLE_SCHEDULED, json=payload)
    if not rows:
        return None
    return rows[0].get("id")


async def update_scheduled_status(
    message_id: str,
    status: str,
    *,
    approval_requested_at: Optional[datetime] = None,
    approval_expires_at: Optional[datetime] = None,
    approved_at: Optional[datetime] = None,
    sent_at: Optional[datetime] = None,
) -> bool:
    """Patch a scheduled-message row's status (+ optional approval timestamps)."""
    patch: Dict[str, Any] = {"status": status}
    if approval_requested_at is not None:
        patch["approval_requested_at"] = _iso(approval_requested_at)
    if approval_expires_at is not None:
        patch["approval_expires_at"] = _iso(approval_expires_at)
    if approved_at is not None:
        patch["approved_at"] = _iso(approved_at)
    if sent_at is not None:
        patch["sent_at"] = _iso(sent_at)
    rows = await _rest_request(
        "PATCH",
        TABLE_SCHEDULED,
        params={"id": f"eq.{message_id}"},
        json=patch,
        prefer="return=minimal",
    )
    return rows is not None


async def insert_pending_clarification(
    owner_id: str,
    raw_command: str,
    clarification_prompt: str,
    clarification_type: str,
    *,
    scheduled_message_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> Optional[str]:
    """Persist an open clarification (missing/unknown/ambiguous). Returns new id."""
    payload = {
        "owner_id": owner_id,
        "scheduled_message_id": scheduled_message_id,
        "raw_command": raw_command,
        "clarification_prompt": clarification_prompt,
        "clarification_type": clarification_type,
        "status": "open",
        "resolved_payload": detail,
    }
    rows = await _rest_request("POST", TABLE_CLARIFICATIONS, json=payload)
    if not rows:
        return None
    return rows[0].get("id")


async def log_activity(
    owner_id: str,
    event_type: str,
    *,
    scheduled_message_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> bool:
    """Append one row to the activity log."""
    payload = {
        "owner_id": owner_id,
        "scheduled_message_id": scheduled_message_id,
        "contact_id": contact_id,
        "event_type": event_type,
        "detail": detail or {},
    }
    rows = await _rest_request(
        "POST", TABLE_ACTIVITY, json=payload, prefer="return=minimal"
    )
    return rows is not None

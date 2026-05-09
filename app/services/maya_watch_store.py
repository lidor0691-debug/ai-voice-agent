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
_TABLE_ACTIONS = "maya_watch_actions"

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
    """
    Return the leads.id (uuid) for a phone within a tenant scope, or None.

    Tenant scoping (Stage 4): when `client_id` is provided, filter on it so
    upserts don't accidentally find another tenant's lead with the same
    phone. When `client_id` is None, match rows where client_id is null
    (the legacy single-tenant pre-Stage-4 path).
    """
    if not env_ready() or not phone:
        return None
    params: dict = {"phone": f"eq.{phone}", "select": "id", "limit": "1"}
    if client_id is not None:
        params["client_id"] = f"eq.{client_id}"
    else:
        params["client_id"] = "is.null"
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
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> bool:
    """Insert one in/out message row. Returns True on success.

    `source` (Stage 10C-1): identifies which writer produced this row.
    'followup' for Maya's auto-followup; 'operator_preview' for the
    operator-driven send endpoint (Stage 10C-2). NULL for legacy rows
    (treated as 'followup' by status-callback mirror logic — the only
    existing writer of direction='out' rows pre-10C-1 was _send_followup).

    `metadata` (Stage 10C-2): jsonb passthrough. The operator-send path
    populates {idempotency_key, decision_id, sent_by} via the dedicated
    insert_outbound_message helper; this kwarg keeps append_message
    consistent for any future inbound or test path that needs to attach
    metadata at insert time.
    """
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
        "source": source,
        "metadata": metadata if metadata is not None else {},
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
            # Update the message row by SID, ask for the lead_id + source back.
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_MESSAGES}",
                params={"sid": f"eq.{sid}", "select": "lead_id,source"},
                json=msg_payload,
                headers=_headers("return=representation"),
            )
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                logger.warning("[MAYA-WATCH] orphan status_callback sid=%s status=%s", sid, status)
                return False
            lead_id = rows[0].get("lead_id")
            row_source = rows[0].get("source")

            # Stage 10C-1 — gate the lead-followup mirror on source. Operator
            # sends ('operator_preview' and any future operator source) update
            # only their own message row, never the lead's denormalized
            # followup snapshot. Legacy NULL source mirrors (the only pre-
            # 10C-1 writer of direction='out' was _send_followup, so NULL is
            # semantically 'followup').
            #
            # Belt + suspenders: the existing `followup_sid: eq.{sid}` filter
            # below ALSO prevents operator-send pollution (operator sids
            # never match lead.followup_sid). Two layers of defense — a
            # future change to either alone still leaves the other intact.
            if row_source not in ("followup", None):
                logger.info(
                    "[MAYA-WATCH] mirror_skipped sid=%s source=%s — operator-send, lead followup_* preserved",
                    sid, row_source,
                )
            else:
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
    """Single-lead variant of get_all_leads_with_messages by phone.

    Tenant scoping: when client_id is provided, only returns the lead if it
    belongs to that tenant. When client_id is None, returns any lead with
    that phone (admin lookup; never shown directly to a client).
    """
    if not env_ready() or not phone:
        return None
    leads_params: dict = {"phone": f"eq.{phone}", "select": "*", "limit": "1"}
    if client_id is not None:
        leads_params["client_id"] = f"eq.{client_id}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            leads_resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params=leads_params,
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


# ── Operator actions (Stage 7) ───────────────────────────────────────────
# These helpers back the maya_watch_actions table (added by
# supabase/migrations/create_maya_watch_actions.sql). They are intentionally
# inert until the migration is applied — every failure path returns a
# falsy/empty value so the rest of Maya Watch keeps working unchanged.
# v0 callers are not yet wired (route + briefing suppression land in PR 3).


async def record_action(
    *,
    lead_id: str,
    phone: str,
    decision_status: str,
    client_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    action_type: str = "acted",
    acted_by: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Insert one operator-action row, or return the existing row when the
    unique constraint (lead_id, decision_status, action_type) already
    matches — same observable result for repeat callers.

    Returns the row dict on success, with an extra `already_acted` boolean
    indicating whether this call inserted a new row (False) or matched an
    existing one (True). Returns None on any failure (missing env, table
    not yet present, network/Supabase error) so the route layer can stay
    a thin pass-through without crashing the request path.
    """
    if not env_ready() or not lead_id or not phone or not decision_status:
        return None
    payload: dict[str, Any] = {
        "lead_id": lead_id,
        "client_id": client_id,
        "agent_id": agent_id,
        "phone": phone,
        "decision_status": decision_status,
        "action_type": action_type,
        "acted_by": acted_by,
        "metadata": metadata if metadata is not None else {},
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_ACTIONS}",
                json=payload,
                headers=_headers("return=representation"),
            )
            # PostgREST returns 409 on a unique-constraint violation. Fetch
            # the existing row and return it so the caller can stay
            # idempotent without inspecting status codes.
            if resp.status_code == 409:
                existing = await client.get(
                    f"{_SUPABASE_URL}/rest/v1/{_TABLE_ACTIONS}",
                    params={
                        "lead_id": f"eq.{lead_id}",
                        "decision_status": f"eq.{decision_status}",
                        "action_type": f"eq.{action_type}",
                        "select": "*",
                        "limit": "1",
                    },
                    headers=_read_headers(),
                )
                existing.raise_for_status()
                rows = existing.json()
                if not rows:
                    logger.warning(
                        "[MAYA-WATCH] record_action 409 but no matching row lead_id=%s status=%s",
                        lead_id, decision_status,
                    )
                    return None
                row = rows[0]
                row["already_acted"] = True
                logger.info(
                    "[MAYA-WATCH] record_action idempotent lead_id=%s status=%s action_id=%s",
                    lead_id, decision_status, row.get("id"),
                )
                return row

            resp.raise_for_status()
            rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        row["already_acted"] = False
        logger.info(
            "[MAYA-WATCH] record_action inserted lead_id=%s status=%s action_id=%s",
            lead_id, decision_status, row.get("id"),
        )
        return row
    except Exception as exc:
        logger.error(
            "[MAYA-WATCH] record_action failed lead_id=%s status=%s: %s",
            lead_id, decision_status, exc,
        )
        return None


def _filter_active_acted_keys(rows: list[dict]) -> set[tuple[str, str, str]]:
    """
    Pure helper. Given rows of {lead_id, decision_status, action_type},
    return the set of (lead_id, decision_status, 'acted') triples that are
    currently *active* — i.e. an 'acted' row exists and no corresponding
    'undone' row exists for the same (lead_id, decision_status).

    Stage 8C — separates the row-grouping logic from the network call so it
    can be unit-tested with deterministic inputs.
    """
    types_by_pair: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        lead_id = r.get("lead_id")
        status = r.get("decision_status")
        atype = r.get("action_type")
        if not (lead_id and status and atype):
            continue
        types_by_pair.setdefault((lead_id, status), set()).add(atype)
    keys: set[tuple[str, str, str]] = set()
    for (lead_id, status), atypes in types_by_pair.items():
        if "acted" in atypes and "undone" not in atypes:
            keys.add((lead_id, status, "acted"))
    return keys


async def list_acted_keys(
    client_id: Optional[str] = None,
) -> set[tuple[str, str, str]]:
    """
    Return the suppression-key set for the briefing.

    A key (lead_id, decision_status, 'acted') is included when an 'acted'
    row exists AND no 'undone' row exists for the same (lead_id, status).
    Stage 8C — undone rows reactivate suppressed decisions: they remove
    the matching key from the returned set so build_briefing's existing
    `if (lead_id, status, "acted") in acted_keys: continue` check resumes
    surfacing the decision as open work.

    Fail-safe: returns an empty set on any failure — missing table, missing
    env, network/Supabase blip. An empty set is identical to pre-Stage-7
    no-suppression behavior; briefing keeps working.
    """
    if not env_ready():
        return set()
    params: dict = {"select": "lead_id,decision_status,action_type"}
    if client_id is not None:
        params["client_id"] = f"eq.{client_id}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_ACTIONS}",
                params=params,
                headers=_read_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
        return _filter_active_acted_keys(rows)
    except Exception as exc:
        logger.warning("[MAYA-WATCH] list_acted_keys failed: %s", exc)
        return set()


# ── Activity feedback (Stage 8B) ─────────────────────────────────────────
# Operator activity summary — distinct from `counts` (lead reality).
# Reads the same maya_watch_actions table but with a date filter so the
# briefing can surface "טיפלת היום: N לידים".


def _utc_today_iso() -> str:
    """Start of the current day in UTC, ISO-formatted for PostgREST.

    v0 caveat: this uses UTC, not the operator's local timezone. An action
    recorded at 22:00 IST drops out of "today" at 02:00 IST when UTC rolls
    over. Acceptable for v0; revisit with a client-supplied `since` ISO if
    the misalignment becomes a friction point.
    """
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.isoformat()


def _filter_active_acted_today(rows: list[dict], limit: int) -> dict:
    """
    Pure helper. Given today's action rows (BOTH 'acted' and 'undone',
    fetched without an action_type filter), return the count + recent
    list of 'acted' rows whose (lead_id, decision_status) does NOT have
    a corresponding 'undone' row in today's window.

    Stage 8C — when an acted-today is undone-today, it's removed from
    handled_today entirely (count drops, doesn't appear in recent). The
    audit history still has both rows in the table.

    `rows` must already be ordered by acted_at desc; the input function
    requests this from PostgREST.
    """
    undone_pairs: set[tuple[str, str]] = {
        (r["lead_id"], r["decision_status"])
        for r in rows
        if r.get("action_type") == "undone"
        and r.get("lead_id") and r.get("decision_status")
    }
    acted_active: list[dict] = [
        r for r in rows
        if r.get("action_type") == "acted"
        and (r.get("lead_id"), r.get("decision_status")) not in undone_pairs
    ]
    return {"count": len(acted_active), "recent": acted_active[:limit]}


async def get_handled_today(
    client_id: Optional[str] = None,
    limit: int = 3,
) -> dict:
    """
    Return a summary of operator actions recorded today (UTC) that are
    still "active" — acted-and-not-undone within today's window.

    Shape:
        {
            "count": int,           # acted-not-undone today within scope
            "recent": list[dict],   # up to `limit`, ordered by acted_at desc
                                    #   each item: {lead_id, phone,
                                    #               decision_status,
                                    #               action_type, acted_at}
        }

    Stage 8C — when the operator undoes a same-day action, both the count
    and the recent row drop immediately. The audit history (both rows)
    persists in the table for analytics and auditing later.

    Tenant scope: when client_id is provided, filters to that tenant.
    When None, aggregates across all tenants (admin view).

    Fail-safe: returns {"count": 0, "recent": []} on any error.

    Note: lead_name is NOT resolved here. The service layer joins it from
    the leads dict it already loaded for the briefing.
    """
    empty: dict = {"count": 0, "recent": []}
    if not env_ready() or limit < 0:
        return empty
    # Stage 8C — drop the action_type filter so we see both 'acted' and
    # 'undone' rows in today's window. The pure helper does the grouping.
    params: dict = {
        "acted_at": f"gte.{_utc_today_iso()}",
        "select": "lead_id,phone,decision_status,action_type,acted_at",
        "order": "acted_at.desc",
    }
    if client_id is not None:
        params["client_id"] = f"eq.{client_id}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_ACTIONS}",
                params=params,
                headers=_read_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
        return _filter_active_acted_today(rows, limit)
    except Exception as exc:
        logger.warning("[MAYA-WATCH] get_handled_today failed: %s", exc)
        return empty


# ── Undo (Stage 8C) ──────────────────────────────────────────────────────
# Undo is recorded as a NEW row with action_type='undone' for the same
# (lead_id, decision_status). The original 'acted' row is preserved for
# audit. Suppression and handled_today both check for the presence of an
# 'undone' row to flip the decision back to "open".
#
# v0 limitation: the unique index (lead_id, decision_status, action_type)
# means re-acting after undo for the same triple is blocked. The lead's
# status must change first (creating a new triple). Documented in the PR.


async def find_action_id(
    *,
    lead_id: str,
    decision_status: str,
    action_type: str,
) -> Optional[str]:
    """
    Look up the id of the matching action row, or None.

    Used by record_undone to confirm there's an 'acted' row to undo before
    inserting the 'undone' row, and to populate metadata.undid_action_id
    for audit linkage.
    """
    if not env_ready() or not lead_id or not decision_status or not action_type:
        return None
    params = {
        "lead_id": f"eq.{lead_id}",
        "decision_status": f"eq.{decision_status}",
        "action_type": f"eq.{action_type}",
        "select": "id",
        "limit": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_ACTIONS}",
                params=params,
                headers=_read_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
        if not rows:
            return None
        return rows[0].get("id")
    except Exception as exc:
        logger.warning(
            "[MAYA-WATCH] find_action_id failed lead_id=%s status=%s type=%s: %s",
            lead_id, decision_status, action_type, exc,
        )
        return None


async def record_undone(
    *,
    lead_id: str,
    phone: str,
    decision_status: str,
    client_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    acted_by: Optional[str] = None,
) -> dict:
    """
    Insert an 'undone' action row for (lead_id, decision_status).

    Returns a discriminated dict so the route layer can pick the right
    HTTP status:
        {
            "found_acted":    bool,  # was there an 'acted' row to undo?
            "ok":             bool,  # did the undo write succeed?
            "already_undone": bool,  # was an 'undone' row already there?
            "row":            dict | None,  # the undone row when ok=True
        }

    Resolution table for the route:
        found_acted=False             → 404 "no prior acted row to undo"
        found_acted=True, ok=False    → 500 "failed to record undo"
        found_acted=True, ok=True     → 200 with row + already_undone

    Audit linkage: metadata.undid_action_id = uuid of the original 'acted'
    row. Idempotency comes for free from the unique index
    (lead_id, decision_status, action_type) — second click hits 409 and
    record_action's existing fetch path returns the existing row.
    """
    result: dict = {"found_acted": False, "ok": False, "already_undone": False, "row": None}
    if not env_ready() or not lead_id or not phone or not decision_status:
        return result

    # Step 1 — confirm there's an acted row to undo, and grab its id for audit linkage.
    acted_id = await find_action_id(
        lead_id=lead_id,
        decision_status=decision_status,
        action_type="acted",
    )
    if not acted_id:
        # Nothing to undo. Caller surfaces as 404.
        return result
    result["found_acted"] = True

    # Step 2 — reuse record_action's insert + 409-idempotency path.
    inserted = await record_action(
        lead_id=lead_id,
        phone=phone,
        decision_status=decision_status,
        client_id=client_id,
        agent_id=agent_id,
        action_type="undone",
        acted_by=acted_by,
        metadata={"undid_action_id": acted_id},
    )
    if inserted is None:
        # DB error during insert. Caller surfaces as 500.
        return result

    result["ok"] = True
    # Translate the action-side flag name for clarity at the API surface.
    result["already_undone"] = bool(inserted.pop("already_acted", False))
    result["row"] = inserted
    return result


# ── Operator-send helpers (Stage 10C-2) ──────────────────────────────────
# Lookups + dedicated outbound insert used by maya_watch.send_operator_whatsapp.
# Kept here to centralize all DB access in one module.


async def get_lead_by_id(
    lead_id: str,
    *,
    client_id: Optional[str] = None,
) -> Optional[dict]:
    """Fetch a maya_watch_leads row by uuid, optionally tenant-scoped.

    Returns {id, phone, client_id, agent_id} or None when the row doesn't
    exist OR (when client_id is provided) the row exists but belongs to a
    different tenant. The 404 vs cross-tenant distinction is intentionally
    collapsed into None — the route layer surfaces both as 404
    `lead_not_found` so cross-tenant existence isn't leaked.
    """
    if not env_ready() or not lead_id:
        return None
    params: dict = {
        "id": f"eq.{lead_id}",
        "select": "id,phone,client_id,agent_id",
        "limit": "1",
    }
    if client_id is not None:
        params["client_id"] = f"eq.{client_id}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params=params,
                headers=_read_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("[MAYA-WATCH] get_lead_by_id failed lead_id=%s: %s", lead_id, exc)
        return None


async def get_last_inbound_ts(lead_id: str) -> Optional[datetime]:
    """Latest inbound message timestamp for the lead, or None.

    Used by send_operator_whatsapp to validate the WhatsApp 24h customer
    service window. Maya Watch's own table is the source of truth — does
    NOT consult the legacy `leads.last_whatsapp_inbound_at` column which
    has a documented tenant-leak issue.

    Indexed by `idx_maya_watch_messages_lead (lead_id, ts desc)` —
    single-row lookup, sub-millisecond.
    """
    if not env_ready() or not lead_id:
        return None
    params = {
        "lead_id": f"eq.{lead_id}",
        "direction": "eq.in",
        "select": "ts",
        "order": "ts.desc",
        "limit": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_MESSAGES}",
                params=params,
                headers=_read_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
        if not rows:
            return None
        ts_str = rows[0].get("ts")
        if not ts_str:
            return None
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except Exception as exc:
        logger.warning("[MAYA-WATCH] get_last_inbound_ts failed lead_id=%s: %s", lead_id, exc)
        return None


async def find_message_by_idempotency_key(key: str) -> Optional[dict]:
    """Lookup an existing outbound message by metadata.idempotency_key.

    Hits the unique partial index `idx_maya_watch_messages_idempotency`
    (Stage 10C-2 made it UNIQUE). Returns the full message row dict or
    None when no row matches.

    Used by send_operator_whatsapp BEFORE calling Twilio to short-circuit
    duplicate sends, AND after a 409 conflict during insert to fetch the
    race-winner row.
    """
    if not env_ready() or not key:
        return None
    params = {
        "metadata->>idempotency_key": f"eq.{key}",
        "select": "id,lead_id,client_id,agent_id,direction,body,sid,status,ts,source,metadata",
        "limit": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_MESSAGES}",
                params=params,
                headers=_read_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("[MAYA-WATCH] find_message_by_idempotency_key failed key=%s: %s", key, exc)
        return None


async def insert_outbound_message(
    *,
    lead_id: str,
    client_id: Optional[str],
    agent_id: Optional[str],
    body: str,
    sid: str,
    source: str,
    status: str = "queued",
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """Direct outbound message insert that bypasses upsert_lead.

    Returns the inserted row dict on success. Returns the sentinel
    {"_conflict": True} when the unique idempotency index rejects the
    insert (concurrent same-key race) — caller should re-fetch via
    find_message_by_idempotency_key. Returns None on any other failure.

    Used by send_operator_whatsapp where the lead_id is already resolved
    upstream; avoids the redundant phone-based lookup that
    append_message → upsert_lead would do.
    """
    if not env_ready() or not lead_id or not body:
        return None
    payload: dict[str, Any] = {
        "lead_id": lead_id,
        "client_id": client_id,
        "agent_id": agent_id,
        "direction": "out",
        "body": body,
        "sid": sid,
        "source": source,
        "status": status,
        "metadata": metadata if metadata is not None else {},
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_MESSAGES}",
                json=payload,
                headers=_headers("return=representation"),
            )
            if resp.status_code == 409:
                # Concurrent same-idempotency-key race — second writer
                # gets here. Caller re-fetches the winning row.
                logger.info(
                    "[MAYA-WATCH] insert_outbound_message conflict lead_id=%s sid=%s — likely idempotency race",
                    lead_id, sid,
                )
                return {"_conflict": True}
            resp.raise_for_status()
            rows = resp.json()
        return rows[0] if rows else None
    except Exception as exc:
        logger.error(
            "[MAYA-WATCH] insert_outbound_message failed lead_id=%s sid=%s: %s",
            lead_id, sid, exc,
        )
        return None

"""
app/services/attribution.py
============================
Attribution Ledger v0 — Phase 2a spear tip.

Records WhatsApp outbound actions, runs batch single-touch attribution
against booked outcomes, and reads recovered revenue.

Public API
----------
record_whatsapp_action(client_id, lead_phone, metadata=None) -> None
    Fire-and-forget. Resolves lead_id from phone, inserts an
    attribution_actions row. Skips silently on missing env / lead.
    Never raises — wired into the WA reply pipeline.

run_batch_attribution() -> dict
    Process every attribution_outcomes row that has no edge yet.
    For each: find the latest WhatsApp action within the window,
    write one attribution_edges row. NULL action_id when no action
    found — that case is recorded explicitly.
    Returns {"processed": N, "attributed": K, "unattributed": M}.

compute_recovered_revenue(client_id, since=None) -> dict
    Sum attributed_amount on edges for client. Counts attributed vs.
    unattributed outcomes. Returns {"recovered_total", "attributed_count",
    "unattributed_count"}.

Economic constants
------------------
RECOVERED_AMOUNT_PER_BOOKING is the single source of truth for the v0
per-booking recovered amount. The migration's trigger does NOT embed
this value — it only writes the state-change fact. The batch worker
applies the constant when an outcome is matched to an action.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Economic constants (v0 single source of truth) ───────────────────────────
# v0 is one tenant (BPM). When the second client onboards, replace these
# constants with a per-client lookup against clients.metadata or a small
# attribution_config table. ~10 minutes of work, no application change here.
RECOVERED_AMOUNT_PER_BOOKING: float = 12000.0   # NIS per booked lead
ATTRIBUTION_WINDOW_HOURS: int = 48              # action must be within this window before outcome

# ── Supabase wiring ──────────────────────────────────────────────────────────
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_TABLE_ACTIONS = "attribution_actions"
_TABLE_OUTCOMES = "attribution_outcomes"
_TABLE_EDGES = "attribution_edges"
_TABLE_LEADS = "leads"


def _headers(prefer: str = "return=minimal") -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _env_ready() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_lead_id_by_phone(phone: str) -> Optional[str]:
    """Resolve leads.id from phone. Returns None if not found or env missing."""
    if not _env_ready() or not phone:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_LEADS}",
                params={"phone": f"eq.{phone}", "select": "id", "limit": "1"},
                headers={
                    "apikey": _SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
                },
            )
            resp.raise_for_status()
            rows = resp.json()
        if not rows:
            return None
        return rows[0].get("id")
    except Exception as exc:
        logger.warning("[ATTRIBUTION] lead lookup failed phone=%s: %s", phone, exc)
        return None


def _parse_iso(ts: str) -> datetime:
    """Parse Postgres ISO timestamp into a tz-aware datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ── Public API: action recording ─────────────────────────────────────────────


async def record_whatsapp_action(
    client_id: str,
    lead_phone: str,
    metadata: Optional[dict] = None,
) -> None:
    """
    Insert one attribution_actions row for an outbound WhatsApp message.
    Never raises. Skips silently on missing env, missing client_id, or
    unresolvable phone.
    """
    if not _env_ready():
        return
    if not client_id or not lead_phone:
        return

    lead_id = await _get_lead_id_by_phone(lead_phone)
    if not lead_id:
        # Lead not yet persisted — acceptable v0 loss. The first WA from a
        # new lead saves the lead row; the recorded action follows on the
        # next inbound message.
        logger.info("[ATTRIBUTION] skip action — lead not found phone=%s", lead_phone)
        return

    payload = {
        "client_id": client_id,
        "lead_id": lead_id,
        "channel": "whatsapp",
        "metadata": metadata or {},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE_ACTIONS}",
                json=payload,
                headers=_headers(),
            )
            resp.raise_for_status()
        logger.info(
            "[ATTRIBUTION] action recorded client_id=%s lead_id=%s",
            client_id, lead_id,
        )
    except Exception as exc:
        logger.error("[ATTRIBUTION] action insert failed: %s | payload=%s", exc, payload)


# ── Public API: batch attribution worker ─────────────────────────────────────


async def _fetch_unattributed_outcomes() -> list[dict]:
    """
    Return outcomes that have no row in attribution_edges yet.
    v0 implementation: fetch all outcomes + all edge.outcome_ids,
    diff in Python. Acceptable at v0 volumes.
    """
    headers = {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        outcomes_resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_TABLE_OUTCOMES}",
            params={"select": "id,client_id,lead_id,occurred_at"},
            headers=headers,
        )
        outcomes_resp.raise_for_status()
        outcomes = outcomes_resp.json()

        edges_resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_TABLE_EDGES}",
            params={"select": "outcome_id"},
            headers=headers,
        )
        edges_resp.raise_for_status()
        attributed_ids = {e["outcome_id"] for e in edges_resp.json()}

    return [o for o in outcomes if o["id"] not in attributed_ids]


async def _find_latest_action_in_window(
    lead_id: str,
    outcome_occurred_at: datetime,
    window_hours: int,
) -> Optional[dict]:
    """
    Return the most-recent attribution_actions row for lead_id with
    occurred_at in (outcome - window, outcome]. None if no match.
    """
    start = (outcome_occurred_at - timedelta(hours=window_hours)).isoformat()
    end = outcome_occurred_at.isoformat()
    headers = {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_TABLE_ACTIONS}",
            params={
                "lead_id": f"eq.{lead_id}",
                "occurred_at": [f"gte.{start}", f"lte.{end}"],
                "order": "occurred_at.desc",
                "limit": "1",
                "select": "id,occurred_at",
            },
            headers=headers,
        )
        resp.raise_for_status()
        rows = resp.json()
    return rows[0] if rows else None


async def _insert_edge(
    outcome_id: str,
    client_id: str,
    action_id: Optional[str],
    attributed_amount: float,
) -> None:
    payload = {
        "outcome_id": outcome_id,
        "client_id": client_id,
        "action_id": action_id,
        "attributed_amount": attributed_amount,
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/rest/v1/{_TABLE_EDGES}",
            json=payload,
            headers=_headers(),
        )
        resp.raise_for_status()


async def run_batch_attribution() -> dict:
    """
    Single-touch v0 attribution worker.

    For each unattributed outcome: find the latest WhatsApp action for
    that lead within ATTRIBUTION_WINDOW_HOURS before the outcome.
    Write an edge — with action_id when found, or NULL when not.

    NULL-action edges are persisted explicitly so unattributed bookings
    are queryable: 'Maya did NOT contribute to N of these bookings, by
    our own measurement.'
    """
    if not _env_ready():
        raise RuntimeError("SUPABASE env not configured")

    outcomes = await _fetch_unattributed_outcomes()
    attributed = 0
    unattributed = 0

    for outcome in outcomes:
        outcome_id = outcome["id"]
        client_id = outcome["client_id"]
        lead_id = outcome["lead_id"]
        occurred_at = _parse_iso(outcome["occurred_at"])

        action = await _find_latest_action_in_window(
            lead_id=lead_id,
            outcome_occurred_at=occurred_at,
            window_hours=ATTRIBUTION_WINDOW_HOURS,
        )

        if action:
            await _insert_edge(
                outcome_id=outcome_id,
                client_id=client_id,
                action_id=action["id"],
                attributed_amount=RECOVERED_AMOUNT_PER_BOOKING,
            )
            attributed += 1
        else:
            await _insert_edge(
                outcome_id=outcome_id,
                client_id=client_id,
                action_id=None,
                attributed_amount=0.0,
            )
            unattributed += 1

    return {
        "processed": len(outcomes),
        "attributed": attributed,
        "unattributed": unattributed,
    }


# ── Public API: recovered revenue read ───────────────────────────────────────


async def compute_recovered_revenue(
    client_id: str,
    since: Optional[str] = None,
) -> dict:
    """
    Aggregate attribution_edges for client. Returns three numbers:
      recovered_total      — sum(attributed_amount)
      attributed_count     — count of edges with action_id NOT NULL
      unattributed_count   — count of edges with action_id NULL

    `since` is an optional ISO timestamp; when provided, edges are
    filtered by created_at >= since.
    """
    if not _env_ready():
        raise RuntimeError("SUPABASE env not configured")
    if not client_id:
        raise ValueError("client_id is required")

    params: list[tuple[str, str]] = [
        ("client_id", f"eq.{client_id}"),
        ("select", "action_id,attributed_amount"),
    ]
    if since:
        params.append(("created_at", f"gte.{since}"))

    headers = {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_TABLE_EDGES}",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        edges = resp.json()

    recovered_total = sum(float(e.get("attributed_amount") or 0) for e in edges)
    attributed_count = sum(1 for e in edges if e.get("action_id"))
    unattributed_count = len(edges) - attributed_count

    return {
        "recovered_total": recovered_total,
        "attributed_count": attributed_count,
        "unattributed_count": unattributed_count,
    }

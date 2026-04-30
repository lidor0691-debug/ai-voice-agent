"""
Tests for app/services/attribution.py — Attribution Ledger v0.

Coverage:
  * record_whatsapp_action — skip paths and happy path payload shape
  * run_batch_attribution — attributed / unattributed / nothing-to-do
  * compute_recovered_revenue — empty / mixed / since filter passthrough
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import attribution
from app.services.attribution import (
    ATTRIBUTION_WINDOW_HOURS,
    RECOVERED_AMOUNT_PER_BOOKING,
    compute_recovered_revenue,
    record_whatsapp_action,
    run_batch_attribution,
)


# ── module-level constants ───────────────────────────────────────────────────

def test_recovered_amount_constant_is_positive():
    assert RECOVERED_AMOUNT_PER_BOOKING > 0


def test_window_hours_constant_is_positive_int():
    assert isinstance(ATTRIBUTION_WINDOW_HOURS, int)
    assert ATTRIBUTION_WINDOW_HOURS > 0


# ── record_whatsapp_action — skip paths ──────────────────────────────────────

@pytest.mark.asyncio
async def test_record_action_skips_when_env_missing():
    with patch.object(attribution, "_env_ready", return_value=False):
        # Must not raise, must not attempt any network.
        await record_whatsapp_action(client_id="c1", lead_phone="+972501234567")


@pytest.mark.asyncio
async def test_record_action_skips_when_client_id_empty():
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution, "_get_lead_id_by_phone", new=AsyncMock()) as lookup:
        await record_whatsapp_action(client_id="", lead_phone="+972501234567")
        lookup.assert_not_called()


@pytest.mark.asyncio
async def test_record_action_skips_when_lead_not_found():
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution, "_get_lead_id_by_phone", new=AsyncMock(return_value=None)), \
         patch.object(attribution, "httpx") as httpx_mod:
        await record_whatsapp_action(client_id="c1", lead_phone="+972501234567")
        # No POST attempted if lead unresolved.
        httpx_mod.AsyncClient.assert_not_called()


@pytest.mark.asyncio
async def test_record_action_never_raises_on_network_error():
    """Wired into the WA reply pipeline — must absorb errors silently."""
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution, "_get_lead_id_by_phone", new=AsyncMock(return_value="lead-1")), \
         patch.object(attribution, "httpx") as httpx_mod:
        client_mock = AsyncMock()
        client_mock.post = AsyncMock(side_effect=RuntimeError("boom"))
        httpx_mod.AsyncClient.return_value.__aenter__.return_value = client_mock
        # Must not raise.
        await record_whatsapp_action(client_id="c1", lead_phone="+972501234567")


# ── run_batch_attribution — happy paths ──────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_writes_attributed_edge_when_action_in_window():
    outcome_time = datetime.now(timezone.utc)
    outcomes = [{
        "id": "outcome-1",
        "client_id": "client-1",
        "lead_id": "lead-1",
        "occurred_at": outcome_time.isoformat(),
    }]
    matching_action = {"id": "action-1", "occurred_at": (outcome_time - timedelta(hours=2)).isoformat()}

    insert_edge = AsyncMock()
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution, "_fetch_unattributed_outcomes", new=AsyncMock(return_value=outcomes)), \
         patch.object(attribution, "_find_latest_action_in_window", new=AsyncMock(return_value=matching_action)), \
         patch.object(attribution, "_insert_edge", new=insert_edge):
        result = await run_batch_attribution()

    assert result == {"processed": 1, "attributed": 1, "unattributed": 0}
    insert_edge.assert_awaited_once()
    kwargs = insert_edge.await_args.kwargs
    assert kwargs["outcome_id"] == "outcome-1"
    assert kwargs["client_id"] == "client-1"
    assert kwargs["action_id"] == "action-1"
    assert kwargs["attributed_amount"] == RECOVERED_AMOUNT_PER_BOOKING


@pytest.mark.asyncio
async def test_batch_writes_null_action_edge_when_no_action_in_window():
    outcomes = [{
        "id": "outcome-1",
        "client_id": "client-1",
        "lead_id": "lead-1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }]
    insert_edge = AsyncMock()
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution, "_fetch_unattributed_outcomes", new=AsyncMock(return_value=outcomes)), \
         patch.object(attribution, "_find_latest_action_in_window", new=AsyncMock(return_value=None)), \
         patch.object(attribution, "_insert_edge", new=insert_edge):
        result = await run_batch_attribution()

    assert result == {"processed": 1, "attributed": 0, "unattributed": 1}
    kwargs = insert_edge.await_args.kwargs
    assert kwargs["action_id"] is None
    assert kwargs["attributed_amount"] == 0.0


@pytest.mark.asyncio
async def test_batch_no_outcomes_does_no_work():
    insert_edge = AsyncMock()
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution, "_fetch_unattributed_outcomes", new=AsyncMock(return_value=[])), \
         patch.object(attribution, "_insert_edge", new=insert_edge):
        result = await run_batch_attribution()

    assert result == {"processed": 0, "attributed": 0, "unattributed": 0}
    insert_edge.assert_not_called()


@pytest.mark.asyncio
async def test_batch_mixed_outcomes_count_correctly():
    now = datetime.now(timezone.utc)
    outcomes = [
        {"id": "o1", "client_id": "c1", "lead_id": "l1", "occurred_at": now.isoformat()},
        {"id": "o2", "client_id": "c1", "lead_id": "l2", "occurred_at": now.isoformat()},
        {"id": "o3", "client_id": "c1", "lead_id": "l3", "occurred_at": now.isoformat()},
    ]
    # l1 has action, l2 has none, l3 has action
    def _find_action(lead_id, outcome_occurred_at, window_hours):  # noqa: ARG001
        if lead_id == "l2":
            return None
        return {"id": f"action-{lead_id}", "occurred_at": (now - timedelta(hours=1)).isoformat()}

    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution, "_fetch_unattributed_outcomes", new=AsyncMock(return_value=outcomes)), \
         patch.object(attribution, "_find_latest_action_in_window", new=AsyncMock(side_effect=_find_action)), \
         patch.object(attribution, "_insert_edge", new=AsyncMock()):
        result = await run_batch_attribution()

    assert result == {"processed": 3, "attributed": 2, "unattributed": 1}


@pytest.mark.asyncio
async def test_batch_raises_when_env_missing():
    with patch.object(attribution, "_env_ready", return_value=False):
        with pytest.raises(RuntimeError):
            await run_batch_attribution()


# ── compute_recovered_revenue ────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


def _patched_httpx_get(payload):
    """Build a context-manager mock for httpx.AsyncClient that returns payload from .get()."""
    client_mock = AsyncMock()
    client_mock.get = AsyncMock(return_value=_FakeResp(payload))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client_mock)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, client_mock


@pytest.mark.asyncio
async def test_recovered_returns_zero_when_no_edges():
    cm, _ = _patched_httpx_get([])
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution.httpx, "AsyncClient", return_value=cm):
        result = await compute_recovered_revenue("client-1")
    assert result == {"recovered_total": 0.0, "attributed_count": 0, "unattributed_count": 0}


@pytest.mark.asyncio
async def test_recovered_aggregates_mixed_edges():
    edges = [
        {"action_id": "a1", "attributed_amount": 12000},
        {"action_id": None, "attributed_amount": 0},
        {"action_id": "a2", "attributed_amount": 12000},
        {"action_id": None, "attributed_amount": 0},
    ]
    cm, _ = _patched_httpx_get(edges)
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution.httpx, "AsyncClient", return_value=cm):
        result = await compute_recovered_revenue("client-1")

    assert result["recovered_total"] == 24000.0
    assert result["attributed_count"] == 2
    assert result["unattributed_count"] == 2


@pytest.mark.asyncio
async def test_recovered_passes_since_to_query():
    cm, client_mock = _patched_httpx_get([])
    with patch.object(attribution, "_env_ready", return_value=True), \
         patch.object(attribution.httpx, "AsyncClient", return_value=cm):
        await compute_recovered_revenue("client-1", since="2026-04-01T00:00:00Z")

    # Inspect params passed to .get
    call_kwargs = client_mock.get.await_args.kwargs
    params = call_kwargs["params"]
    flat = {k: v for k, v in params}
    assert flat.get("created_at") == "gte.2026-04-01T00:00:00Z"
    assert flat.get("client_id") == "eq.client-1"


@pytest.mark.asyncio
async def test_recovered_raises_on_empty_client_id():
    with patch.object(attribution, "_env_ready", return_value=True):
        with pytest.raises(ValueError):
            await compute_recovered_revenue("")

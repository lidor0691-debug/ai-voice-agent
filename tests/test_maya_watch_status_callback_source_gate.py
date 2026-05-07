"""
Stage 10C-1 — unit tests for the status-callback source gate.

Verifies that update_outbound_status mirrors delivery state to
maya_watch_leads.followup_* only when the matched message row's source is
'followup' or NULL (legacy). Operator-send rows (source='operator_preview')
update only their own row, never the lead's followup snapshot.

We mock httpx.AsyncClient so no real network calls happen.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import maya_watch_store


def _mock_resp(status_code: int, json_value: list):
    """Build a fake httpx response with .raise_for_status() and .json()."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value=json_value)
    return resp


def _build_async_client(message_patch_rows: list):
    """
    Build a context-manager-compatible mock of httpx.AsyncClient whose
    .patch() returns sequenced responses:
      1st patch → messages PATCH (returns message_patch_rows for select=lead_id,source)
      2nd patch → leads PATCH (returns empty success)

    The test inspects .patch.await_args_list to verify how many PATCHes
    fired and against which URLs.
    """
    client = MagicMock()
    # First call returns the messages-patch result; subsequent calls return
    # an empty success (leads patch returns nothing visible to the caller).
    responses = [
        _mock_resp(200, message_patch_rows),     # messages PATCH
        _mock_resp(204, []),                      # leads PATCH (when fired)
    ]
    client.patch = AsyncMock(side_effect=responses)

    # async with httpx.AsyncClient(...) as client:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, client


@pytest.mark.asyncio
async def test_mirror_fires_for_source_followup():
    """source='followup' → both message PATCH and lead PATCH fire."""
    cm, client = _build_async_client([
        {"lead_id": "lead-uuid-1", "source": "followup"},
    ])
    with patch.object(maya_watch_store, "env_ready", return_value=True), \
         patch.object(maya_watch_store, "httpx") as httpx_mock:
        httpx_mock.AsyncClient = MagicMock(return_value=cm)

        ok = await maya_watch_store.update_outbound_status(
            sid="SM_followup",
            status="delivered",
        )

    assert ok is True
    # Two PATCHes: one for messages, one for leads.
    assert client.patch.await_count == 2
    urls = [call.args[0] for call in client.patch.await_args_list]
    assert any("maya_watch_messages" in u for u in urls)
    assert any("maya_watch_leads" in u for u in urls)


@pytest.mark.asyncio
async def test_mirror_fires_for_legacy_null_source():
    """source=None (pre-10C-1 legacy) → mirror still fires for backward compat."""
    cm, client = _build_async_client([
        {"lead_id": "lead-uuid-2", "source": None},
    ])
    with patch.object(maya_watch_store, "env_ready", return_value=True), \
         patch.object(maya_watch_store, "httpx") as httpx_mock:
        httpx_mock.AsyncClient = MagicMock(return_value=cm)

        ok = await maya_watch_store.update_outbound_status(
            sid="SM_legacy",
            status="sent",
        )

    assert ok is True
    assert client.patch.await_count == 2  # message + lead
    urls = [call.args[0] for call in client.patch.await_args_list]
    assert any("maya_watch_leads" in u for u in urls)


@pytest.mark.asyncio
async def test_mirror_skipped_for_operator_preview_source():
    """source='operator_preview' → only message PATCH fires; NO lead PATCH."""
    cm, client = _build_async_client([
        {"lead_id": "lead-uuid-3", "source": "operator_preview"},
    ])
    with patch.object(maya_watch_store, "env_ready", return_value=True), \
         patch.object(maya_watch_store, "httpx") as httpx_mock:
        httpx_mock.AsyncClient = MagicMock(return_value=cm)

        ok = await maya_watch_store.update_outbound_status(
            sid="SM_operator",
            status="delivered",
        )

    assert ok is True
    assert client.patch.await_count == 1  # message only — lead skipped
    urls = [call.args[0] for call in client.patch.await_args_list]
    assert any("maya_watch_messages" in u for u in urls)
    assert not any("maya_watch_leads" in u for u in urls)


@pytest.mark.asyncio
async def test_orphan_sid_returns_false():
    """No matching message row → returns False, no PATCHes beyond the first."""
    cm, client = _build_async_client([])  # empty result from messages PATCH
    with patch.object(maya_watch_store, "env_ready", return_value=True), \
         patch.object(maya_watch_store, "httpx") as httpx_mock:
        httpx_mock.AsyncClient = MagicMock(return_value=cm)

        ok = await maya_watch_store.update_outbound_status(
            sid="SM_unknown",
            status="failed",
        )

    assert ok is False
    # Only the messages PATCH happened; no lead PATCH for an orphan.
    assert client.patch.await_count == 1


@pytest.mark.asyncio
async def test_filter_active_acted_keys_unaffected():
    """Sanity: source-tracking change doesn't disturb the existing
    pure helper used by briefing suppression."""
    rows = [
        {"lead_id": "L1", "decision_status": "awaiting_attention", "action_type": "acted"},
        {"lead_id": "L2", "decision_status": "no_response",        "action_type": "acted"},
        {"lead_id": "L2", "decision_status": "no_response",        "action_type": "undone"},
    ]
    keys = maya_watch_store._filter_active_acted_keys(rows)
    assert ("L1", "awaiting_attention", "acted") in keys
    assert ("L2", "no_response", "acted") not in keys  # undone cancels

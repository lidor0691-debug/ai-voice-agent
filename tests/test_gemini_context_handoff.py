"""
Tests for the durable Gemini HTTP→WebSocket context handoff
(app/routes/voice_gemini.py::_resolve_gemini_context).

The WS no longer depends on cross-process shared memory: it re-resolves the
active agent from a `client_id` passed via Twilio <Stream><Parameter>, keeping
the in-memory _GEMINI_CALL_CONTEXT only as a temporary fallback.

No real Supabase/Twilio/network: fetch_agent_config_by_client_id is mocked and
the in-memory store is set directly. Covers:
  1. context resolved through customParameters
  2. missing parameters → fall back to the in-memory store
  3. neither source available → empty cfg (caller fail-closes)
  4. inactive / invalid client → empty cfg (caller fail-closes)
"""
from __future__ import annotations

import os
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

from unittest.mock import AsyncMock, patch

import pytest

import app.routes.voice_gemini as vg

# A genuinely active agent config (not fallback, has prompt_override).
VALID_CFG = {
    "client_id":       "c-roi",
    "client_name":     "מאיה - Roi Insurance",
    "prompt_override": "PROMPT for {{caller_phone}}",
    "webhook_url":     "http://hook.example/roi",
    "fallback_used":   False,
}

# What fetch_agent_config_by_client_id returns on miss / inactive.
SAFE_DEFAULT = {
    "client_name":     "Unassigned",
    "prompt_override": "",
    "webhook_url":     "",
    "fallback_used":   True,
}


def _fail_closed(agent_cfg: dict) -> bool:
    """Mirror the WS fail-closed condition."""
    return bool(agent_cfg.get("fallback_used")) or not agent_cfg.get("prompt_override")


@pytest.mark.asyncio
async def test_context_resolved_via_custom_parameters():
    """client_id in customParameters → Supabase re-resolution (no in-memory needed)."""
    vg._GEMINI_CALL_CONTEXT.clear()  # prove it did NOT come from memory
    fetch = AsyncMock(return_value=VALID_CFG)
    with patch.object(vg, "fetch_agent_config_by_client_id", fetch):
        res = await vg._resolve_gemini_context(
            {"client_id": "c-roi", "caller_phone": "+972500000001", "call_sid": "CA1"},
            "CA1",
        )
    fetch.assert_awaited_once_with("c-roi")
    assert res["source"] == "custom_parameters"
    assert res["agent_cfg"] is VALID_CFG
    assert res["caller_phone"] == "+972500000001"
    assert res["client_id"] == "c-roi"
    assert res["client_name"] == "מאיה - Roi Insurance"
    assert _fail_closed(res["agent_cfg"]) is False


@pytest.mark.asyncio
async def test_missing_params_fall_back_to_in_memory():
    """No client_id in params → use the legacy in-memory store; Supabase not called."""
    vg._GEMINI_CALL_CONTEXT.clear()
    vg._GEMINI_CALL_CONTEXT["CA2"] = {"from": "+972500000002", "agent_cfg": VALID_CFG}
    fetch = AsyncMock(return_value=SAFE_DEFAULT)
    with patch.object(vg, "fetch_agent_config_by_client_id", fetch):
        res = await vg._resolve_gemini_context({}, "CA2")
    fetch.assert_not_awaited()  # no client_id → no Supabase call
    assert res["source"] == "in_memory_fallback"
    assert res["agent_cfg"] is VALID_CFG
    assert res["caller_phone"] == "+972500000002"
    assert res["client_id"] == "c-roi"
    assert _fail_closed(res["agent_cfg"]) is False


@pytest.mark.asyncio
async def test_neither_source_available_fails_closed():
    """No params and nothing in memory → empty cfg, caller must fail-closed."""
    vg._GEMINI_CALL_CONTEXT.clear()
    fetch = AsyncMock(return_value=SAFE_DEFAULT)
    with patch.object(vg, "fetch_agent_config_by_client_id", fetch):
        res = await vg._resolve_gemini_context({}, "CA_none")
    assert res["source"] == "none"
    assert res["agent_cfg"] == {}
    assert _fail_closed(res["agent_cfg"]) is True


@pytest.mark.asyncio
async def test_inactive_or_invalid_client_fails_closed():
    """client_id given but no active agent (safe default) and no memory → fail-closed."""
    vg._GEMINI_CALL_CONTEXT.clear()
    fetch = AsyncMock(return_value=SAFE_DEFAULT)
    with patch.object(vg, "fetch_agent_config_by_client_id", fetch):
        res = await vg._resolve_gemini_context(
            {"client_id": "ghost", "caller_phone": "+972500000003"},
            "CA_bad",
        )
    fetch.assert_awaited_once_with("ghost")
    assert res["source"] == "none"
    assert res["agent_cfg"] == {}
    assert res["caller_phone"] == "+972500000003"   # caller phone still carried through
    assert _fail_closed(res["agent_cfg"]) is True


@pytest.mark.asyncio
async def test_custom_params_win_over_stale_in_memory():
    """When both exist, the Supabase-resolved (params) config is authoritative."""
    vg._GEMINI_CALL_CONTEXT.clear()
    stale = {**VALID_CFG, "client_name": "STALE", "client_id": "c-stale"}
    vg._GEMINI_CALL_CONTEXT["CA3"] = {"from": "+972500000009", "agent_cfg": stale}
    with patch.object(vg, "fetch_agent_config_by_client_id", AsyncMock(return_value=VALID_CFG)):
        res = await vg._resolve_gemini_context(
            {"client_id": "c-roi", "caller_phone": "+972500000004"}, "CA3",
        )
    assert res["source"] == "custom_parameters"
    assert res["client_name"] == "מאיה - Roi Insurance"

"""
Tests for app/services/maya_action_executor.py.

No real Supabase calls. No real Twilio calls. user_supabase_rpc is patched
on the executor module; the Twilio SDK is replaced by a sentinel that
records every method call so we can assert it's never invoked in dryrun.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import maya_action_executor as ex
from app.services.maya_action_executor import (
    ResolveResult,
    TwilioResult,
    execute_one,
    resolve_twilio_config,
    send_whatsapp,
)


# ── shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def env_no_live(monkeypatch):
    """Default — MAYA_TWILIO_MODE unset, no allowlist."""
    monkeypatch.delenv("MAYA_TWILIO_MODE", raising=False)
    monkeypatch.delenv("MAYA_TWILIO_LIVE_ALLOWLIST", raising=False)
    monkeypatch.delenv("MAYA_TWILIO_FROM_NUMBER", raising=False)


@pytest.fixture
def env_live(monkeypatch):
    monkeypatch.setenv("MAYA_TWILIO_MODE", "live")
    monkeypatch.setenv("MAYA_TWILIO_LIVE_ALLOWLIST", "+15550009999")


def _agent_row(**overrides):
    base = {
        "id":              "agent-uuid-1",
        "client_id":       "client-uuid-1",
        "is_active":       True,
        "whatsapp_number": "+15550000000",
    }
    base.update(overrides)
    return base


def _claim_ok(**overrides):
    base = {
        "ok": True,
        "error_code": "ok",
        "suggestion": {"id": "s1", "status": "executing", "version": 5},
        "execution_log_id": "log-1",
        "lead_phone": "+15550009999",
        "message_he": "שלום עולם",
        "agent_id": "agent-uuid-1",
        "client_id": "client-uuid-1",
    }
    base.update(overrides)
    return base


# ── 1. invalid input ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_input_empty_suggestion_id(env_no_live):
    out = await execute_one("", 1, "jwt")
    assert out == {"ok": False, "error_code": "invalid_input", "error_he": "קלט לא תקין."}


@pytest.mark.asyncio
async def test_invalid_input_empty_jwt(env_no_live):
    out = await execute_one("s1", 1, "")
    assert out["error_code"] == "invalid_input"


@pytest.mark.asyncio
async def test_invalid_input_non_int_version(env_no_live):
    out = await execute_one("s1", "not-int", "jwt")  # type: ignore[arg-type]
    assert out["error_code"] == "invalid_input"


@pytest.mark.asyncio
async def test_invalid_input_bool_version_rejected(env_no_live):
    # bool is a subclass of int — explicitly reject
    out = await execute_one("s1", True, "jwt")  # type: ignore[arg-type]
    assert out["error_code"] == "invalid_input"


# ── 2. claim failure returns envelope as-is, no resolve/send ───────────────


@pytest.mark.asyncio
async def test_claim_failure_returns_envelope(env_no_live):
    claim_fail = {"ok": False, "error_code": "stale_version", "error_he": "..."}
    with patch.object(ex, "user_supabase_rpc", new=AsyncMock(return_value=claim_fail)) as rpc, \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock()) as lookup:
        out = await execute_one("s1", 1, "jwt")
        assert out == claim_fail
        # exactly one RPC call — only claim, no finalize
        assert rpc.call_count == 1
        assert rpc.call_args.args[1] == "claim_action_for_execution"
        # agents_config never touched on claim failure
        lookup.assert_not_called()


# ── 3. dryrun happy path ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dryrun_success_executes(env_no_live):
    claim_ok = _claim_ok()
    finalize_ok = {"ok": True, "error_code": "ok",
                   "suggestion": {"id": "s1", "status": "executed", "version": 7}}

    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_ok])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        out = await execute_one("s1", 5, "jwt")

    assert out["ok"] is True
    assert out["suggestion"]["status"] == "executed"

    # Two RPC calls: claim then finalize
    assert rpc_mock.call_count == 2
    fn_names = [c.args[1] for c in rpc_mock.call_args_list]
    assert fn_names == ["claim_action_for_execution", "finalize_action_execution"]

    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_terminal_status"] == "executed"
    assert finalize_params["p_twilio_message_sid"].startswith("DRYRUN_")
    assert finalize_params["p_twilio_message_status"] == "dryrun"
    assert finalize_params["p_failure_code"] is None
    assert finalize_params["p_failure_detail"] is None


# ── 4. config_missing after claim → finalize failed/config_missing ─────────


@pytest.mark.asyncio
async def test_config_missing_no_agent_finalizes_failed(env_no_live):
    claim_ok = _claim_ok(agent_id=None)  # missing agent_id
    finalize_fail = {"ok": True, "suggestion": {"status": "failed"}}

    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock()) as lookup:
        out = await execute_one("s1", 5, "jwt")

    assert out == finalize_fail
    # No agents_config lookup attempted when agent_id is missing
    lookup.assert_not_called()

    # finalize call had config_missing + agent_id_missing detail
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_terminal_status"] == "failed"
    assert finalize_params["p_failure_code"] == "config_missing"
    assert finalize_params["p_failure_detail"] == "agent_id_missing"


# ── 5. live allowlist blocks non-allowed phone, no Twilio call ─────────────


@pytest.mark.asyncio
async def test_live_allowlist_blocks_unlisted_phone(env_live, monkeypatch):
    # lead_phone NOT in MAYA_TWILIO_LIVE_ALLOWLIST (which is +15550009999 only)
    claim_ok = _claim_ok(lead_phone="+15550008888")
    finalize_fail = {"ok": True, "suggestion": {"status": "failed"}}

    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    twilio_sentinel = MagicMock()  # any call to this should fail the test
    fake_twilio_rest = types.ModuleType("twilio.rest")
    fake_twilio_rest.Client = MagicMock(return_value=twilio_sentinel)
    monkeypatch.setitem(sys.modules, "twilio.rest", fake_twilio_rest)

    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        out = await execute_one("s1", 5, "jwt")

    assert out == finalize_fail
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_code"] == "config_missing"
    assert finalize_params["p_failure_detail"] == "phone_not_in_live_allowlist"
    # Twilio Client never instantiated
    fake_twilio_rest.Client.assert_not_called()
    twilio_sentinel.messages.create.assert_not_called()


# ── 6. no MAYA_TWILIO_FROM_NUMBER read ──────────────────────────────────────


@pytest.mark.asyncio
async def test_no_global_from_number_env_read(env_no_live, monkeypatch):
    # Set a sentinel that would scream if it ever appears anywhere.
    monkeypatch.setenv("MAYA_TWILIO_FROM_NUMBER", "SHOULD_NEVER_BE_READ_SENTINEL")
    claim_ok = _claim_ok()
    finalize_ok = {"ok": True, "suggestion": {"status": "executed"}}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_ok])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        out = await execute_one("s1", 5, "jwt")

    assert out["ok"] is True

    # from-number used in send must come from agents_config row, not env
    finalize_params = rpc_mock.call_args_list[1].args[2]
    sid = finalize_params["p_twilio_message_sid"]
    assert sid.startswith("DRYRUN_")
    # The sentinel must not appear anywhere in the finalize payload
    for v in finalize_params.values():
        assert v is None or "SHOULD_NEVER_BE_READ_SENTINEL" not in str(v)


# ── 7-9. config_missing variants from agents_config row ─────────────────────


@pytest.mark.asyncio
async def test_inactive_agent_config_missing(env_no_live):
    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup",
                      new=AsyncMock(return_value=_agent_row(is_active=False))):
        await execute_one("s1", 5, "jwt")
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_detail"] == "agent_inactive"


@pytest.mark.asyncio
async def test_cross_tenant_agent_rejected(env_no_live):
    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup",
                      new=AsyncMock(return_value=_agent_row(client_id="different-client"))):
        await execute_one("s1", 5, "jwt")
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_detail"] == "cross_tenant_rejection"


@pytest.mark.asyncio
async def test_invalid_e164_whatsapp_number_rejected(env_no_live):
    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup",
                      new=AsyncMock(return_value=_agent_row(whatsapp_number="not-e164"))):
        await execute_one("s1", 5, "jwt")
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_detail"] == "whatsapp_number_invalid_e164"


@pytest.mark.asyncio
async def test_agent_not_found_returns_config_missing(env_no_live):
    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=None)):
        await execute_one("s1", 5, "jwt")
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_detail"] == "agent_not_found"


@pytest.mark.asyncio
async def test_agent_id_mismatch_returns_config_missing(env_no_live):
    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup",
                      new=AsyncMock(return_value=_agent_row(id="agent-uuid-OTHER"))):
        await execute_one("s1", 5, "jwt")
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_detail"] == "agent_id_mismatch"


@pytest.mark.asyncio
async def test_missing_whatsapp_number_returns_config_missing(env_no_live):
    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup",
                      new=AsyncMock(return_value=_agent_row(whatsapp_number=None))):
        await execute_one("s1", 5, "jwt")
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_detail"] == "no_whatsapp_number_for_agent"


# ── 10-11. Twilio error code mapping ────────────────────────────────────────


class _FakeTwilioRestException(Exception):
    """Stand-in for twilio.base.exceptions.TwilioRestException."""

    def __init__(self, code: int, msg: str = ""):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def _install_fake_twilio_sdk(monkeypatch, *, success_sid: str = "SM_real",
                              success_status: str = "queued",
                              raise_code: int | None = None):
    """Replace twilio.rest and twilio.base.exceptions in sys.modules."""
    rest = types.ModuleType("twilio.rest")
    base_exc = types.ModuleType("twilio.base.exceptions")
    base_exc.TwilioRestException = _FakeTwilioRestException  # type: ignore[attr-defined]

    fake_message = MagicMock()
    fake_message.sid = success_sid
    fake_message.status = success_status

    if raise_code is None:
        fake_messages = MagicMock()
        fake_messages.create.return_value = fake_message
    else:
        fake_messages = MagicMock()
        fake_messages.create.side_effect = _FakeTwilioRestException(raise_code,
                                                                    msg=f"twilio fail {raise_code}")

    fake_client_instance = MagicMock()
    fake_client_instance.messages = fake_messages
    fake_client_class = MagicMock(return_value=fake_client_instance)
    rest.Client = fake_client_class  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "twilio.rest", rest)
    monkeypatch.setitem(sys.modules, "twilio.base.exceptions", base_exc)
    return fake_client_class, fake_messages


@pytest.mark.asyncio
async def test_twilio_63016_maps_to_session_expired(env_live, monkeypatch):
    monkeypatch.setenv("MAYA_TWILIO_LIVE_ALLOWLIST", "+15550009999")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_test")
    _, fake_messages = _install_fake_twilio_sdk(monkeypatch, raise_code=63016)

    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        await execute_one("s1", 5, "jwt")

    fake_messages.create.assert_called_once()
    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_code"] == "session_expired"
    assert "63016" in (finalize_params["p_failure_detail"] or "")


@pytest.mark.asyncio
async def test_twilio_generic_error_maps_to_twilio_error(env_live, monkeypatch):
    monkeypatch.setenv("MAYA_TWILIO_LIVE_ALLOWLIST", "+15550009999")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_test")
    _install_fake_twilio_sdk(monkeypatch, raise_code=21610)  # arbitrary non-session code

    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        await execute_one("s1", 5, "jwt")

    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_code"] == "twilio_error"


# ── 12. dryrun never calls Twilio SDK ───────────────────────────────────────


@pytest.mark.asyncio
async def test_dryrun_never_calls_twilio_sdk(env_no_live, monkeypatch):
    fake_client_class, fake_messages = _install_fake_twilio_sdk(monkeypatch)
    claim_ok = _claim_ok()
    finalize_ok = {"ok": True, "suggestion": {"status": "executed"}}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_ok])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        await execute_one("s1", 5, "jwt")

    fake_client_class.assert_not_called()
    fake_messages.create.assert_not_called()


# ── 13. user_supabase_rpc used for both claim and finalize; no service-role ─


@pytest.mark.asyncio
async def test_claim_and_finalize_use_user_jwt_helper(env_no_live):
    claim_ok = _claim_ok()
    finalize_ok = {"ok": True, "suggestion": {"status": "executed"}}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_ok])

    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        await execute_one("s1", 5, "JWT_SECRET")

    # Both RPC calls went through the user-JWT helper, with the JWT preserved.
    assert rpc_mock.call_count == 2
    for call in rpc_mock.call_args_list:
        assert call.args[0] == "JWT_SECRET"
    assert [c.args[1] for c in rpc_mock.call_args_list] == [
        "claim_action_for_execution",
        "finalize_action_execution",
    ]


# ── 14. failure_detail bounded to 500 chars ─────────────────────────────────


@pytest.mark.asyncio
async def test_failure_detail_bounded(env_live, monkeypatch):
    monkeypatch.setenv("MAYA_TWILIO_LIVE_ALLOWLIST", "+15550009999")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_test")

    rest = types.ModuleType("twilio.rest")
    base_exc = types.ModuleType("twilio.base.exceptions")
    base_exc.TwilioRestException = _FakeTwilioRestException  # type: ignore[attr-defined]
    long_msg = "X" * 5000
    fake_messages = MagicMock()
    fake_messages.create.side_effect = _FakeTwilioRestException(21610, msg=long_msg)
    fake_client_instance = MagicMock(messages=fake_messages)
    rest.Client = MagicMock(return_value=fake_client_instance)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "twilio.rest", rest)
    monkeypatch.setitem(sys.modules, "twilio.base.exceptions", base_exc)

    claim_ok = _claim_ok()
    finalize_fail = {"ok": True}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_fail])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        await execute_one("s1", 5, "jwt")

    finalize_params = rpc_mock.call_args_list[1].args[2]
    assert finalize_params["p_failure_code"] == "twilio_error"
    assert len(finalize_params["p_failure_detail"]) <= 500


# ── 15. no JWT/Authorization in returned envelope ──────────────────────────


@pytest.mark.asyncio
async def test_no_jwt_or_authorization_in_returned_envelope(env_no_live):
    claim_ok = _claim_ok()
    finalize_ok = {"ok": True, "suggestion": {"status": "executed"}}
    rpc_mock = AsyncMock(side_effect=[claim_ok, finalize_ok])
    with patch.object(ex, "user_supabase_rpc", new=rpc_mock), \
         patch.object(ex, "_agents_config_lookup", new=AsyncMock(return_value=_agent_row())):
        out = await execute_one("s1", 5, "VERY_SECRET_JWT")

    assert "VERY_SECRET_JWT" not in str(out)
    assert "Authorization" not in str(out)


# ── resolve_twilio_config unit coverage ─────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_returns_dryrun_when_env_unset(env_no_live):
    with patch.object(ex, "_agents_config_lookup",
                      new=AsyncMock(return_value=_agent_row())):
        r = await resolve_twilio_config("agent-uuid-1", "client-uuid-1", "+15550009999")
    assert r.ok is True
    assert r.mode == "dryrun"
    assert r.from_number == "+15550000000"


@pytest.mark.asyncio
async def test_resolve_returns_live_with_allowlisted_phone(env_live):
    with patch.object(ex, "_agents_config_lookup",
                      new=AsyncMock(return_value=_agent_row())):
        r = await resolve_twilio_config("agent-uuid-1", "client-uuid-1", "+15550009999")
    assert r.ok is True
    assert r.mode == "live"


@pytest.mark.asyncio
async def test_resolve_misspelled_mode_falls_back_to_dryrun(monkeypatch):
    monkeypatch.setenv("MAYA_TWILIO_MODE", "Live")  # capitalization matters
    with patch.object(ex, "_agents_config_lookup",
                      new=AsyncMock(return_value=_agent_row())):
        r = await resolve_twilio_config("agent-uuid-1", "client-uuid-1", "+15550009999")
    assert r.ok is True
    assert r.mode == "dryrun"


# ── send_whatsapp unit coverage ─────────────────────────────────────────────


def test_send_whatsapp_dryrun_returns_dryrun_sid():
    res = send_whatsapp("+15550009999", "+15550000000", "hello", mode="dryrun")
    assert res.kind == "success"
    assert res.sid is not None and res.sid.startswith("DRYRUN_")
    assert res.status == "dryrun"


def test_send_whatsapp_live_without_creds_returns_twilio_error(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    res = send_whatsapp("+15550009999", "+15550000000", "hello", mode="live")
    assert res.kind == "twilio_error"
    assert res.detail == "twilio_credentials_missing"

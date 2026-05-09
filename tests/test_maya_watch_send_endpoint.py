"""
Stage 10C-2 — End-to-end tests for POST /maya-watch/messages/send.

Mocks all external boundaries (Supabase store helpers + Twilio send).
NO real network. NO real WhatsApp. NO real Twilio call. Lidor untouched.

Coverage matches the 13 cases from the 10C-2 plan:
  1. happy path                                    → 200, row inserted
  2. no inbound                                    → 409 whatsapp_window_closed reason=no_inbound
  3. inbound > 24h ago                             → 409 whatsapp_window_closed reason=too_old
  4. invalid X-Maya-Watch-Key                      → 401 (existing dep)
  5. cross-tenant client_id                        → 404 lead_not_found
  6. lead.agent_id is NULL                         → 400 lead_unrouted
  7. agent.whatsapp_number empty                   → 500 agent_misconfigured
  8. message empty after trim                      → 400 invalid_body
  9. message too long                              → 400 invalid_body
 10. invalid idempotency key                       → 400 invalid_idempotency_key
 11. duplicate idempotency key                     → 200 already_sent=True, no Twilio call
 12. Twilio raises                                 → 502 twilio_send_failed, no insert
 13. BASE_URL missing                              → 500 base_url_not_configured, no Twilio call

Status-callback source-gate behavior already covered by
tests/test_maya_watch_status_callback_source_gate.py from Stage 10C-1.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import maya_watch as routes_module
from app.services import maya_watch as svc_module
from app.services import maya_watch_store as store_module


# ── Fixtures ─────────────────────────────────────────────────────────────


_TEST_INTERNAL_KEY = "test_internal_key"
_TEST_LEAD_ID = "11111111-1111-4111-8111-111111111111"
_TEST_CLIENT_ID = "22222222-2222-4222-8222-222222222222"
_TEST_AGENT_ID = "33333333-3333-4333-8333-333333333333"
_TEST_PHONE = "+972500000792"
_TEST_AGENT_NUMBER = "+972500000111"
_TEST_IDEMPOTENCY_KEY = "abcdef01-2345-4678-9abc-def012345678"  # UUID v4
_TEST_BASE_URL = "https://api.test.example.com"


@pytest.fixture
def fast_env(monkeypatch):
    """Set every env var the orchestrator + route check at call time."""
    monkeypatch.setenv("BASE_URL", _TEST_BASE_URL)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtestaccountsid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_auth_token")
    # Stage 10D — allowlist the test phone so existing happy-path tests
    # continue exercising the post-allowlist code paths. Allowlist-block
    # tests use monkeypatch.delenv to override.
    monkeypatch.setenv("MAYA_WATCH_SEND_ALLOWED_PHONES", _TEST_PHONE)
    # Internal key is module-global; route loaded it at import time. Override.
    monkeypatch.setattr(routes_module, "_INTERNAL_KEY", _TEST_INTERNAL_KEY)


@pytest.fixture
def store_mocks(monkeypatch):
    """Default mocks for store calls — happy path. Individual tests override.

    Returns a MutableNamespace whose attrs are AsyncMock instances so tests
    can inspect call counts and override return values.
    """
    class M:
        find_idempotency = AsyncMock(return_value=None)  # no duplicate
        get_lead = AsyncMock(return_value={
            "id": _TEST_LEAD_ID,
            "phone": _TEST_PHONE,
            "client_id": _TEST_CLIENT_ID,
            "agent_id": _TEST_AGENT_ID,
        })
        get_last_inbound_ts = AsyncMock(
            return_value=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        insert_outbound = AsyncMock(return_value={
            "id": 12345,
            "lead_id": _TEST_LEAD_ID,
            "client_id": _TEST_CLIENT_ID,
            "agent_id": _TEST_AGENT_ID,
            "direction": "out",
            "body": "test body",
            "sid": "SMtest_sid_happy",
            "status": "queued",
            "ts": "2026-05-09T12:00:00+00:00",
            "source": "operator_preview",
            "metadata": {
                "idempotency_key": _TEST_IDEMPOTENCY_KEY,
                "decision_id": "decision:awaiting_attention:+972500000792",
                "sent_by": "operator-id-1",
            },
        })
    monkeypatch.setattr(store_module, "find_message_by_idempotency_key", M.find_idempotency)
    monkeypatch.setattr(store_module, "get_lead_by_id", M.get_lead)
    monkeypatch.setattr(store_module, "get_last_inbound_ts", M.get_last_inbound_ts)
    monkeypatch.setattr(store_module, "insert_outbound_message", M.insert_outbound)
    return M


@pytest.fixture
def svc_mocks(monkeypatch):
    """Default mocks for service-layer external boundaries — happy path."""
    class M:
        agents_lookup = AsyncMock(return_value={
            "id": _TEST_AGENT_ID,
            "client_id": _TEST_CLIENT_ID,
            "whatsapp_number": _TEST_AGENT_NUMBER,
        })
        twilio_send = AsyncMock(return_value="SMtest_sid_happy")
    monkeypatch.setattr(svc_module, "_agents_config_lookup", M.agents_lookup)
    monkeypatch.setattr(svc_module, "_send_operator_via_twilio", M.twilio_send)
    return M


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes_module.router)
    return TestClient(app)


def _post(
    client: TestClient,
    *,
    body: dict,
    key: str = _TEST_INTERNAL_KEY,
    idempotency_key: str = _TEST_IDEMPOTENCY_KEY,
    acted_by: str = "operator-id-1",
    client_id_query: str = None,
):
    headers = {
        "X-Maya-Watch-Key": key,
        "X-Maya-Watch-Idempotency-Key": idempotency_key,
        "X-Maya-Watch-Acted-By": acted_by,
    }
    params = {}
    if client_id_query is not None:
        params["client_id"] = client_id_query
    return client.post("/maya-watch/messages/send", json=body, headers=headers, params=params)


def _valid_body() -> dict:
    return {
        "lead_id": _TEST_LEAD_ID,
        "message": "Test message body שלום",
        "decision_id": "decision:awaiting_attention:+972500000792",
        "source": "operator_preview",
    }


# ── 1. Happy path ────────────────────────────────────────────────────────


def test_happy_path_sends_and_inserts(fast_env, store_mocks, svc_mocks, client):
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["already_sent"] is False
    assert body["twilio_sid"] == "SMtest_sid_happy"
    assert body["status"] == "queued"
    assert body["lead_id"] == _TEST_LEAD_ID
    assert body["phone"] == _TEST_PHONE
    assert body["source"] == "operator_preview"
    assert body["decision_id"] == "decision:awaiting_attention:+972500000792"
    # Verify Twilio was called exactly once with correct args.
    assert svc_mocks.twilio_send.await_count == 1
    call_kwargs = svc_mocks.twilio_send.await_args.kwargs
    assert call_kwargs["from_number"] == _TEST_AGENT_NUMBER
    assert call_kwargs["to_phone"] == _TEST_PHONE
    assert call_kwargs["base_url"] == _TEST_BASE_URL
    # Verify insert was called with operator_preview source + metadata.
    assert store_mocks.insert_outbound.await_count == 1
    insert_kwargs = store_mocks.insert_outbound.await_args.kwargs
    assert insert_kwargs["source"] == "operator_preview"
    assert insert_kwargs["metadata"]["idempotency_key"] == _TEST_IDEMPOTENCY_KEY
    assert insert_kwargs["metadata"]["decision_id"] == "decision:awaiting_attention:+972500000792"
    assert insert_kwargs["metadata"]["sent_by"] == "operator-id-1"


# ── 2-3. 24h window ──────────────────────────────────────────────────────


def test_no_inbound_returns_409_no_twilio(fast_env, store_mocks, svc_mocks, client):
    store_mocks.get_last_inbound_ts.return_value = None
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "whatsapp_window_closed"
    assert body["reason"] == "no_inbound"
    assert body["last_inbound_at"] is None
    assert svc_mocks.twilio_send.await_count == 0
    assert store_mocks.insert_outbound.await_count == 0


def test_inbound_too_old_returns_409_no_twilio(fast_env, store_mocks, svc_mocks, client):
    too_old = datetime.now(timezone.utc) - timedelta(hours=25)
    store_mocks.get_last_inbound_ts.return_value = too_old
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "whatsapp_window_closed"
    assert body["reason"] == "too_old"
    assert body["last_inbound_at"].startswith(too_old.isoformat()[:19])
    assert svc_mocks.twilio_send.await_count == 0


# ── 4. Internal key ─────────────────────────────────────────────────────


def test_invalid_internal_key_returns_401(fast_env, store_mocks, svc_mocks, client):
    resp = _post(client, body=_valid_body(), key="wrong_key")
    assert resp.status_code == 401
    assert svc_mocks.twilio_send.await_count == 0


# ── 5. Tenant scope ──────────────────────────────────────────────────────


def test_cross_tenant_returns_404(fast_env, store_mocks, svc_mocks, client):
    # Simulate the store's tenant filter producing no row.
    store_mocks.get_lead.return_value = None
    resp = _post(
        client, body=_valid_body(),
        client_id_query="99999999-9999-4999-8999-999999999999",
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "lead_not_found"
    assert svc_mocks.twilio_send.await_count == 0


# ── 6. Unrouted lead ─────────────────────────────────────────────────────


def test_lead_unrouted_returns_400(fast_env, store_mocks, svc_mocks, client):
    store_mocks.get_lead.return_value = {
        "id": _TEST_LEAD_ID, "phone": _TEST_PHONE,
        "client_id": _TEST_CLIENT_ID, "agent_id": None,
    }
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "lead_unrouted"
    assert svc_mocks.twilio_send.await_count == 0


# ── 7. Agent misconfigured ───────────────────────────────────────────────


def test_agent_missing_whatsapp_number_returns_500(fast_env, store_mocks, svc_mocks, client):
    svc_mocks.agents_lookup.return_value = {
        "id": _TEST_AGENT_ID, "client_id": _TEST_CLIENT_ID,
        "whatsapp_number": "",
    }
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 500
    assert resp.json()["error_code"] == "agent_misconfigured"
    assert svc_mocks.twilio_send.await_count == 0


def test_agent_row_missing_returns_500(fast_env, store_mocks, svc_mocks, client):
    svc_mocks.agents_lookup.return_value = None
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 500
    assert resp.json()["error_code"] == "agent_misconfigured"
    assert svc_mocks.twilio_send.await_count == 0


# ── 8. Empty message ─────────────────────────────────────────────────────


def test_empty_message_after_trim_returns_400(fast_env, store_mocks, svc_mocks, client):
    body = _valid_body()
    body["message"] = "    "  # all-whitespace
    resp = _post(client, body=body)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_body"
    assert svc_mocks.twilio_send.await_count == 0


def test_zero_length_message_returns_400(fast_env, store_mocks, svc_mocks, client):
    body = _valid_body()
    body["message"] = ""
    resp = _post(client, body=body)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_body"
    assert svc_mocks.twilio_send.await_count == 0


# ── 9. Too long ──────────────────────────────────────────────────────────


def test_too_long_message_returns_400(fast_env, store_mocks, svc_mocks, client):
    body = _valid_body()
    body["message"] = "x" * 1501
    resp = _post(client, body=body)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_body"
    assert svc_mocks.twilio_send.await_count == 0


# ── 10. Invalid idempotency key ──────────────────────────────────────────


def test_missing_idempotency_key_returns_400(fast_env, store_mocks, svc_mocks, client):
    headers = {
        "X-Maya-Watch-Key": _TEST_INTERNAL_KEY,
        "X-Maya-Watch-Acted-By": "op-1",
        # No idempotency key
    }
    resp = client.post("/maya-watch/messages/send", json=_valid_body(), headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_idempotency_key"
    assert svc_mocks.twilio_send.await_count == 0


def test_non_uuid_idempotency_key_returns_400(fast_env, store_mocks, svc_mocks, client):
    resp = _post(client, body=_valid_body(), idempotency_key="not-a-uuid")
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_idempotency_key"


def test_uuid_v1_rejected_as_invalid_idempotency_key(fast_env, store_mocks, svc_mocks, client):
    # v1 UUID — version digit is 1, our regex requires 4
    resp = _post(client, body=_valid_body(), idempotency_key="11111111-1111-1111-8111-111111111111")
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_idempotency_key"


# ── 11. Duplicate idempotency ────────────────────────────────────────────


def test_duplicate_idempotency_returns_existing_no_twilio(fast_env, store_mocks, svc_mocks, client):
    # Pre-existing row matches the key.
    store_mocks.find_idempotency.return_value = {
        "id": 99999,
        "lead_id": _TEST_LEAD_ID,
        "client_id": _TEST_CLIENT_ID,
        "agent_id": _TEST_AGENT_ID,
        "direction": "out",
        "body": "previously sent",
        "sid": "SMpreviously_sent",
        "status": "delivered",
        "ts": "2026-05-09T11:00:00+00:00",
        "source": "operator_preview",
        "metadata": {
            "idempotency_key": _TEST_IDEMPOTENCY_KEY,
            "decision_id": "decision:awaiting_attention:+972500000792",
            "sent_by": "operator-id-1",
        },
    }
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["already_sent"] is True
    assert body["message_id"] == 99999
    assert body["twilio_sid"] == "SMpreviously_sent"
    assert body["status"] == "delivered"
    # Crucial: NO Twilio call, NO new insert.
    assert svc_mocks.twilio_send.await_count == 0
    assert store_mocks.insert_outbound.await_count == 0


# ── 12. Twilio failure ───────────────────────────────────────────────────


def test_twilio_failure_returns_502_no_insert(fast_env, store_mocks, svc_mocks, client):
    svc_mocks.twilio_send.side_effect = RuntimeError("Twilio rate limit exceeded")
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 502
    body = resp.json()
    assert body["error_code"] == "twilio_send_failed"
    assert "Twilio rate limit exceeded" in body["detail"]
    # No row inserted on Twilio failure.
    assert store_mocks.insert_outbound.await_count == 0


# ── 13. BASE_URL missing ─────────────────────────────────────────────────


def test_base_url_missing_returns_500_no_twilio(fast_env, store_mocks, svc_mocks, client, monkeypatch):
    monkeypatch.delenv("BASE_URL", raising=False)
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 500
    assert resp.json()["error_code"] == "base_url_not_configured"
    assert svc_mocks.twilio_send.await_count == 0


def test_twilio_creds_missing_returns_500_no_twilio(fast_env, store_mocks, svc_mocks, client, monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 500
    assert resp.json()["error_code"] == "twilio_not_configured"
    assert svc_mocks.twilio_send.await_count == 0


# ── Stage 10D — allowlist gate ──────────────────────────────────────────


def test_allowlist_missing_returns_403_no_twilio_no_insert(
    fast_env, store_mocks, svc_mocks, client, monkeypatch,
):
    """Env var unset → fail closed: 403, no Twilio, no insert."""
    monkeypatch.delenv("MAYA_WATCH_SEND_ALLOWED_PHONES", raising=False)
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 403
    body = resp.json()
    assert body["ok"] is False
    assert body["error_code"] == "send_not_allowed"
    assert body["message"] == "Operator send is not enabled for this phone"
    assert svc_mocks.twilio_send.await_count == 0
    assert store_mocks.insert_outbound.await_count == 0


def test_allowlist_empty_returns_403_no_twilio_no_insert(
    fast_env, store_mocks, svc_mocks, client, monkeypatch,
):
    """Env var present but empty (or whitespace-only) → fail closed."""
    monkeypatch.setenv("MAYA_WATCH_SEND_ALLOWED_PHONES", "   ")
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "send_not_allowed"
    assert svc_mocks.twilio_send.await_count == 0
    assert store_mocks.insert_outbound.await_count == 0


def test_allowlist_excludes_lead_phone_returns_403(
    fast_env, store_mocks, svc_mocks, client, monkeypatch,
):
    """Allowlist contains other phones but not the lead's → 403."""
    monkeypatch.setenv(
        "MAYA_WATCH_SEND_ALLOWED_PHONES",
        "+972500000111,+972500000222",  # neither matches _TEST_PHONE
    )
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "send_not_allowed"
    assert svc_mocks.twilio_send.await_count == 0
    assert store_mocks.insert_outbound.await_count == 0


def test_allowlist_includes_lead_phone_continues_to_send(
    fast_env, store_mocks, svc_mocks, client, monkeypatch,
):
    """Allowlist explicitly includes lead.phone → normal happy path."""
    monkeypatch.setenv(
        "MAYA_WATCH_SEND_ALLOWED_PHONES",
        f"+972500000111,{_TEST_PHONE},+972500000222",
    )
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert svc_mocks.twilio_send.await_count == 1
    assert store_mocks.insert_outbound.await_count == 1


def test_allowlist_trims_whitespace_around_entries(
    fast_env, store_mocks, svc_mocks, client, monkeypatch,
):
    """Spaces around comma-separated entries are stripped before match."""
    monkeypatch.setenv(
        "MAYA_WATCH_SEND_ALLOWED_PHONES",
        f"  +972500000111 ,  {_TEST_PHONE}  ,  +972500000222 ",
    )
    resp = _post(client, body=_valid_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert svc_mocks.twilio_send.await_count == 1


def test_caller_supplied_phone_cannot_bypass_allowlist(
    fast_env, store_mocks, svc_mocks, client, monkeypatch,
):
    """A `phone` field in the request body is ignored — server uses
    only lead.phone (resolved from lead_id), so a caller can't smuggle
    an allowlisted phone past the gate when their lead is unallowed."""
    # Allowlist a DIFFERENT phone than the lead's. Caller will try to
    # bypass by adding that phone to the body.
    allowlisted_other = "+972500000999"
    monkeypatch.setenv("MAYA_WATCH_SEND_ALLOWED_PHONES", allowlisted_other)
    # Body includes an extra phone field — this should be silently ignored.
    body = _valid_body()
    body["phone"] = allowlisted_other  # caller's bypass attempt
    resp = _post(client, body=body)
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "send_not_allowed"
    # No Twilio, no insert. The orchestrator only ever consulted
    # store_mocks.get_lead.return_value["phone"] (= _TEST_PHONE), never
    # the body's phone field.
    assert svc_mocks.twilio_send.await_count == 0
    assert store_mocks.insert_outbound.await_count == 0

"""
Tests for app/routes/maya_actions_execute.py.

Mocks every external dependency:
- Supabase auth verification (httpx.AsyncClient.get) inside _verify_bearer.
- execute_one in the route module (patched to record args, never invokes
  the real service / Supabase / Twilio).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import maya_actions_execute as route_mod


# ── App fixture ──────────────────────────────────────────────────────────────


@pytest.fixture
def app_with_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service_test_key")
    # Re-read module-level env caches after monkeypatch.
    monkeypatch.setattr(route_mod, "_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(route_mod, "_SUPABASE_SERVICE_KEY", "service_test_key")
    app = FastAPI()
    app.include_router(route_mod.router)
    return app


@pytest.fixture
def client(app_with_env):
    return TestClient(app_with_env)


def _auth_response_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": "user-1", "user_metadata": {"client_id": "c1"}}
    return resp


def _auth_response_fail(status: int = 401):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"error": "unauthorized"}
    return resp


class _AuthAsyncClient:
    """Replaces httpx.AsyncClient inside _verify_bearer."""

    next_get_response: MagicMock | None = None
    next_get_exception: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        if type(self).next_get_exception is not None:
            raise type(self).next_get_exception
        return type(self).next_get_response


@pytest.fixture(autouse=True)
def _reset_auth_client():
    _AuthAsyncClient.next_get_response = None
    _AuthAsyncClient.next_get_exception = None
    yield
    _AuthAsyncClient.next_get_response = None
    _AuthAsyncClient.next_get_exception = None


# ── 1. missing Authorization → 401, execute_one not called ──────────────────


def test_missing_authorization_returns_401(client):
    with patch.object(route_mod, "execute_one", new=AsyncMock()) as exec_mock:
        r = client.post("/maya-actions/s1/execute", json={"expected_version": 1})
    assert r.status_code == 401
    exec_mock.assert_not_called()
    assert "Authorization" not in r.text  # banner-style leak guard


# ── 2. malformed Authorization → 401 ────────────────────────────────────────


def test_malformed_authorization_returns_401(client):
    with patch.object(route_mod, "execute_one", new=AsyncMock()) as exec_mock:
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 1},
            headers={"Authorization": "NotBearer xyz"},
        )
    assert r.status_code == 401
    exec_mock.assert_not_called()


def test_authorization_with_empty_token_returns_401(client):
    with patch.object(route_mod, "execute_one", new=AsyncMock()) as exec_mock:
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 1},
            headers={"Authorization": "Bearer "},
        )
    assert r.status_code == 401
    exec_mock.assert_not_called()


# ── 3. auth verification fails (non-200 from Supabase) → 401 ────────────────


def test_auth_verification_non_200_returns_401(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_fail(401)
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    with patch.object(route_mod, "execute_one", new=AsyncMock()) as exec_mock:
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 1},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 401
    exec_mock.assert_not_called()


def test_auth_network_error_returns_401(client, monkeypatch):
    import httpx as _httpx
    _AuthAsyncClient.next_get_exception = _httpx.ConnectError("simulated")
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    with patch.object(route_mod, "execute_one", new=AsyncMock()) as exec_mock:
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 1},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 401
    exec_mock.assert_not_called()


# ── 4. valid auth + valid body → execute_one called with exact args ────────


def test_valid_auth_and_body_invokes_execute_one_with_token(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    exec_mock = AsyncMock(return_value={"ok": True, "error_code": "ok",
                                        "suggestion": {"id": "s1", "status": "executed"}})
    with patch.object(route_mod, "execute_one", new=exec_mock):
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 7},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 200
    assert exec_mock.call_count == 1
    kwargs = exec_mock.call_args.kwargs
    assert kwargs["suggestion_id"] == "s1"
    assert kwargs["expected_version"] == 7
    assert kwargs["user_jwt"] == "JWT_VALUE"


# ── 5. ok=true → HTTP 200 with envelope ─────────────────────────────────────


def test_ok_true_returns_200_with_envelope(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    envelope = {"ok": True, "error_code": "ok",
                "suggestion": {"id": "s1", "status": "executed", "version": 8}}
    with patch.object(route_mod, "execute_one", new=AsyncMock(return_value=envelope)):
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 7},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 200
    assert r.json() == envelope


# ── 6. forbidden → 403 ──────────────────────────────────────────────────────


def test_executor_forbidden_returns_403(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    envelope = {"ok": False, "error_code": "forbidden", "error_he": "אין הרשאה"}
    with patch.object(route_mod, "execute_one", new=AsyncMock(return_value=envelope)):
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 7},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 403
    # FastAPI wraps detail under "detail" when HTTPException is raised with dict
    assert r.json()["detail"]["error_code"] == "forbidden"


# ── 7. not_found → 404 ──────────────────────────────────────────────────────


def test_executor_not_found_returns_404(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    envelope = {"ok": False, "error_code": "not_found", "error_he": "לא נמצא"}
    with patch.object(route_mod, "execute_one", new=AsyncMock(return_value=envelope)):
        r = client.post(
            "/maya-actions/missing/execute",
            json={"expected_version": 1},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "not_found"


# ── 8. not_authenticated → 401 ──────────────────────────────────────────────


def test_executor_not_authenticated_returns_401(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    envelope = {"ok": False, "error_code": "not_authenticated", "error_he": "..."}
    with patch.object(route_mod, "execute_one", new=AsyncMock(return_value=envelope)):
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 1},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 401


# ── 9. config_missing / invalid_message → 200 ok=false ─────────────────────


def test_executor_config_missing_returns_200_ok_false(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    envelope = {"ok": False, "error_code": "config_missing",
                "error_he": "תצורה חסרה",
                "suggestion": {"id": "s1", "status": "failed", "version": 9}}
    with patch.object(route_mod, "execute_one", new=AsyncMock(return_value=envelope)):
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 1},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 200
    assert r.json() == envelope


def test_executor_invalid_message_returns_200_ok_false(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    envelope = {"ok": False, "error_code": "invalid_message", "error_he": "..."}
    with patch.object(route_mod, "execute_one", new=AsyncMock(return_value=envelope)):
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 1},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 200
    assert r.json()["ok"] is False


# ── 10. bool expected_version rejected ──────────────────────────────────────


def test_bool_expected_version_rejected(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    with patch.object(route_mod, "execute_one", new=AsyncMock()) as exec_mock:
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": True},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    # Either 422 (pydantic / explicit guard) or any 4xx; bool must NOT reach executor.
    assert 400 <= r.status_code < 500
    exec_mock.assert_not_called()


def test_missing_expected_version_rejected(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    with patch.object(route_mod, "execute_one", new=AsyncMock()) as exec_mock:
        r = client.post(
            "/maya-actions/s1/execute",
            json={},
            headers={"Authorization": "Bearer JWT_VALUE"},
        )
    assert r.status_code == 422
    exec_mock.assert_not_called()


# ── 11. no JWT/Authorization leaked in response ────────────────────────────


def test_no_jwt_or_authorization_header_in_any_response(client, monkeypatch):
    _AuthAsyncClient.next_get_response = _auth_response_ok()
    monkeypatch.setattr(route_mod.httpx, "AsyncClient", _AuthAsyncClient)
    envelope = {"ok": True, "error_code": "ok",
                "suggestion": {"id": "s1", "status": "executed"}}
    with patch.object(route_mod, "execute_one", new=AsyncMock(return_value=envelope)):
        r = client.post(
            "/maya-actions/s1/execute",
            json={"expected_version": 7},
            headers={"Authorization": "Bearer SECRET_JWT_VALUE"},
        )
    assert "SECRET_JWT_VALUE" not in r.text
    # FastAPI may echo back an "Authorization" header name in CORS preflight
    # contexts; for a regular POST body we don't expect it.
    assert "SECRET_JWT_VALUE" not in str(r.headers)

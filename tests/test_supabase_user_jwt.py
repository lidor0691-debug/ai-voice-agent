"""
Tests for app/integrations/supabase_user_jwt.py.

No real network calls. httpx.AsyncClient is monkeypatched so the helper
never opens a socket. The JWT and service-role key invariants are
asserted by inspecting the captured request shape.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations import supabase_user_jwt
from app.integrations.supabase_user_jwt import user_supabase_rpc


def _mock_response(status_code: int, json_value=None, text: str = "") -> MagicMock:
    """Build a fake httpx.Response-shaped object."""
    resp = MagicMock()
    resp.status_code = status_code
    if json_value is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json_value
    resp.text = text
    return resp


class _FakeAsyncClient:
    """Replaces httpx.AsyncClient for monkeypatching.

    Records the post() call args and returns the configured response.
    """

    last_post_kwargs: dict | None = None
    last_post_url: str | None = None
    next_response: MagicMock | None = None
    next_exception: Exception | None = None

    def __init__(self, *args, **kwargs):
        self._init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        type(self).last_post_url = url
        type(self).last_post_kwargs = kwargs
        if type(self).next_exception is not None:
            raise type(self).next_exception
        return type(self).next_response


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeAsyncClient.last_post_kwargs = None
    _FakeAsyncClient.last_post_url = None
    _FakeAsyncClient.next_response = None
    _FakeAsyncClient.next_exception = None
    yield
    _FakeAsyncClient.last_post_kwargs = None
    _FakeAsyncClient.last_post_url = None
    _FakeAsyncClient.next_response = None
    _FakeAsyncClient.next_exception = None


@pytest.fixture
def patched_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon_test_key")
    monkeypatch.setattr(supabase_user_jwt.httpx, "AsyncClient", _FakeAsyncClient)


# ── env-missing cases ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_supabase_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    out = await user_supabase_rpc("jwt", "fn", {})
    assert out["ok"] is False
    assert out["error_code"] == "config_missing"
    assert out["error_he"] == "תצורת Supabase חסרה."
    assert _FakeAsyncClient.last_post_url is None  # no network attempted


@pytest.mark.asyncio
async def test_missing_anon_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    out = await user_supabase_rpc("jwt", "fn", {})
    assert out["ok"] is False
    assert out["error_code"] == "config_missing"


# ── invalid input cases ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_jwt(patched_env):
    out = await user_supabase_rpc("", "fn", {})
    assert out["ok"] is False
    assert out["error_code"] == "invalid_input"
    assert _FakeAsyncClient.last_post_url is None


@pytest.mark.asyncio
async def test_whitespace_jwt(patched_env):
    out = await user_supabase_rpc("   ", "fn", {})
    assert out["ok"] is False
    assert out["error_code"] == "invalid_input"


@pytest.mark.asyncio
async def test_empty_fn(patched_env):
    out = await user_supabase_rpc("jwt", "", {})
    assert out["ok"] is False
    assert out["error_code"] == "invalid_input"


@pytest.mark.asyncio
async def test_params_not_dict(patched_env):
    out = await user_supabase_rpc("jwt", "fn", "not_a_dict")  # type: ignore[arg-type]
    assert out["ok"] is False
    assert out["error_code"] == "invalid_input"


# ── happy path ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_returns_envelope_unchanged(patched_env):
    _FakeAsyncClient.next_response = _mock_response(
        200,
        json_value={"ok": True, "error_code": "ok", "suggestion": {"id": "abc"}},
    )
    out = await user_supabase_rpc("THE_JWT", "claim_action_for_execution",
                                  {"p_suggestion_id": "abc"})
    assert out == {"ok": True, "error_code": "ok", "suggestion": {"id": "abc"}}

    # URL shape
    assert _FakeAsyncClient.last_post_url == (
        "https://example.supabase.co/rest/v1/rpc/claim_action_for_execution"
    )

    # Headers contract — apikey is the anon key, Authorization is Bearer <jwt>
    headers = _FakeAsyncClient.last_post_kwargs["headers"]
    assert headers["apikey"] == "anon_test_key"
    assert headers["Authorization"] == "Bearer THE_JWT"
    assert headers["Content-Type"] == "application/json"

    # Body is the params dict, untouched
    assert _FakeAsyncClient.last_post_kwargs["json"] == {"p_suggestion_id": "abc"}


# ── 4xx/5xx non-2xx response ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_2xx_returns_safe_envelope(patched_env):
    _FakeAsyncClient.next_response = _mock_response(
        403,
        text="forbidden: row-level security",
    )
    out = await user_supabase_rpc("jwt", "fn", {})
    assert out["ok"] is False
    assert out["error_code"] == "supabase_rpc_error"
    assert out["error_he"] == "פעולת Supabase נכשלה."
    assert out["status_code"] == 403
    assert "forbidden" in out["detail"]


@pytest.mark.asyncio
async def test_non_2xx_detail_bounded_to_500_chars(patched_env):
    long_body = "X" * 2000
    _FakeAsyncClient.next_response = _mock_response(500, text=long_body)
    out = await user_supabase_rpc("jwt", "fn", {})
    assert out["error_code"] == "supabase_rpc_error"
    assert len(out["detail"]) == 500


@pytest.mark.asyncio
async def test_non_2xx_detail_never_contains_jwt_or_auth_header(patched_env):
    # Server might echo headers in error bodies. Real Supabase doesn't, but
    # this test enforces that our helper never *constructs* a detail using
    # the JWT or Authorization header. Detail comes solely from response body.
    _FakeAsyncClient.next_response = _mock_response(401, text="unauthenticated")
    out = await user_supabase_rpc("SECRET_JWT_VALUE", "fn", {})
    assert "SECRET_JWT_VALUE" not in (out.get("detail") or "")
    assert "Authorization" not in (out.get("detail") or "")


# ── network errors ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_network_timeout_returns_network_error(patched_env):
    _FakeAsyncClient.next_exception = httpx.ReadTimeout("simulated")
    out = await user_supabase_rpc("jwt", "fn", {})
    assert out["ok"] is False
    assert out["error_code"] == "supabase_rpc_network_error"
    assert out["error_he"] == "לא ניתן להתחבר ל-Supabase."


@pytest.mark.asyncio
async def test_network_connect_error_returns_network_error(patched_env):
    _FakeAsyncClient.next_exception = httpx.ConnectError("simulated")
    out = await user_supabase_rpc("jwt", "fn", {})
    assert out["error_code"] == "supabase_rpc_network_error"


# ── success body shape variations ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_with_non_dict_json(patched_env):
    # PostgREST RPCs that RETURN scalar/array would come back as non-dict.
    _FakeAsyncClient.next_response = _mock_response(200, json_value=[1, 2, 3])
    out = await user_supabase_rpc("jwt", "fn", {})
    assert out["ok"] is True
    assert out["data"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_success_with_invalid_json_body(patched_env):
    # 2xx but the body isn't valid JSON (unlikely from Supabase, but defensive).
    _FakeAsyncClient.next_response = _mock_response(200, json_value=None,
                                                    text="not json")
    out = await user_supabase_rpc("jwt", "fn", {})
    assert out["ok"] is False
    assert out["error_code"] == "supabase_rpc_error"
    assert out["status_code"] == 200


# ── URL handling ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trailing_slash_in_url_is_normalized(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(supabase_user_jwt.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.next_response = _mock_response(200, json_value={"ok": True})
    await user_supabase_rpc("jwt", "fn", {})
    assert _FakeAsyncClient.last_post_url == (
        "https://example.supabase.co/rest/v1/rpc/fn"
    )

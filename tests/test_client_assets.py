"""
Tests for app/services/client_assets.py
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_returns_empty_when_supabase_not_configured():
    from app.services.client_assets import get_assets_by_trigger
    with patch("app.services.client_assets._is_configured", return_value=False):
        result = await get_assets_by_trigger("client-123", "trial_booked")
    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_client_id_is_blank():
    from app.services.client_assets import get_assets_by_trigger
    with patch("app.services.client_assets._is_configured", return_value=True):
        result = await get_assets_by_trigger("", "trial_booked")
    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_trigger_key_is_blank():
    from app.services.client_assets import get_assets_by_trigger
    with patch("app.services.client_assets._is_configured", return_value=True):
        result = await get_assets_by_trigger("client-123", "")
    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_on_network_error():
    from app.services.client_assets import get_assets_by_trigger

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("app.services.client_assets._is_configured", return_value=True):
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_assets_by_trigger("client-123", "trial_booked")

    assert result == []


@pytest.mark.asyncio
async def test_returns_assets_list_on_success():
    from app.services.client_assets import get_assets_by_trigger

    mock_assets = [
        {"id": "a1", "asset_name": "confirm", "asset_type": "text",
         "content": "Hi!", "sort_order": 0, "enabled": True},
        {"id": "a2", "asset_name": "payment", "asset_type": "link",
         "content": "https://pay.example.com", "sort_order": 1, "enabled": True},
    ]

    mock_response = MagicMock()
    mock_response.json.return_value = mock_assets
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.client_assets._is_configured", return_value=True):
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_assets_by_trigger("client-123", "trial_booked")

    assert len(result) == 2
    assert result[0]["asset_name"] == "confirm"
    assert result[1]["asset_type"] == "link"


# ── route tests ───────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_test_client():
    from app.routes.assets import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_trigger_route_returns_200_with_empty_assets():
    with patch("app.routes.assets.get_assets_by_trigger", new=AsyncMock(return_value=[])):
        client = _make_test_client()
        resp = client.post("/trigger", json={
            "client_id":   "client-abc",
            "trigger_key": "trial_booked",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["assets"] == []
    assert body["client_id"] == "client-abc"
    assert body["trigger_key"] == "trial_booked"


def test_trigger_route_returns_assets_and_echoes_context():
    mock_assets = [
        {"id": "a1", "asset_name": "confirm", "asset_type": "text", "content": "Hi!"}
    ]
    with patch("app.routes.assets.get_assets_by_trigger", new=AsyncMock(return_value=mock_assets)):
        client = _make_test_client()
        resp = client.post("/trigger", json={
            "client_id":      "client-abc",
            "trigger_key":    "trial_booked",
            "trigger_source": "make",
            "event_id":       "evt-001",
            "context":        {"name": "David", "phone": "+972500000000"},
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["assets"][0]["asset_name"] == "confirm"
    assert body["trigger_source"] == "make"
    assert body["event_id"] == "evt-001"
    assert body["context"]["name"] == "David"


def test_trigger_route_requires_client_id():
    with patch("app.routes.assets.get_assets_by_trigger", new=AsyncMock(return_value=[])):
        client = _make_test_client()
        resp = client.post("/trigger", json={"trigger_key": "trial_booked"})
    assert resp.status_code == 422  # Pydantic validation error


def test_trigger_route_requires_trigger_key():
    with patch("app.routes.assets.get_assets_by_trigger", new=AsyncMock(return_value=[])):
        client = _make_test_client()
        resp = client.post("/trigger", json={"client_id": "client-abc"})
    assert resp.status_code == 422

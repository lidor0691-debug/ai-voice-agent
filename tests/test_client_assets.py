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

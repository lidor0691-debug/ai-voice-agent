"""
Focused tests for app/services/whatsapp_reply.py::_record_inbound_lead_timestamp
— the inbound-WhatsApp lead-timestamp writer (Phase 3.12C-4).

No real Supabase/Twilio/network. httpx.AsyncClient is mocked; we assert the
PATCH is scoped by (phone, client_id), carries last_whatsapp_inbound_at, is
skipped without a client_id, and never raises on failure.
"""
from __future__ import annotations

import os
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the module-level cache picks up the test env even if imported earlier.
import app.services.whatsapp_reply as wr


def _patch_async_client(patch_mock: AsyncMock):
    """Return a context manager that replaces httpx.AsyncClient in wr with a
    fake whose .patch is `patch_mock`."""
    fake_client = MagicMock()
    fake_client.patch = patch_mock
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_client)
    fake_cm.__aexit__ = AsyncMock(return_value=False)
    return patch.object(wr.httpx, "AsyncClient", MagicMock(return_value=fake_cm))


@pytest.mark.asyncio
async def test_inbound_update_scoped_by_phone_and_client():
    patch_mock = AsyncMock()
    with _patch_async_client(patch_mock), \
         patch.object(wr, "_SUPABASE_URL", "http://sb"), \
         patch.object(wr, "_SUPABASE_SERVICE_KEY", "svc"):
        await wr._record_inbound_lead_timestamp("client-1", "+15550009999", "2026-05-25T10:00:00+00:00")

    patch_mock.assert_awaited_once()
    _, kwargs = patch_mock.call_args
    # Scoped by BOTH phone and client_id (no cross-tenant phone-only update)
    assert kwargs["params"]["phone"] == "eq.+15550009999"
    assert kwargs["params"]["client_id"] == "eq.client-1"
    # Sets the inbound timestamp
    assert kwargs["json"] == {"last_whatsapp_inbound_at": "2026-05-25T10:00:00+00:00"}
    # Service-role headers present (built inline)
    assert kwargs["headers"]["apikey"] == "svc"


@pytest.mark.asyncio
async def test_skipped_without_client_id():
    patch_mock = AsyncMock()
    with _patch_async_client(patch_mock):
        await wr._record_inbound_lead_timestamp(None, "+15550009999", "2026-05-25T10:00:00+00:00")
        await wr._record_inbound_lead_timestamp("", "+15550009999", "2026-05-25T10:00:00+00:00")
    # Never attempts a phone-only update when client_id is unknown
    patch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_phone_passed_through_verbatim():
    # The caller normalizes (strips 'whatsapp:') before calling; the helper must
    # use the phone it is given verbatim in the scoped filter.
    patch_mock = AsyncMock()
    with _patch_async_client(patch_mock), \
         patch.object(wr, "_SUPABASE_URL", "http://sb"), \
         patch.object(wr, "_SUPABASE_SERVICE_KEY", "svc"):
        await wr._record_inbound_lead_timestamp("c1", "+972524620550", "2026-05-25T10:00:00+00:00")
    _, kwargs = patch_mock.call_args
    assert kwargs["params"]["phone"] == "eq.+972524620550"


@pytest.mark.asyncio
async def test_failure_is_non_fatal():
    patch_mock = AsyncMock(side_effect=RuntimeError("supabase down"))
    with _patch_async_client(patch_mock), \
         patch.object(wr, "_SUPABASE_URL", "http://sb"), \
         patch.object(wr, "_SUPABASE_SERVICE_KEY", "svc"):
        # Must NOT raise — pipeline continuity is required.
        result = await wr._record_inbound_lead_timestamp("c1", "+15550009999", "2026-05-25T10:00:00+00:00")
    assert result is None

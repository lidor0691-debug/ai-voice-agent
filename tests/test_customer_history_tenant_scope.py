"""
Tenant-scoped call history — closes the shared call_logs read leak.

get_customer_history() previously matched call_logs by caller phone ALONE, so a
number that had called one tenant (e.g. Roi) would show up as an existing
customer for a DIFFERENT tenant (e.g. the demo) that happened to be called from
the same phone. call_logs carries agent_id (one active agent per tenant), so the
lookup is now scoped by agent_id when the caller passes it.

Proven here:
  • the query is scoped by agent_id when provided (and only then);
  • a phone that called Roi is NOT recognized as existing for the demo tenant;
  • Roi's own existing-customer recognition is unchanged.
"""
from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")

import pytest

import app.services.voice_shared as vs

ROI_AGENT = "5e28e7ec-ec83-4683-af50-3749115cdec7"
DEMO_AGENT = "b9e5644b-d40a-4df8-a3f4-39325bbc9ead"
ROI_PHONE = "+972500000000"
BEFORE = "2026-07-29T00:00:00+00:00"


# ── pure query-param builder ──────────────────────────────────────────────────
class TestHistoryParams:
    def test_includes_agent_id_when_provided(self):
        p = vs._customer_history_params(ROI_PHONE, BEFORE, agent_id=ROI_AGENT)
        assert p["phone_number"] == f"eq.{ROI_PHONE}"
        assert p["created_at"] == f"lt.{BEFORE}"
        assert p["agent_id"] == f"eq.{ROI_AGENT}"

    def test_omits_agent_id_when_absent(self):
        for aid in (None, "", "   "):
            p = vs._customer_history_params(ROI_PHONE, BEFORE, agent_id=aid)
            assert "agent_id" not in p


# ── end-to-end cross-tenant isolation (fake Supabase transport) ───────────────
class _FakeResp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self._rows


class _FakeClient:
    """Returns rows only for the agent_id the query is scoped to — mirroring a
    real call_logs table where each row belongs to exactly one agent."""

    def __init__(self, db):
        self._db = db

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        params = params or {}
        aid = params.get("agent_id", "")
        key = aid.split("eq.", 1)[-1] if aid.startswith("eq.") else None
        if key is None:  # no scoping → every row for that phone (the OLD leak)
            rows = [r for rs in self._db.values() for r in rs]
        else:
            rows = self._db.get(key, [])
        return _FakeResp(rows)


@pytest.fixture
def fake_calllogs(monkeypatch):
    # Roi has 2 prior calls from ROI_PHONE; the demo agent has none.
    db = {
        ROI_AGENT: [
            {"created_at": "2026-07-01T10:00:00+00:00"},
            {"created_at": "2026-06-01T10:00:00+00:00"},
        ],
    }
    monkeypatch.setattr(vs.httpx, "AsyncClient", _FakeClient(db))
    return db


class TestCrossTenantIsolation:
    @pytest.mark.asyncio
    async def test_roi_number_is_new_for_demo_tenant(self, fake_calllogs):
        res = await vs.get_customer_history(ROI_PHONE, BEFORE, agent_id=DEMO_AGENT)
        assert res["customer_status"] == "לקוח חדש"
        assert res["prior_count"] == 0

    @pytest.mark.asyncio
    async def test_roi_recognizes_its_own_customer(self, fake_calllogs):
        res = await vs.get_customer_history(ROI_PHONE, BEFORE, agent_id=ROI_AGENT)
        assert res["customer_status"] == "לקוח קיים"
        assert res["prior_count"] == 2

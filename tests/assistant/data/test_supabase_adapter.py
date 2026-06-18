"""Tests for the dormant assistant Supabase adapter. TEST-ONLY.

No live DB: the single HTTP seam ``_rest_request`` is monkeypatched with a fake
that serves seeded PostgREST-shaped rows. Async adapter functions are driven via
``asyncio.run`` so no pytest-asyncio plugin is required.

Also includes a lockstep test asserting the migration's CHECK domains match the
``contract.py`` enums, so the SQL schema and the Python vocabulary can't drift.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.assistant.data import supabase_adapter as adapter
from app.assistant.nlp.contract import (
    MessageType,
    ParseStatus,
    ParsedIntent,
    RecipientType,
    SendPlan,
    TEMPLATE_TYPES,
)

OWNER = "11111111-1111-1111-1111-111111111111"


# ── seeded fake for the HTTP seam ─────────────────────────────────────────────

def _strip(eq: str) -> str:
    return eq[3:] if eq.startswith("eq.") else eq


def make_fake_rest(contacts=None, templates=None, capture=None):
    contacts = contacts or []
    templates = templates or []

    async def fake(method, table, *, params=None, json=None, prefer="return=representation"):
        if capture is not None:
            capture.append({"method": method, "table": table, "params": params, "json": json})
        params = params or {}
        if method == "GET" and table == adapter.TABLE_CONTACTS:
            name = _strip(params.get("name", ""))
            owner = _strip(params.get("owner_id", ""))
            matched = [
                c for c in contacts
                if c["name"] == name and c["owner_id"] == owner
                and c.get("status", "active") == "active"
            ]
            return matched[:1]
        if method == "GET" and table == adapter.TABLE_TEMPLATES:
            owner = _strip(params.get("owner_id", ""))
            return [
                {"message_type": t["message_type"]}
                for t in templates
                if t["owner_id"] == owner and t.get("status", "active") == "active"
            ]
        if method == "POST":
            return [{"id": "new-id-123"}]
        if method == "PATCH":
            return []
        return []

    return fake


def _intent(recipient_name="דנה", recipient_type=RecipientType.CLIENT,
            message_type=MessageType.CUSTOM):
    return ParsedIntent(
        status=ParseStatus.PARSED,
        recipient_name=recipient_name,
        recipient_type=recipient_type,
        message_type=message_type,
        scheduled_at_local="2026-06-16T10:00:00",
        is_explicit_time=True,
    )


def _contact_row(name="דנה", recipient_type="client", phone="+972500000001",
                 last_inbound_at=None, status="active"):
    return {
        "owner_id": OWNER, "name": name, "recipient_type": recipient_type,
        "phone": phone, "last_inbound_at": last_inbound_at, "status": status,
    }


# ── resolve_with_data: all four send plans + unknown contact ──────────────────

def test_resolve_group_is_group_manual(monkeypatch):
    monkeypatch.setattr(adapter, "_rest_request",
        make_fake_rest(contacts=[_contact_row(name="קבוצת בוקר", recipient_type="group", phone=None)]))
    plan = asyncio.run(adapter.resolve_with_data(
        _intent(recipient_name="קבוצת בוקר", recipient_type=RecipientType.GROUP), OWNER))
    assert plan.send_plan == SendPlan.GROUP_MANUAL


def test_resolve_no_phone_is_manual_fallback(monkeypatch):
    monkeypatch.setattr(adapter, "_rest_request",
        make_fake_rest(contacts=[_contact_row(phone=None)]))
    plan = asyncio.run(adapter.resolve_with_data(_intent(), OWNER))
    assert plan.send_plan == SendPlan.MANUAL_FALLBACK


def test_resolve_unknown_contact_is_manual_fallback(monkeypatch):
    monkeypatch.setattr(adapter, "_rest_request", make_fake_rest(contacts=[]))
    plan = asyncio.run(adapter.resolve_with_data(_intent(recipient_name="מי-שלא-קיים"), OWNER))
    assert plan.send_plan == SendPlan.MANUAL_FALLBACK


def test_resolve_inside_window_is_freeform(monkeypatch):
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    monkeypatch.setattr(adapter, "_rest_request",
        make_fake_rest(contacts=[_contact_row(last_inbound_at=recent)],
                       templates=[{"owner_id": OWNER, "message_type": "agreement"}]))
    plan = asyncio.run(adapter.resolve_with_data(
        _intent(message_type=MessageType.AGREEMENT), OWNER))
    assert plan.send_plan == SendPlan.API_FREEFORM  # window beats template


def test_resolve_outside_window_with_template_is_api_template(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    monkeypatch.setattr(adapter, "_rest_request",
        make_fake_rest(contacts=[_contact_row(last_inbound_at=old)],
                       templates=[{"owner_id": OWNER, "message_type": "agreement"}]))
    plan = asyncio.run(adapter.resolve_with_data(
        _intent(message_type=MessageType.AGREEMENT), OWNER))
    assert plan.send_plan == SendPlan.API_TEMPLATE


def test_resolve_outside_window_no_template_is_manual_fallback(monkeypatch):
    monkeypatch.setattr(adapter, "_rest_request",
        make_fake_rest(contacts=[_contact_row(last_inbound_at=None)], templates=[]))
    plan = asyncio.run(adapter.resolve_with_data(
        _intent(message_type=MessageType.DEPOSIT), OWNER))
    assert plan.send_plan == SendPlan.MANUAL_FALLBACK


# ── within_24h_window unit ────────────────────────────────────────────────────

def test_within_window_recent_true():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(hours=1)).isoformat()
    assert adapter.within_24h_window(recent, now=now) is True


def test_within_window_old_false():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    old = (now - timedelta(hours=25)).isoformat()
    assert adapter.within_24h_window(old, now=now) is False


def test_within_window_none_false():
    assert adapter.within_24h_window(None) is False


def test_within_window_parses_z_suffix():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    assert adapter.within_24h_window("2026-06-15T11:00:00Z", now=now) is True


# ── mappers / reads ───────────────────────────────────────────────────────────

def test_get_contact_by_name_maps_row(monkeypatch):
    monkeypatch.setattr(adapter, "_rest_request",
        make_fake_rest(contacts=[_contact_row()]))
    contact = asyncio.run(adapter.get_contact_by_name(OWNER, "דנה"))
    assert contact is not None
    assert contact.name == "דנה"
    assert contact.recipient_type == RecipientType.CLIENT
    assert contact.phone == "+972500000001"


def test_list_active_templates_returns_enum_set(monkeypatch):
    monkeypatch.setattr(adapter, "_rest_request", make_fake_rest(templates=[
        {"owner_id": OWNER, "message_type": "agreement"},
        {"owner_id": OWNER, "message_type": "deposit"},
        {"owner_id": OWNER, "message_type": "not_a_real_type"},  # ignored
    ]))
    templates = asyncio.run(adapter.list_active_templates(OWNER))
    assert templates == {MessageType.AGREEMENT, MessageType.DEPOSIT}


# ── writes (payload shape via capture) ────────────────────────────────────────

def test_insert_scheduled_message_builds_payload(monkeypatch):
    capture: list = []
    monkeypatch.setattr(adapter, "_rest_request", make_fake_rest(capture=capture))
    new_id = asyncio.run(adapter.insert_scheduled_message(
        OWNER, _intent(message_type=MessageType.AGREEMENT),
        contact_id="c-1", send_plan="api_template", status="scheduled", body="hi"))
    assert new_id == "new-id-123"
    post = [c for c in capture if c["method"] == "POST"][0]
    assert post["table"] == adapter.TABLE_SCHEDULED
    body = post["json"]
    assert body["owner_id"] == OWNER
    assert body["status"] == "scheduled"
    assert body["send_plan"] == "api_template"
    assert body["message_type"] == "agreement"
    assert body["recipient_type"] == "client"


def test_update_scheduled_status_patches_with_timestamp(monkeypatch):
    capture: list = []
    monkeypatch.setattr(adapter, "_rest_request", make_fake_rest(capture=capture))
    approved = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)
    ok = asyncio.run(adapter.update_scheduled_status("m-1", "approved", approved_at=approved))
    assert ok is True
    patch = [c for c in capture if c["method"] == "PATCH"][0]
    assert patch["params"]["id"] == "eq.m-1"
    assert patch["json"]["status"] == "approved"
    assert patch["json"]["approved_at"].startswith("2026-06-15T13:00:00")


def test_log_activity_posts_event(monkeypatch):
    capture: list = []
    monkeypatch.setattr(adapter, "_rest_request", make_fake_rest(capture=capture))
    ok = asyncio.run(adapter.log_activity(OWNER, "reminded_manual", scheduled_message_id="m-1"))
    assert ok is True
    post = [c for c in capture if c["method"] == "POST"][0]
    assert post["table"] == adapter.TABLE_ACTIVITY
    assert post["json"]["event_type"] == "reminded_manual"


# ── error resilience: a None from the seam never raises ───────────────────────

def test_resolve_swallows_seam_failure(monkeypatch):
    async def boom(*a, **k):
        return None  # mimics a swallowed transient error
    monkeypatch.setattr(adapter, "_rest_request", boom)
    plan = asyncio.run(adapter.resolve_with_data(_intent(), OWNER))
    assert plan.send_plan == SendPlan.MANUAL_FALLBACK  # no contact -> safe default


# ── lockstep: migration CHECK domains == contract.py enums ────────────────────

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase" / "migrations" / "create_assistant_foundations.sql"
)


def _check_values(constraint_name: str) -> set:
    """Locate a named CHECK constraint, return the value set of its IN (...) list."""
    sql = _MIGRATION.read_text(encoding="utf-8")
    idx = sql.find(constraint_name)
    assert idx != -1, f"could not locate {constraint_name} in migration"
    m = re.search(r"IN\s*\(([^)]*)\)", sql[idx:])
    assert m, f"no IN (...) list after {constraint_name}"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_migration_exists():
    assert _MIGRATION.is_file()


def test_recipient_type_check_matches_contract():
    assert _check_values("chk_asm_recipient_type") == {e.value for e in RecipientType}


def test_message_type_check_matches_contract():
    assert _check_values("chk_asm_message_type") == {e.value for e in MessageType}


def test_send_plan_check_matches_contract():
    assert _check_values("chk_asm_send_plan") == {e.value for e in SendPlan}


def test_template_message_type_check_matches_template_types():
    assert _check_values("chk_amt_message_type") == {e.value for e in TEMPLATE_TYPES}

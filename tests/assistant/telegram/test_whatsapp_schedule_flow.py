"""Scheduled Telegram->WhatsApp persist flow tests (PR-A). TEST-ONLY.

Fully mocked: the Supabase HTTP seam (``_rest_request``) is stubbed so the REAL
``resolve_contact_candidates`` + ``insert_scheduled_message`` + ``log_activity``
run against seeded rows — no Supabase, no network, and (by construction) no
Twilio/WhatsApp send anywhere in this path. Route tests use TestClient with the
parser + telegram send mocked.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.assistant.telegram.whatsapp_schedule_flow as sched
import app.routes.assistant_telegram_api as tg
from app.assistant.data import supabase_adapter as data
from app.assistant.nlp.contract import MessageType, ParsedIntent, ParseStatus, RecipientType
from app.config.settings import settings

OWNER = "642d2881-9e7d-47cb-8cae-2d6b58a062de"
SECRET = "topsecret"
LOCAL = "2026-07-13T10:00:00"          # naive Asia/Jerusalem wall clock (IDT, +03)
UTC = "2026-07-13T07:00:00+00:00"      # the correct stored UTC instant
RAW_OK = "שלח לקסניה מחר ב-10:00 הודעה: היי קסניה, מזכירים לך לגבי הפגישה"
BODY_OK = "היי קסניה, מזכירים לך לגבי הפגישה"


# ── flow-level tests (handle_scheduled_whatsapp) ──────────────────────────────

class _Rest:
    """Stub for ``data._rest_request`` — serves seeded contacts, records the
    scheduled-message POST and any activity-log POSTs. Never sends anything."""

    def __init__(self, contacts):
        self._contacts = contacts
        self.scheduled_payload = None
        self.activity = []

    async def __call__(self, method, table, *, params=None, json=None,
                       prefer="return=representation"):
        if method == "GET" and table == data.TABLE_CONTACTS:
            return list(self._contacts)
        if method == "POST" and table == data.TABLE_SCHEDULED:
            self.scheduled_payload = json
            return [{"id": "sm-1"}]
        if method == "POST" and table == data.TABLE_ACTIVITY:
            self.activity.append(json)
            return []
        return []


def _install(monkeypatch, contacts):
    stub = _Rest(contacts)
    monkeypatch.setattr(data, "_rest_request", stub)
    return stub


def _contact(name="קסניה", phone="+972538208363", recipient_type="client"):
    return {"id": "c-1", "name": name, "recipient_type": recipient_type,
            "phone": phone, "last_inbound_at": None}


def _intent(recipient_name="קסניה", status=ParseStatus.PARSED, scheduled_at=LOCAL,
            recipient_type=RecipientType.CLIENT, message_type=MessageType.CUSTOM):
    return ParsedIntent(status=status, recipient_name=recipient_name,
                        recipient_type=recipient_type, message_type=message_type,
                        scheduled_at_local=scheduled_at, is_explicit_time=True)


def _run(intent, raw=RAW_OK):
    return asyncio.run(sched.handle_scheduled_whatsapp(
        owner_id=OWNER, intent=intent, raw_command=raw))


def test_persist_happy_path_writes_freeform_scheduled_row(monkeypatch):
    stub = _install(monkeypatch, [_contact()])
    reply = _run(_intent())
    p = stub.scheduled_payload
    assert p is not None
    assert p["owner_id"] == OWNER
    assert p["contact_id"] == "c-1"
    assert p["recipient_type"] == "client"
    assert p["status"] == "scheduled"
    assert p["send_plan"] == "api_freeform"
    assert p["body"] == BODY_OK
    assert p["scheduled_at"] == UTC                    # stored as UTC instant
    assert isinstance(p["parsed_intent"], dict)
    assert p["parsed_intent"]["scheduled_at_local"] == LOCAL
    # audit trail mirrors command_core: resolved -> scheduled
    assert [a["event_type"] for a in stub.activity] == ["resolved", "scheduled"]
    assert "נקבע" in reply and "🧪" not in reply       # real confirmation, not a preview


def test_missing_body_clarifies_and_persists_nothing(monkeypatch):
    stub = _install(monkeypatch, [_contact()])
    reply = _run(_intent(), raw="שלח לקסניה מחר ב-10:00")   # no "הודעה:"
    assert stub.scheduled_payload is None
    assert "תוכן ההודעה" in reply


def test_contact_without_phone_clarifies_and_persists_nothing(monkeypatch):
    stub = _install(monkeypatch, [_contact(phone=None)])
    reply = _run(_intent())
    assert stub.scheduled_payload is None
    assert "אין לו מספר" in reply


def test_unknown_contact_persists_nothing(monkeypatch):
    stub = _install(monkeypatch, [])
    reply = _run(_intent())
    assert stub.scheduled_payload is None
    assert "לא מצאתי" in reply


def test_ambiguous_contact_persists_nothing(monkeypatch):
    stub = _install(monkeypatch, [_contact(), _contact()])
    reply = _run(_intent())
    assert stub.scheduled_payload is None
    assert "יותר מאיש קשר" in reply


def test_missing_send_time_clarifies_and_persists_nothing(monkeypatch):
    stub = _install(monkeypatch, [_contact()])
    reply = _run(_intent(status=ParseStatus.NEEDS_CLARIFICATION, scheduled_at=None))
    assert stub.scheduled_payload is None
    assert "מתי לשלוח" in reply


def test_missing_recipient_clarifies_and_persists_nothing(monkeypatch):
    stub = _install(monkeypatch, [_contact()])
    reply = _run(_intent(status=ParseStatus.NEEDS_CLARIFICATION,
                         recipient_name=None, recipient_type=None, scheduled_at=None))
    assert stub.scheduled_payload is None
    assert "למי לשלוח" in reply


# ── route-level: flag gating + immediate-vs-future ────────────────────────────

class FakeParser:
    def __init__(self, intent):
        self.intent = intent

    def parse(self, raw_command, *, now=None):
        return self.intent


@pytest.fixture(autouse=True)
def _no_real_anthropic(monkeypatch):
    import anthropic

    def _boom(*a, **k):
        raise AssertionError("real AsyncAnthropic must not be constructed in tests")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _boom)


@pytest.fixture(autouse=True)
def _reset_seen():
    tg._SEEN_UPDATE_IDS.clear()
    yield
    tg._SEEN_UPDATE_IDS.clear()


@pytest.fixture
def sent(monkeypatch):
    calls = []

    async def fake_send(chat_id, text):
        calls.append({"chat_id": chat_id, "text": text})
        return True

    monkeypatch.setattr(tg.telegram_client, "send_message", fake_send)
    return calls


def _client():
    app = FastAPI()
    app.include_router(tg.router)
    return TestClient(app)


def _configure(monkeypatch, *, schedule_enabled, dry_run=True, wa_send=False):
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_INTAKE_ENABLED", True)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_DRY_RUN", dry_run)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_ALLOWED_USER_IDS", "111")
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_OWNER_MAP", f"111:{OWNER}")
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_WHATSAPP_SEND_ENABLED", wa_send)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_WHATSAPP_SCHEDULE_ENABLED", schedule_enabled)


def _post(client, text, *, update_id=20):
    body = {"update_id": update_id,
            "message": {"text": text, "from": {"id": 111}, "chat": {"id": 555}}}
    return client.post(tg.WEBHOOK_PATH, json=body, headers={tg.SECRET_HEADER: SECRET})


def test_route_schedule_disabled_future_is_dry_run_and_never_schedules(monkeypatch, sent):
    _configure(monkeypatch, schedule_enabled=False, dry_run=True)
    monkeypatch.setattr(tg, "_build_parser", lambda: FakeParser(_intent()))

    async def _boom(**k):
        raise AssertionError("schedule flow must not run when the flag is off")

    monkeypatch.setattr(sched, "handle_scheduled_whatsapp", _boom)
    _post(_client(), RAW_OK)
    assert sent[0]["text"].startswith("🧪")           # unchanged dry-run preview


def test_route_schedule_enabled_future_calls_flow_even_in_dry_run(monkeypatch, sent):
    _configure(monkeypatch, schedule_enabled=True, dry_run=True)
    monkeypatch.setattr(tg, "_build_parser", lambda: FakeParser(_intent()))
    called = {}

    async def fake_flow(**kwargs):
        called.update(kwargs)
        return "✅ נקבע: הודעה לקסניה — שליחה 13.07 10:00 (טקסט חופשי)."

    monkeypatch.setattr(sched, "handle_scheduled_whatsapp", fake_flow)
    _post(_client(), RAW_OK)
    assert called.get("owner_id") == OWNER
    assert called.get("raw_command") == RAW_OK
    assert called.get("intent") is not None
    assert "נקבע" in sent[0]["text"] and "🧪" not in sent[0]["text"]


def test_route_immediate_command_bypasses_schedule_flow(monkeypatch, sent):
    # "עכשיו" stays on the PR6.5 immediate path; never persisted as scheduled.
    _configure(monkeypatch, schedule_enabled=True, wa_send=False)
    monkeypatch.setattr(tg, "_build_parser", lambda: FakeParser(_intent(scheduled_at=None)))

    async def _boom(**k):
        raise AssertionError("an immediate command must not hit the schedule flow")

    monkeypatch.setattr(sched, "handle_scheduled_whatsapp", _boom)
    _post(_client(), "שלח לקסניה עכשיו הודעה: היי")
    assert "כבויה" in sent[0]["text"]                 # immediate pilot disabled reply


def test_route_schedule_flag_takes_precedence_over_command_core(monkeypatch, sent):
    # With the schedule flag ON, a future command persists via the schedule flow
    # even when DRY_RUN=false — command_core's general persist path is bypassed.
    _configure(monkeypatch, schedule_enabled=True, dry_run=False)
    monkeypatch.setattr(tg, "_build_parser", lambda: FakeParser(_intent()))
    import app.assistant.core.command_core as cc

    async def _boom(*a, **k):
        raise AssertionError("command_core must not run when the schedule flag is on")

    monkeypatch.setattr(cc, "process_command", _boom)
    called = {}

    async def fake_flow(**kwargs):
        called.update(kwargs)
        return "✅ נקבע"

    monkeypatch.setattr(sched, "handle_scheduled_whatsapp", fake_flow)
    _post(_client(), RAW_OK)
    assert called.get("owner_id") == OWNER

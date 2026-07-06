"""Immediate Telegram->WhatsApp flow tests. TEST-ONLY.

Fully mocked: contact resolution, the leads lookup, and the Twilio send are all
monkeypatched — no Supabase, no Twilio, no network, no real sends. The route
tests use TestClient with the parser + telegram send mocked (as elsewhere).
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.assistant.telegram.whatsapp_flow as flow
import app.routes.assistant_telegram_api as tg
from app.assistant.nlp.contract import MessageType, ParsedIntent, ParseStatus, RecipientType
from app.config.settings import settings

OWNER = "642d2881-9e7d-47cb-8cae-2d6b58a062de"
AGENT = "2145e5c9-52b2-451a-9aa9-6329a8293dc5"
SECRET = "topsecret"
FRESH = "2026-07-06T08:00:00+00:00"   # recent inbound (test clocks are near now)


# ── flow-level gate tests (handle_immediate_whatsapp) ─────────────────────────

class _Stub:
    """Monkeypatches the data adapter + whatsapp_sender seams used by the flow."""
    def __init__(self, mp, *, candidates=None, leads=None, sender="+972535666375",
                 send_result=None, window_open=True):
        self.calls = {"send": []}
        self._candidates = candidates if candidates is not None else []
        self._leads = leads if leads is not None else []
        self._sender = sender
        self._send_result = send_result or {"status": "sent", "sid": "SMxxx", "error": ""}
        self._window_open = window_open

        import app.assistant.data.supabase_adapter as data
        import app.integrations.whatsapp_sender as wa

        async def resolve_contact_candidates(owner_id, recipient_raw, hint=None):
            return list(self._candidates)

        async def get_leads_by_phone(phone, client_id):
            return list(self._leads)

        async def get_agent_whatsapp_number(agent_id):
            return self._sender

        def is_window_open(last_inbound):
            return self._window_open

        async def twilio_send_whatsapp(*, sender_number, to_phone, body):
            self.calls["send"].append({"from": sender_number, "to": to_phone, "body": body})
            return dict(self._send_result)

        mp.setattr(data, "resolve_contact_candidates", resolve_contact_candidates)
        mp.setattr(wa, "get_leads_by_phone", get_leads_by_phone)
        mp.setattr(wa, "get_agent_whatsapp_number", get_agent_whatsapp_number)
        mp.setattr(wa, "is_window_open", is_window_open)
        mp.setattr(wa, "twilio_send_whatsapp", twilio_send_whatsapp)


def _contact(name="אני", phone="+972509620964", recipient_type="client"):
    return {"id": "c-1", "name": name, "recipient_type": recipient_type, "phone": phone}


def _lead(last_inbound=FRESH):
    return {"id": "l-1", "phone": "+972509620964", "last_whatsapp_inbound_at": last_inbound}


def _run(stub, *, name="אני", body="היי בדיקה"):
    return asyncio.run(flow.handle_immediate_whatsapp(
        owner_id=OWNER, recipient_name=name, recipient_type=RecipientType.CLIENT,
        body=body, agent_map={OWNER: AGENT}))


def test_happy_path_sends_and_confirms(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact()], leads=[_lead()])
    reply = _run(stub)
    assert len(stub.calls["send"]) == 1
    assert stub.calls["send"][0] == {"from": "+972535666375", "to": "+972509620964", "body": "היי בדיקה"}
    assert "נשלח WhatsApp" in reply and "אני" in reply


def test_no_body_no_send(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact()], leads=[_lead()])
    reply = asyncio.run(flow.handle_immediate_whatsapp(
        owner_id=OWNER, recipient_name="אני", recipient_type=RecipientType.CLIENT,
        body=None, agent_map={OWNER: AGENT}))
    assert not stub.calls["send"] and "תוכן ההודעה" in reply


def test_zero_contacts_not_found(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[], leads=[_lead()])
    reply = _run(stub)
    assert not stub.calls["send"] and "לא מצאתי" in reply


def test_two_contacts_ambiguous(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact(), _contact()], leads=[_lead()])
    reply = _run(stub)
    assert not stub.calls["send"] and "יותר מאיש קשר" in reply


def test_contact_without_phone_missing_phone(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact(phone=None)], leads=[_lead()])
    reply = _run(stub, name="דנה")
    assert not stub.calls["send"] and "אין לו מספר" in reply


def test_zero_leads_no_lead(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact()], leads=[])
    reply = _run(stub)
    assert not stub.calls["send"] and "אין ליד" in reply


def test_two_leads_ambiguous_lead(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact()], leads=[_lead(), _lead()])
    reply = _run(stub)
    assert not stub.calls["send"] and "יותר מליד" in reply


def test_window_closed_no_send(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact()], leads=[_lead(last_inbound=None)],
                 window_open=False)
    reply = _run(stub)
    assert not stub.calls["send"] and "חלון WhatsApp" in reply


def test_no_agent_mapped_not_configured(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact()], leads=[_lead()])
    reply = asyncio.run(flow.handle_immediate_whatsapp(
        owner_id=OWNER, recipient_name="אני", recipient_type=RecipientType.CLIENT,
        body="היי", agent_map={}))   # owner not mapped
    assert not stub.calls["send"] and "לא מוגדרת" in reply


def test_send_failure_reply(monkeypatch):
    stub = _Stub(monkeypatch, candidates=[_contact()], leads=[_lead()],
                 send_result={"status": "failed", "sid": "", "error": "TwilioRestException"})
    reply = _run(stub)
    assert len(stub.calls["send"]) == 1 and "נכשלה" in reply


# ── route-level: flag gating + future vs immediate ────────────────────────────

class FakeParser:
    def __init__(self, intent):
        self.intent = intent

    def parse(self, raw_command, *, now=None):
        return self.intent


def _intent(recipient_name="אני", status=ParseStatus.PARSED, scheduled_at="2026-07-07T10:00:00"):
    return ParsedIntent(status=status, recipient_name=recipient_name,
                        recipient_type=RecipientType.CLIENT, message_type=MessageType.CUSTOM,
                        scheduled_at_local=scheduled_at, is_explicit_time=True)


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


def _configure(monkeypatch, *, wa_enabled, dry_run=True):
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_INTAKE_ENABLED", True)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_DRY_RUN", dry_run)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_ALLOWED_USER_IDS", "111")
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_OWNER_MAP", f"111:{OWNER}")
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_WHATSAPP_SEND_ENABLED", wa_enabled)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_WHATSAPP_AGENT_MAP", f"{OWNER}:{AGENT}")


def _post(client, text, *, update_id=10):
    body = {"update_id": update_id,
            "message": {"text": text, "from": {"id": 111}, "chat": {"id": 555}}}
    return client.post(tg.WEBHOOK_PATH, json=body, headers={tg.SECRET_HEADER: SECRET})


def test_route_immediate_disabled_replies_disabled_no_flow(monkeypatch, sent):
    _configure(monkeypatch, wa_enabled=False)
    monkeypatch.setattr(tg, "_build_parser", lambda: FakeParser(_intent()))

    async def _boom(**k):
        raise AssertionError("handle_immediate_whatsapp must not run when disabled")

    monkeypatch.setattr(flow, "handle_immediate_whatsapp", _boom)
    _post(_client(), "שלח לאני עכשיו הודעה: היי בדיקה")
    assert "כבויה" in sent[0]["text"]


def test_route_immediate_enabled_calls_flow(monkeypatch, sent):
    _configure(monkeypatch, wa_enabled=True)
    monkeypatch.setattr(tg, "_build_parser", lambda: FakeParser(_intent()))
    called = {}

    async def fake_flow(**kwargs):
        called.update(kwargs)
        return "✅ נשלח WhatsApp לאני"

    monkeypatch.setattr(flow, "handle_immediate_whatsapp", fake_flow)
    _post(_client(), "שלח לאני עכשיו הודעה: היי בדיקה")
    assert called.get("owner_id") == OWNER
    assert called.get("body") == "היי בדיקה"
    assert called.get("agent_map") == {OWNER: AGENT}
    assert "נשלח WhatsApp" in sent[0]["text"]


def test_route_future_command_never_calls_flow(monkeypatch, sent):
    # A future/scheduled command must keep dry-run preview, even with WA enabled.
    _configure(monkeypatch, wa_enabled=True, dry_run=True)
    monkeypatch.setattr(tg, "_build_parser", lambda: FakeParser(_intent()))

    async def _boom(**k):
        raise AssertionError("future command must not trigger immediate WhatsApp")

    monkeypatch.setattr(flow, "handle_immediate_whatsapp", _boom)
    _post(_client(), "שלח לאני מחר ב-10:00 הודעה: היי")
    assert sent[0]["text"].startswith("🧪")  # dry-run preview

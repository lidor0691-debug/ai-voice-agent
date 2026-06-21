"""Tests for the dormant Assistant Command Core. TEST-ONLY.

A FakeParser supplies canned ParsedIntents (no LLM). The data adapter's
network functions are monkeypatched to record calls and return seeded data
(no Supabase). The pure helpers (within_24h_window, resolve_send_plan) run for
real. Async flow driven via asyncio.run (no pytest-asyncio).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.assistant.core import command_core
from app.assistant.core.command_core import process_command
from app.assistant.data import supabase_adapter as data
from app.assistant.nlp.contract import MessageType, ParseStatus, ParsedIntent, RecipientType, SendPlan

OWNER = "11111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeParser:
    def __init__(self, intent: ParsedIntent):
        self._intent = intent
        self.calls = []

    def parse(self, raw_command, *, now=None):
        self.calls.append((raw_command, now))
        return self._intent


def _intent(status=ParseStatus.PARSED, recipient_name="דנה",
            recipient_type=RecipientType.CLIENT, message_type=MessageType.CUSTOM,
            scheduled_at="2026-06-16T10:00:00"):
    return ParsedIntent(
        status=status, recipient_name=recipient_name, recipient_type=recipient_type,
        message_type=message_type, scheduled_at_local=scheduled_at, is_explicit_time=True,
    )


def _cand(id="c-1", name="דנה", recipient_type="client", phone="+972500000001", last_inbound_at=None):
    return {"id": id, "name": name, "recipient_type": recipient_type,
            "phone": phone, "last_inbound_at": last_inbound_at}


class Recorder:
    """Monkeypatches the adapter's network seam, recording calls."""
    def __init__(self, mp, *, candidates=None, templates=None):
        self.calls = {"candidates": [], "templates": [], "scheduled": [],
                      "clarification": [], "activity": []}
        self._candidates = candidates if candidates is not None else []
        self._templates = templates if templates is not None else set()

        async def resolve_contact_candidates(owner_id, recipient_raw, recipient_type_hint=None):
            self.calls["candidates"].append(
                {"owner_id": owner_id, "recipient_raw": recipient_raw, "hint": recipient_type_hint})
            return list(self._candidates)

        async def list_active_templates(owner_id):
            self.calls["templates"].append(owner_id)
            return set(self._templates)

        async def insert_scheduled_message(owner_id, intent, *, raw_command=None,
                                           contact_id=None, send_plan=None,
                                           status="needs_clarification", body=None):
            self.calls["scheduled"].append(
                {"owner_id": owner_id, "raw_command": raw_command, "contact_id": contact_id,
                 "send_plan": send_plan, "status": status})
            return "sm-1"

        async def insert_pending_clarification(owner_id, raw_command, prompt, ctype, *,
                                               scheduled_message_id=None, detail=None):
            self.calls["clarification"].append(
                {"owner_id": owner_id, "raw_command": raw_command, "type": ctype, "detail": detail})
            return "cl-1"

        async def log_activity(owner_id, event_type, *, scheduled_message_id=None,
                               contact_id=None, detail=None):
            self.calls["activity"].append({"event": event_type, "detail": detail})
            return True

        mp.setattr(data, "resolve_contact_candidates", resolve_contact_candidates)
        mp.setattr(data, "list_active_templates", list_active_templates)
        mp.setattr(data, "insert_scheduled_message", insert_scheduled_message)
        mp.setattr(data, "insert_pending_clarification", insert_pending_clarification)
        mp.setattr(data, "log_activity", log_activity)
        # guard: the core must never touch the real HTTP seam
        async def _boom(*a, **k):
            raise AssertionError("real _rest_request must not be called in tests")
        mp.setattr(data, "_rest_request", _boom)


def _run(parser, rec, **kw):
    return asyncio.run(process_command(OWNER, kw.pop("raw", "cmd"), parser=parser, now=NOW, **kw))


# ── parser-driven clarifications ──────────────────────────────────────────────

def test_missing_send_time_from_parser(monkeypatch):
    rec = Recorder(monkeypatch)
    parser = FakeParser(_intent(status=ParseStatus.NEEDS_CLARIFICATION, scheduled_at=None))
    res = _run(parser, rec)
    assert res.kind == "clarification" and res.clarification_type == "missing_send_time"
    assert len(rec.calls["clarification"]) == 1
    assert not rec.calls["scheduled"]
    assert rec.calls["activity"][-1]["event"] == "clarification_opened"


def test_missing_recipient_from_parser(monkeypatch):
    rec = Recorder(monkeypatch)
    parser = FakeParser(_intent(status=ParseStatus.NEEDS_CLARIFICATION, recipient_name=None,
                                recipient_type=None, scheduled_at=None))
    res = _run(parser, rec)
    assert res.clarification_type == "missing_recipient"
    assert not rec.calls["scheduled"]


def test_parsed_but_missing_scheduled_at_becomes_clarification(monkeypatch):
    rec = Recorder(monkeypatch, candidates=[_cand()])
    parser = FakeParser(_intent(status=ParseStatus.PARSED, scheduled_at=None))
    res = _run(parser, rec)
    assert res.kind == "clarification" and res.clarification_type == "missing_send_time"
    assert not rec.calls["scheduled"]            # no invalid insert
    assert not rec.calls["candidates"]           # short-circuits before DB lookup


# ── DB-driven recipient resolution ───────────────────────────────────────────

def test_unknown_recipient_zero_candidates(monkeypatch):
    rec = Recorder(monkeypatch, candidates=[])
    res = _run(FakeParser(_intent()), rec)
    assert res.kind == "clarification" and res.clarification_type == "unknown_recipient"
    assert not rec.calls["scheduled"]


def test_ambiguous_recipient_multiple_candidates(monkeypatch):
    rec = Recorder(monkeypatch, candidates=[_cand(id="c-1"), _cand(id="c-2", name="דנה")])
    res = _run(FakeParser(_intent()), rec)
    assert res.kind == "clarification" and res.clarification_type == "ambiguous"
    detail = rec.calls["clarification"][-1]["detail"]
    assert [d["id"] for d in detail["candidates"]] == ["c-1", "c-2"]
    assert not rec.calls["scheduled"]


def test_recipient_type_hint_is_passed(monkeypatch):
    rec = Recorder(monkeypatch, candidates=[_cand(recipient_type="teacher")])
    _run(FakeParser(_intent(recipient_type=RecipientType.TEACHER, message_type=MessageType.LESSON_COORDINATION)), rec)
    assert rec.calls["candidates"][0]["hint"] == RecipientType.TEACHER


# ── resolved plans: all persist status='scheduled' ───────────────────────────

def test_api_template_status_scheduled(monkeypatch):
    rec = Recorder(monkeypatch, candidates=[_cand(last_inbound_at=None)],
                   templates={MessageType.AGREEMENT})
    res = _run(FakeParser(_intent(message_type=MessageType.AGREEMENT)), rec)
    assert res.send_plan == SendPlan.API_TEMPLATE
    sm = rec.calls["scheduled"][-1]
    assert sm["status"] == "scheduled" and sm["send_plan"] == "api_template"


def test_api_freeform_status_scheduled(monkeypatch):
    recent = (NOW - timedelta(hours=2)).isoformat()
    rec = Recorder(monkeypatch, candidates=[_cand(last_inbound_at=recent)],
                   templates={MessageType.AGREEMENT})
    res = _run(FakeParser(_intent(message_type=MessageType.AGREEMENT)), rec)
    assert res.send_plan == SendPlan.API_FREEFORM
    assert rec.calls["scheduled"][-1]["status"] == "scheduled"


def test_group_manual_status_scheduled(monkeypatch):
    rec = Recorder(monkeypatch, candidates=[_cand(recipient_type="group", phone=None, name="קבוצת בוקר")])
    res = _run(FakeParser(_intent(recipient_type=RecipientType.GROUP, recipient_name="קבוצת בוקר")), rec)
    assert res.send_plan == SendPlan.GROUP_MANUAL
    assert rec.calls["scheduled"][-1]["status"] == "scheduled"


def test_manual_fallback_status_scheduled(monkeypatch):
    rec = Recorder(monkeypatch, candidates=[_cand(phone=None, last_inbound_at=None)], templates=set())
    res = _run(FakeParser(_intent()), rec)
    assert res.send_plan == SendPlan.MANUAL_FALLBACK
    assert rec.calls["scheduled"][-1]["status"] == "scheduled"


# ── guard: never reminded_manual at intake ───────────────────────────────────

@pytest.mark.parametrize("setup", [
    ("template", {MessageType.AGREEMENT}, None, "client", "+972500000001"),
    ("freeform", {MessageType.AGREEMENT}, (NOW - timedelta(hours=1)).isoformat(), "client", "+972500000001"),
    ("group", set(), None, "group", None),
    ("manual", set(), None, "client", None),
])
def test_never_writes_reminded_manual(monkeypatch, setup):
    _label, templates, last_in, rtype, phone = setup
    rec = Recorder(monkeypatch,
                   candidates=[_cand(recipient_type=rtype, phone=phone, last_inbound_at=last_in)],
                   templates=templates)
    rt = RecipientType.GROUP if rtype == "group" else RecipientType.CLIENT
    _run(FakeParser(_intent(recipient_type=rt, message_type=MessageType.AGREEMENT)), rec)
    statuses = [s["status"] for s in rec.calls["scheduled"]]
    assert statuses == ["scheduled"]
    assert "reminded_manual" not in statuses
    # activity events are resolved + scheduled, never reminded_manual
    events = [a["event"] for a in rec.calls["activity"]]
    assert "reminded_manual" not in events
    assert events == ["resolved", "scheduled"]


def test_scheduled_insert_carries_raw_command_and_contact(monkeypatch):
    rec = Recorder(monkeypatch, candidates=[_cand(id="c-9")], templates={MessageType.AGREEMENT})
    asyncio.run(process_command(OWNER, "שלח לדנה הסכם מחר ב-10:00",
                                parser=FakeParser(_intent(message_type=MessageType.AGREEMENT)), now=NOW))
    sm = rec.calls["scheduled"][-1]
    assert sm["raw_command"] == "שלח לדנה הסכם מחר ב-10:00"
    assert sm["contact_id"] == "c-9"

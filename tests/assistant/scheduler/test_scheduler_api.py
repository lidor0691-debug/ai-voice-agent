"""Scheduled-WhatsApp dispatcher tests (PR-B). TEST-ONLY.

Fully mocked: the Supabase adapter reads/claim/writes and the whatsapp_sender
gates/Twilio send are all monkeypatched — no Supabase, no Twilio, no network,
no real sends. Async dispatch functions run via asyncio.run; route tests use
TestClient with the router mounted on a fresh app.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.assistant.data.supabase_adapter as data
import app.assistant.scheduler.whatsapp_dispatch as dispatch
import app.integrations.whatsapp_sender as wa
import app.routes.assistant_scheduler_api as api
from app.config.settings import settings

OWNER = "642d2881-9e7d-47cb-8cae-2d6b58a062de"
AGENT = "2145e5c9-52b2-451a-9aa9-6329a8293dc5"
SECRET = "sched-secret"
NOW = datetime(2026, 7, 13, 7, 0, 0, tzinfo=timezone.utc)


def _row(mid="sm-1", body="היי", scheduled_at="2026-07-13T06:00:00+00:00"):
    return {"id": mid, "owner_id": OWNER, "contact_id": "c-1",
            "recipient_type": "client", "body": body, "scheduled_at": scheduled_at}


def _contact(phone="+972538208363", name="קסניה"):
    return {"id": "c-1", "name": name, "recipient_type": "client",
            "phone": phone, "last_inbound_at": None}


def _lead():
    return {"id": "l-1", "phone": "+972538208363",
            "last_whatsapp_inbound_at": "2026-07-13T05:00:00+00:00"}


class _Rec:
    def __init__(self):
        self.status_updates = []
        self.activity = []
        self.sends = []
        self.claims = []


def install(monkeypatch, *, due=None, contact="__default__", leads=None,
            window_open=True, sender="+972535666375", claim=True, send_result=None):
    """Install all adapter + whatsapp_sender seams the dispatcher uses."""
    rec = _Rec()
    due_rows = [_row()] if due is None else (list(due) if isinstance(due, list) else [due])
    contact = _contact() if contact == "__default__" else contact
    leads = [_lead()] if leads is None else leads
    send_result = send_result or {"status": "sent", "sid": "SMxyz", "error": ""}

    async def list_due(now_iso, *, limit=200):
        return list(due_rows)

    async def get_contact_by_id(cid):
        return contact

    async def claim_scheduled_message(mid, *, now=None):
        rec.claims.append(mid)
        return claim

    async def update_scheduled_status(mid, status, *, sent_at=None, **kw):
        rec.status_updates.append({"id": mid, "status": status, "sent_at": sent_at})
        return True

    async def log_activity(owner_id, event_type, *, scheduled_message_id=None,
                           contact_id=None, detail=None):
        rec.activity.append({"event": event_type, "detail": detail or {}})
        return True

    async def get_leads_by_phone(phone, client_id):
        return list(leads)

    def is_window_open(last_inbound):
        return window_open

    async def get_agent_whatsapp_number(agent_id):
        return sender

    async def twilio_send_whatsapp(*, sender_number, to_phone, body):
        rec.sends.append({"from": sender_number, "to": to_phone, "body": body})
        return dict(send_result)

    monkeypatch.setattr(data, "list_due_scheduled_messages", list_due)
    monkeypatch.setattr(data, "get_contact_by_id", get_contact_by_id)
    monkeypatch.setattr(data, "claim_scheduled_message", claim_scheduled_message)
    monkeypatch.setattr(data, "update_scheduled_status", update_scheduled_status)
    monkeypatch.setattr(data, "log_activity", log_activity)
    monkeypatch.setattr(wa, "get_leads_by_phone", get_leads_by_phone)
    monkeypatch.setattr(wa, "is_window_open", is_window_open)
    monkeypatch.setattr(wa, "get_agent_whatsapp_number", get_agent_whatsapp_number)
    monkeypatch.setattr(wa, "twilio_send_whatsapp", twilio_send_whatsapp)
    return rec


def _run(agent_map=None):
    return asyncio.run(dispatch.run_due(
        now=NOW, agent_map={OWNER: AGENT} if agent_map is None else agent_map))


def _fail_reason(rec):
    ev = [a for a in rec.activity if a["event"] == "send_failed"]
    return ev[-1]["detail"].get("reason") if ev else None


# ── run_due: happy path + every gate ──────────────────────────────────────────

def test_run_happy_path_sends_marks_sent_logs_sid(monkeypatch):
    rec = install(monkeypatch)
    summary = _run()
    assert summary == {"sent": 1, "failed": 0, "skipped": 0, "details": summary["details"]}
    assert rec.claims == ["sm-1"]
    assert rec.sends == [{"from": "+972535666375", "to": "+972538208363", "body": "היי"}]
    assert rec.status_updates[-1] == {"id": "sm-1", "status": "sent", "sent_at": NOW}
    sent_ev = [a for a in rec.activity if a["event"] == "sent"][0]
    assert sent_ev["detail"]["sid"] == "SMxyz"


def test_run_lost_claim_skips_and_never_sends(monkeypatch):
    rec = install(monkeypatch, claim=False)
    summary = _run()
    assert summary["skipped"] == 1 and summary["sent"] == 0 and summary["failed"] == 0
    assert rec.sends == []
    assert rec.status_updates == []   # no terminal transition on a lost claim


def test_run_window_closed_marks_failed_no_send(monkeypatch):
    rec = install(monkeypatch, window_open=False)
    summary = _run()
    assert summary["failed"] == 1 and rec.sends == []
    assert rec.status_updates[-1]["status"] == "failed"
    assert _fail_reason(rec) == "window_closed_needs_template"


def test_run_missing_phone_marks_failed_no_send(monkeypatch):
    rec = install(monkeypatch, contact=_contact(phone=None))
    summary = _run()
    assert summary["failed"] == 1 and rec.sends == []
    assert _fail_reason(rec) == "missing_phone"


def test_run_no_lead_marks_failed_no_send(monkeypatch):
    rec = install(monkeypatch, leads=[])
    summary = _run()
    assert summary["failed"] == 1 and rec.sends == []
    assert _fail_reason(rec) == "no_lead"


def test_run_ambiguous_lead_marks_failed_no_send(monkeypatch):
    rec = install(monkeypatch, leads=[_lead(), _lead()])
    summary = _run()
    assert summary["failed"] == 1 and rec.sends == []
    assert _fail_reason(rec) == "ambiguous_lead"


def test_run_contact_not_found_marks_failed_no_send(monkeypatch):
    rec = install(monkeypatch, contact=None)
    summary = _run()
    assert summary["failed"] == 1 and rec.sends == []
    assert _fail_reason(rec) == "contact_not_found"


def test_run_unmapped_agent_marks_failed_no_send(monkeypatch):
    rec = install(monkeypatch)
    summary = _run(agent_map={})   # owner not mapped -> no agent
    assert summary["failed"] == 1 and rec.sends == []
    assert _fail_reason(rec) == "agent_not_configured"


def test_run_twilio_failure_marks_failed_logs_error(monkeypatch):
    rec = install(monkeypatch,
                  send_result={"status": "failed", "sid": "", "error": "TwilioRestException"})
    summary = _run()
    assert summary["failed"] == 1 and len(rec.sends) == 1   # attempted once
    assert rec.status_updates[-1]["status"] == "failed"
    fev = [a for a in rec.activity if a["event"] == "send_failed"][0]
    assert fev["detail"]["reason"] == "twilio_error"
    assert fev["detail"]["error"] == "TwilioRestException"


# ── evaluate_due (GET): read-only, sends nothing ──────────────────────────────

def test_evaluate_due_is_read_only(monkeypatch):
    rec = install(monkeypatch)
    result = asyncio.run(dispatch.evaluate_due(now=NOW, agent_map={OWNER: AGENT}))
    assert result["count"] == 1 and result["eligible"] == 1
    assert result["due"][0]["message_id"] == "sm-1" and result["due"][0]["eligible"] is True
    assert rec.sends == [] and rec.status_updates == [] and rec.claims == []


def test_evaluate_due_reports_gate_reason(monkeypatch):
    install(monkeypatch, window_open=False)
    result = asyncio.run(dispatch.evaluate_due(now=NOW, agent_map={OWNER: AGENT}))
    assert result["eligible"] == 0
    assert result["due"][0]["reason"] == "window_closed_needs_template"


# ── adapter: due-query filters (#11 future / #12 plan / #13 status) + claim ────

def test_list_due_builds_correct_filters(monkeypatch):
    cap = []

    async def fake_rest(method, table, *, params=None, json=None, prefer="return=representation"):
        cap.append({"method": method, "table": table, "params": params})
        return []

    monkeypatch.setattr(data, "_rest_request", fake_rest)
    asyncio.run(data.list_due_scheduled_messages("2026-07-13T07:00:00+00:00", limit=50))
    p = cap[0]["params"]
    assert p["status"] == "eq.scheduled"                       # non-scheduled excluded (#13)
    assert p["send_plan"] == "eq.api_freeform"                 # other plans excluded (#12)
    assert p["scheduled_at"] == "lte.2026-07-13T07:00:00+00:00"  # future excluded (#11)
    assert p["approved_at"] == "is.null"                       # already-claimed excluded
    assert p["contact_id"] == "not.is.null" and p["body"] == "not.is.null"
    assert p["limit"] == "50"


def test_claim_builds_conditional_patch_and_reports_winner(monkeypatch):
    cap = []

    async def won(method, table, *, params=None, json=None, prefer="return=representation"):
        cap.append({"method": method, "params": params, "json": json, "prefer": prefer})
        return [{"id": "sm-1"}]      # matched -> winner

    monkeypatch.setattr(data, "_rest_request", won)
    ok = asyncio.run(data.claim_scheduled_message("sm-1", now=NOW))
    assert ok is True
    c = cap[0]
    assert c["method"] == "PATCH" and c["prefer"] == "return=representation"
    assert c["params"] == {"id": "eq.sm-1", "status": "eq.scheduled", "approved_at": "is.null"}
    assert "approval_requested_at" in c["json"] and "approved_at" in c["json"]


def test_claim_lost_returns_false(monkeypatch):
    async def lost(method, table, *, params=None, json=None, prefer="return=representation"):
        return []      # zero rows matched -> someone else claimed / not scheduled

    monkeypatch.setattr(data, "_rest_request", lost)
    assert asyncio.run(data.claim_scheduled_message("sm-1")) is False


# ── route: mounting / secret / behavior ───────────────────────────────────────

def _client():
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def _configure(monkeypatch, *, enabled=True, secret=SECRET):
    monkeypatch.setattr(settings, "ASSISTANT_SCHEDULER_ENABLED", enabled)
    monkeypatch.setattr(settings, "ASSISTANT_SCHEDULER_SECRET", secret)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_WHATSAPP_AGENT_MAP", f"{OWNER}:{AGENT}")


def test_route_disabled_returns_404(monkeypatch):
    _configure(monkeypatch, enabled=False)
    assert _client().get(api.DUE_PATH, headers={api.SECRET_HEADER: SECRET}).status_code == 404
    assert _client().post(api.RUN_PATH, headers={api.SECRET_HEADER: SECRET}).status_code == 404


def test_route_missing_secret_401_does_nothing(monkeypatch):
    _configure(monkeypatch)

    async def boom(*a, **k):
        raise AssertionError("no work may run without a valid secret")

    monkeypatch.setattr(data, "list_due_scheduled_messages", boom)
    assert _client().get(api.DUE_PATH).status_code == 401
    assert _client().post(api.RUN_PATH).status_code == 401


def test_route_wrong_secret_401(monkeypatch):
    _configure(monkeypatch)

    async def boom(*a, **k):
        raise AssertionError("no work may run with a wrong secret")

    monkeypatch.setattr(data, "list_due_scheduled_messages", boom)
    r = _client().get(api.DUE_PATH, headers={api.SECRET_HEADER: "WRONG"})
    assert r.status_code == 401


def test_route_due_lists_and_sends_nothing(monkeypatch):
    _configure(monkeypatch)
    rec = install(monkeypatch)
    r = _client().get(api.DUE_PATH, headers={api.SECRET_HEADER: SECRET})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True and body["count"] == 1 and body["eligible"] == 1
    assert rec.sends == [] and rec.status_updates == []


def test_route_run_sends_and_summarizes(monkeypatch):
    _configure(monkeypatch)
    rec = install(monkeypatch)
    r = _client().post(api.RUN_PATH, headers={api.SECRET_HEADER: SECRET})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["sent"] == 1 and body["failed"] == 0
    assert len(rec.sends) == 1 and rec.status_updates[-1]["status"] == "sent"


# ── isolation: router not mounted by default; no heavy top-level imports ───────

def test_scheduler_not_mounted_in_main_by_default():
    import subprocess
    import sys

    code = (
        "import main, sys;"
        "paths=[getattr(r,'path',None) for r in main.app.routes];"
        "assert '/assistant/scheduler/due' not in paths, paths;"
        "assert '/assistant/scheduler/run' not in paths, paths;"
        "assert not any('assistant_scheduler_api' in m for m in sys.modules), 'router imported';"
        "assert not any('whatsapp_dispatch' in m for m in sys.modules), 'dispatch imported';"
        "print('SCHED_DISABLED_OK')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "SCHED_DISABLED_OK" in r.stdout


def test_router_module_imports_no_twilio_or_heavy_deps_at_top_level():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(api))
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module)
    joined = " ".join(top).lower()
    assert "twilio" not in joined, top
    assert not any("whatsapp_sender" in m for m in top), top
    assert not any("whatsapp_dispatch" in m for m in top), top   # dispatcher stays lazy
    assert not any("supabase_adapter" in m for m in top), top

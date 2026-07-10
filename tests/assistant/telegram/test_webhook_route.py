"""Telegram webhook route tests. TEST-ONLY.

Fully mocked: a FakeParser (no Claude/key), a recording send_message (no httpx),
and a monkeypatched Command Core (no Supabase). The route is mounted on a local
FastAPI app via TestClient. No network anywhere.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes.assistant_telegram_api as tg
from app.assistant.core.parser_port import CommandResult
from app.assistant.nlp.contract import (
    MessageType,
    ParsedIntent,
    ParseStatus,
    RecipientType,
    SendPlan,
)
from app.config.settings import settings

UUID1 = "11111111-1111-1111-1111-111111111111"
SECRET = "topsecret"


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeParser:
    def __init__(self, intent):
        self.intent = intent
        self.calls = []

    def parse(self, raw_command, *, now=None):
        self.calls.append((raw_command, now))
        return self.intent


def _intent(status=ParseStatus.PARSED, recipient_name="דנה",
            recipient_type=RecipientType.CLIENT, message_type=MessageType.CUSTOM,
            scheduled_at="2026-06-16T10:00:00", related_event_date=None):
    return ParsedIntent(
        status=status, recipient_name=recipient_name, recipient_type=recipient_type,
        message_type=message_type, scheduled_at_local=scheduled_at,
        is_explicit_time=True, related_event_date=related_event_date,
    )


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
    """Record telegram sendMessage calls instead of hitting the network."""
    calls = []

    async def fake_send(chat_id, text):
        calls.append({"chat_id": chat_id, "text": text})
        return True

    monkeypatch.setattr(tg.telegram_client, "send_message", fake_send)
    return calls


def _configure(monkeypatch, *, enabled=True, dry_run=True,
               allowed="111", owner_map=f"111:{UUID1}", secret=SECRET):
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_INTAKE_ENABLED", enabled)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_DRY_RUN", dry_run)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_ALLOWED_USER_IDS", allowed)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_OWNER_MAP", owner_map)
    monkeypatch.setattr(settings, "ASSISTANT_TELEGRAM_WEBHOOK_SECRET", secret)


def _client():
    app = FastAPI()
    app.include_router(tg.router)
    return TestClient(app)


def _use_parser(monkeypatch, intent):
    fake = FakeParser(intent)
    monkeypatch.setattr(tg, "_build_parser", lambda: fake)
    return fake


def _post(client, body, *, secret=SECRET, uid=111, cid=555, update_id=10, text="שלח לדנה הודעה מחר"):
    payload = body if body is not None else {
        "update_id": update_id,
        "message": {"text": text, "from": {"id": uid}, "chat": {"id": cid}},
    }
    headers = {tg.SECRET_HEADER: secret} if secret is not None else {}
    return client.post(tg.WEBHOOK_PATH, json=payload, headers=headers)


# ── disabled by default ───────────────────────────────────────────────────────

def test_route_not_mounted_in_main_by_default():
    # Run in a subprocess: importing `main` rewraps sys.stdout/stderr (UTF-8),
    # which would corrupt pytest's capture teardown if done in-process.
    import subprocess
    import sys

    code = (
        "import main, sys;"
        "paths=[getattr(r,'path',None) for r in main.app.routes];"
        "assert '/assistant/telegram/webhook' not in paths, paths;"
        "assert not any('assistant_telegram_api' in m for m in sys.modules), 'route imported';"
        "assert not any(m.endswith('command_core') for m in sys.modules), 'command_core imported';"
        "assert not any('llm_parser' in m for m in sys.modules), 'llm_parser imported';"
        "assert not any('telegram_client' in m for m in sys.modules), 'tg client imported';"
        "print('DISABLED_OK')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "DISABLED_OK" in r.stdout


def test_defensive_disabled_flag_makes_handler_inert(monkeypatch, sent):
    _configure(monkeypatch, enabled=False)
    fake = _use_parser(monkeypatch, _intent())
    r = _post(_client(), None)
    assert r.status_code == 200
    assert fake.calls == []      # parser never called
    assert sent == []            # no reply


# ── secret gate ───────────────────────────────────────────────────────────────

def test_missing_secret_rejected_before_parser(monkeypatch, sent):
    _configure(monkeypatch)
    fake = _use_parser(monkeypatch, _intent())
    r = _post(_client(), None, secret=None)
    assert r.status_code == 200
    assert fake.calls == [] and sent == []


def test_wrong_secret_rejected(monkeypatch, sent):
    _configure(monkeypatch)
    fake = _use_parser(monkeypatch, _intent())
    r = _post(_client(), None, secret="WRONG")
    assert r.status_code == 200
    assert fake.calls == [] and sent == []


# ── auth gate ─────────────────────────────────────────────────────────────────

def test_non_allowlisted_user_rejected(monkeypatch, sent):
    _configure(monkeypatch, allowed="999")  # 111 not allowed
    fake = _use_parser(monkeypatch, _intent())
    r = _post(_client(), None)
    assert r.status_code == 200
    assert fake.calls == [] and sent == []


def test_unmapped_user_rejected(monkeypatch, sent):
    _configure(monkeypatch, allowed="111", owner_map="222:" + UUID1)  # 111 allowed but unmapped
    fake = _use_parser(monkeypatch, _intent())
    r = _post(_client(), None)
    assert r.status_code == 200
    assert fake.calls == [] and sent == []


# ── non-text update ───────────────────────────────────────────────────────────

def test_non_text_update_is_neutral_noop(monkeypatch, sent):
    _configure(monkeypatch)
    fake = _use_parser(monkeypatch, _intent())
    body = {"update_id": 1, "message": {"from": {"id": 111}, "chat": {"id": 555}, "photo": []}}
    r = _post(_client(), body)
    assert r.status_code == 200
    assert fake.calls == [] and sent == []


# ── dry-run (default) ─────────────────────────────────────────────────────────

def test_dry_run_parsed_command_replies_and_does_not_persist(monkeypatch, sent):
    _configure(monkeypatch, dry_run=True)
    _use_parser(monkeypatch, _intent())

    # Guard: the persist path (the only writer) must NOT be invoked in dry-run.
    import app.assistant.core.command_core as cc

    async def _boom(*a, **k):
        raise AssertionError("Command Core must not run in dry-run")

    monkeypatch.setattr(cc, "process_command", _boom)

    r = _post(_client(), None)
    assert r.status_code == 200
    assert len(sent) == 1
    assert sent[0]["chat_id"] == 555
    assert sent[0]["text"].startswith("🧪")        # dry-run prefix
    assert "דנה" in sent[0]["text"]


def test_dry_run_missing_send_time_clarifies(monkeypatch, sent):
    _configure(monkeypatch, dry_run=True)
    _use_parser(monkeypatch, _intent(status=ParseStatus.NEEDS_CLARIFICATION, scheduled_at=None))
    r = _post(_client(), None)
    assert r.status_code == 200
    assert "מתי לשלוח" in sent[0]["text"] and sent[0]["text"].startswith("🧪")


def test_dry_run_missing_recipient_clarifies(monkeypatch, sent):
    _configure(monkeypatch, dry_run=True)
    _use_parser(monkeypatch, _intent(status=ParseStatus.NEEDS_CLARIFICATION,
                                     recipient_name=None, recipient_type=None, scheduled_at=None))
    r = _post(_client(), None)
    assert "למי לשלוח" in sent[0]["text"]


# ── persist mode (mocked Command Core) ────────────────────────────────────────

def _patch_command_core(monkeypatch, result):
    import app.assistant.core.command_core as cc
    captured = {}

    async def fake_pc(owner_id, raw_command, *, parser, now=None, source=None):
        captured.update(owner_id=owner_id, raw=raw_command, source=source,
                        parser=parser)
        return result

    monkeypatch.setattr(cc, "process_command", fake_pc)
    return captured


def test_persist_scheduled_invokes_command_core(monkeypatch, sent):
    _configure(monkeypatch, dry_run=False)
    _use_parser(monkeypatch, _intent(message_type=MessageType.AGREEMENT))
    cap = _patch_command_core(monkeypatch, CommandResult(
        kind="scheduled", status="scheduled", send_plan=SendPlan.API_TEMPLATE,
        scheduled_message_id="sm-1"))
    r = _post(_client(), None)
    assert r.status_code == 200
    assert cap["owner_id"] == UUID1
    assert cap["source"] == {"channel": "telegram", "tg_user_id": 111}
    # reused the already-parsed intent (no second model call)
    assert isinstance(cap["parser"], tg._PreparsedParser)
    assert "✅ נקבע" in sent[0]["text"] and "🧪" not in sent[0]["text"]


def test_persist_unknown_recipient_reply(monkeypatch, sent):
    _configure(monkeypatch, dry_run=False)
    _use_parser(monkeypatch, _intent())
    _patch_command_core(monkeypatch, CommandResult(
        kind="clarification", status="needs_clarification",
        clarification_type="unknown_recipient"))
    _post(_client(), None)
    assert "לא מצאתי" in sent[0]["text"]


def test_persist_ambiguous_reply(monkeypatch, sent):
    _configure(monkeypatch, dry_run=False)
    _use_parser(monkeypatch, _intent())
    _patch_command_core(monkeypatch, CommandResult(
        kind="clarification", status="needs_clarification",
        clarification_type="ambiguous"))
    _post(_client(), None)
    assert "כמה אנשי קשר" in sent[0]["text"]


# ── idempotency ───────────────────────────────────────────────────────────────

def test_duplicate_update_id_deduped(monkeypatch, sent):
    _configure(monkeypatch, dry_run=True)
    fake = _use_parser(monkeypatch, _intent())
    client = _client()
    _post(client, None, update_id=77)
    _post(client, None, update_id=77)   # same update_id
    assert len(fake.calls) == 1         # parsed only once
    assert len(sent) == 1               # replied only once


# ── isolation: importing the route pulls in no heavy deps ─────────────────────

def test_route_module_imports_no_heavy_deps_at_import_time():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(tg))
    top_level = set()
    for node in tree.body:  # module-level imports only (not lazy in-function)
        if isinstance(node, ast.Import):
            top_level.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module)
    assert not any("command_core" in m for m in top_level), top_level
    assert not any("llm_parser" in m for m in top_level), top_level
    assert not any("assistant.data" in m for m in top_level), top_level
    assert not any(m == "anthropic" for m in top_level), top_level


def test_route_does_not_import_twilio_make_scheduler_or_whatsapp_sender():
    # The route may reference the WhatsApp *flow* (lazily), but must NOT import
    # Twilio, Make, a scheduler, or the Twilio-backed whatsapp_sender directly —
    # and the heavy flow must be imported LAZILY (not at module top level).
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(tg))
    all_names, top_level = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            all_names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            all_names.add(node.module)
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module)

    joined = " ".join(all_names).lower()
    assert "twilio" not in joined, all_names
    assert "make_webhook" not in joined, all_names
    assert "scheduler" not in joined and "apscheduler" not in joined, all_names
    # Twilio-backed sender reached only via whatsapp_flow, never imported directly.
    assert not any("whatsapp_sender" in m for m in all_names), all_names
    # Heavy WhatsApp flow must stay lazy (not a top-level import).
    assert not any("whatsapp_flow" in m for m in top_level), top_level

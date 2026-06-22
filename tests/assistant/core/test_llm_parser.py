"""Tests for the dormant Claude Stage-1 parser adapter. TEST-ONLY.

The Anthropic client is mocked — no real Claude/API calls, no ANTHROPIC_API_KEY.
Async parse is driven via asyncio.run (no pytest-asyncio).
"""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone

import pytest

import app.assistant.core.llm_parser as llm_parser_mod
from app.assistant.core import parser_schema
from app.assistant.core.llm_parser import DEFAULT_MODEL, ClaudeParser
from app.assistant.core.parser_schema import (
    MESSAGE_TYPE_VALUES,
    RECIPIENT_TYPE_VALUES,
    STATUS_VALUES,
    LLMParseResult,
    to_parsed_intent,
)
from app.assistant.nlp.contract import (
    MessageType,
    ParseStatus,
    RecipientType,
)

NOW = datetime(2026, 6, 16, 9, 0, 0, tzinfo=timezone.utc)  # 12:00 Asia/Jerusalem (summer)


# ── fake Anthropic client ─────────────────────────────────────────────────────

class _Resp:
    def __init__(self, parsed_output, stop_reason="end_turn"):
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, resp=None, raises=None):
        self._resp = resp
        self._raises = raises
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._resp


class _Client:
    def __init__(self, resp=None, raises=None):
        self.messages = _Messages(resp=resp, raises=raises)


@pytest.fixture(autouse=True)
def _no_real_client(monkeypatch):
    """Guarantee no real AsyncAnthropic is ever constructed in tests."""
    import anthropic

    def _boom(*a, **k):
        raise AssertionError("real AsyncAnthropic must not be constructed in tests")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _boom)


def _parser(resp=None, raises=None):
    return ClaudeParser(client=_Client(resp=resp, raises=raises))


# ── model resolution ──────────────────────────────────────────────────────────

def test_default_model_is_sonnet(monkeypatch):
    monkeypatch.delenv("ASSISTANT_PARSER_MODEL", raising=False)
    assert ClaudeParser(client=_Client()).model == "claude-sonnet-4-6"
    assert DEFAULT_MODEL == "claude-sonnet-4-6"


def test_env_override_model(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PARSER_MODEL", "claude-opus-4-8")
    assert ClaudeParser(client=_Client()).model == "claude-opus-4-8"


def test_model_is_passed_to_api(monkeypatch):
    monkeypatch.delenv("ASSISTANT_PARSER_MODEL", raising=False)
    p = _parser(resp=_Resp(LLMParseResult(status="needs_clarification", clarification="?")))
    asyncio.run(p.parse("שלח לדנה הודעה", now=NOW))
    assert p._client.messages.calls[0]["model"] == "claude-sonnet-4-6"


# ── valid structured output -> ParsedIntent ───────────────────────────────────

def test_valid_parsed_maps_through():
    out = LLMParseResult(
        status="parsed", recipient_name="דנה", recipient_type="client",
        message_type="custom", scheduled_at_local="2026-06-16T10:00:00",
        is_explicit_time=False,
    )
    intent = asyncio.run(_parser(resp=_Resp(out)).parse("שלח לדנה הודעה מחר", now=NOW))
    assert intent.status == ParseStatus.PARSED
    assert intent.recipient_name == "דנה"
    assert intent.recipient_type == RecipientType.CLIENT
    assert intent.message_type == MessageType.CUSTOM
    assert intent.scheduled_at_local == "2026-06-16T10:00:00"
    assert intent.is_explicit_time is False


def test_hebrew_date_fields_pass_through():
    out = LLMParseResult(
        status="parsed", recipient_name="יוסי", recipient_type="teacher",
        message_type="lesson_coordination", scheduled_at_local="2026-06-17T09:00:00",
        is_explicit_time=True, related_event_date="2026-06-20",
    )
    intent = asyncio.run(_parser(resp=_Resp(out)).parse("...", now=NOW))
    assert intent.scheduled_at_local == "2026-06-17T09:00:00"
    assert intent.related_event_date == "2026-06-20"
    assert intent.recipient_type == RecipientType.TEACHER
    assert intent.message_type == MessageType.LESSON_COORDINATION


def test_needs_clarification_event_date_only_preserved():
    out = LLMParseResult(
        status="needs_clarification", recipient_name="רבקה", recipient_type="client",
        message_type="agreement", related_event_date="2026-06-29",
        clarification="When should I send it?",
    )
    intent = asyncio.run(_parser(resp=_Resp(out)).parse("...", now=NOW))
    assert intent.status == ParseStatus.NEEDS_CLARIFICATION
    assert intent.related_event_date == "2026-06-29"
    assert intent.scheduled_at_local is None
    assert intent.message_type == MessageType.AGREEMENT


# ── safe-clarification fallbacks ──────────────────────────────────────────────

def test_none_parsed_output_is_safe_clarification():
    intent = asyncio.run(_parser(resp=_Resp(None)).parse("...", now=NOW))
    assert intent.status == ParseStatus.NEEDS_CLARIFICATION
    assert intent.inferred_notes == ["unclear_intent"]


def test_refusal_is_safe_clarification():
    out = LLMParseResult(status="parsed", recipient_name="x", scheduled_at_local="2026-06-16T10:00:00")
    intent = asyncio.run(_parser(resp=_Resp(out, stop_reason="refusal")).parse("...", now=NOW))
    assert intent.status == ParseStatus.NEEDS_CLARIFICATION
    assert intent.inferred_notes == ["unclear_intent"]


def test_api_exception_is_safe_clarification():
    intent = asyncio.run(_parser(raises=RuntimeError("boom")).parse("...", now=NOW))
    assert intent.status == ParseStatus.NEEDS_CLARIFICATION
    assert intent.inferred_notes == ["unclear_intent"]


def test_parsed_missing_required_fields_is_safe_clarification():
    out = LLMParseResult(status="parsed", recipient_name=None, scheduled_at_local=None)
    assert to_parsed_intent(out).status == ParseStatus.NEEDS_CLARIFICATION
    assert to_parsed_intent(out).inferred_notes == ["unclear_intent"]


def test_invalid_enum_is_safe_clarification():
    # bypass pydantic validation to inject an invalid enum value
    bad = LLMParseResult.model_construct(
        status="parsed", recipient_name="x", recipient_type="alien",
        message_type="custom", scheduled_at_local="2026-06-16T10:00:00",
    )
    assert to_parsed_intent(bad).status == ParseStatus.NEEDS_CLARIFICATION
    assert to_parsed_intent(bad).inferred_notes == ["unclear_intent"]


# ── now / timezone anchoring ──────────────────────────────────────────────────

def test_now_anchored_to_jerusalem_in_prompt():
    p = _parser(resp=_Resp(LLMParseResult(status="needs_clarification", clarification="?")))
    asyncio.run(p.parse("שלח לדנה הודעה", now=NOW))
    content = p._client.messages.calls[0]["messages"][0]["content"]
    assert "2026-06-16T12:00:00 (Asia/Jerusalem)" in content   # 09:00 UTC -> 12:00 IDT
    assert "שלח לדנה הודעה" in content


# ── recipient_type teacher inference (prompt contract + mapping) ──────────────

def test_prompt_states_lesson_coordination_implies_teacher():
    prompt = llm_parser_mod._SYSTEM_PROMPT
    assert "recipient_type inference" in prompt
    assert "lesson_coordination" in prompt and "teacher" in prompt
    assert "coordinate lessons WITH teachers" in prompt
    # the explicit student/parent/client override is documented
    assert "תלמיד" in prompt and "הורה" in prompt


def test_prompt_states_dual_date_does_not_change_recipient_type():
    prompt = llm_parser_mod._SYSTEM_PROMPT
    assert "Dual-date" in prompt
    assert "must NOT change recipient_type" in prompt


def test_prompt_has_teacher_dual_date_example_not_overfit_to_case_23():
    prompt = llm_parser_mod._SYSTEM_PROMPT
    # a structurally-equivalent lesson_coordination/teacher dual-date example
    assert "תיאום שיעור" in prompt
    assert 'recipient_type="teacher"' in prompt
    # NOT the exact case-23 command text — pattern taught, not hardcoded
    assert "שלח ליוסי תיאום שיעור ל-20.6 ב-17.6 בשעה 09:00" not in prompt


def test_dual_date_teacher_output_maps_through():
    # Mapping-only (no network): a correct teacher/lesson_coordination dual-date
    # structured output must map to recipient_type=teacher with both dates kept.
    out = LLMParseResult(
        status="parsed", recipient_name="יוסי", recipient_type="teacher",
        message_type="lesson_coordination", scheduled_at_local="2026-06-17T09:00:00",
        is_explicit_time=True, related_event_date="2026-06-20",
    )
    intent = asyncio.run(
        _parser(resp=_Resp(out)).parse(
            "שלח ליוסי תיאום שיעור ל-20.6 ב-17.6 בשעה 09:00", now=NOW
        )
    )
    assert intent.recipient_type == RecipientType.TEACHER
    assert intent.message_type == MessageType.LESSON_COORDINATION
    assert intent.scheduled_at_local == "2026-06-17T09:00:00"
    assert intent.related_event_date == "2026-06-20"


# ── isolation: no contact lookup / no data adapter ────────────────────────────

def _imported_modules(mod):
    import ast

    tree = ast.parse(inspect.getsource(mod))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_adapter_does_not_import_data_layer():
    # Functional isolation: neither module imports the Supabase data adapter,
    # so the parser cannot perform contact lookup or any DB access.
    for mod in (llm_parser_mod, parser_schema):
        imports = _imported_modules(mod)
        assert not any(name.startswith("app.assistant.data") for name in imports), imports
        assert not any("supabase" in name.lower() for name in imports), imports


def test_no_send_plan_attribute_emitted():
    out = LLMParseResult(status="parsed", recipient_name="דנה",
                         scheduled_at_local="2026-06-16T10:00:00")
    intent = asyncio.run(_parser(resp=_Resp(out)).parse("...", now=NOW))
    assert not hasattr(intent, "send_plan")


# ── schema <-> contract lockstep ──────────────────────────────────────────────

def test_recipient_type_values_match_contract():
    assert set(RECIPIENT_TYPE_VALUES) == {e.value for e in RecipientType}


def test_message_type_values_match_contract():
    assert set(MESSAGE_TYPE_VALUES) == {e.value for e in MessageType}


def test_status_values_match_contract():
    assert set(STATUS_VALUES) == {e.value for e in ParseStatus}

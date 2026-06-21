"""Tests for the dormant Hebrew parser eval harness. TEST-ONLY.

Fully mocked and no-network: a FakeParser supplies canned ParsedIntents, no
Anthropic client is ever constructed, no ANTHROPIC_API_KEY is required, and the
data adapter is never imported. Async flow via asyncio.run (no pytest-asyncio).
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import sys

import pytest

from app.assistant.nlp.contract import (
    MessageType,
    ParsedIntent,
    ParseStatus,
    RecipientType,
)
from tools.assistant_eval import compare as compare_mod
from tools.assistant_eval import dataset as dataset_mod
from tools.assistant_eval import report as report_mod
from tools.assistant_eval import run_eval as run_eval_mod
from tools.assistant_eval.compare import compare_case
from tools.assistant_eval.dataset import CASES, anchored_now, select_cases
from tools.assistant_eval.report import format_report, summarize, to_dict
from tools.assistant_eval.run_eval import (
    KEY_ENV,
    RUN_FLAG,
    _configure_utf8_output,
    evaluate_cases,
    gate_blockers,
    live_allowed,
    run,
    safe_print,
)


# ── safety: never let a real Anthropic client be constructed ──────────────────

@pytest.fixture(autouse=True)
def _no_real_client(monkeypatch):
    import anthropic

    def _boom(*a, **k):
        raise AssertionError("real AsyncAnthropic must not be constructed in tests")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _boom)


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeParser:
    """Returns a canned ParsedIntent per command (by text), recording calls."""

    def __init__(self, by_text=None, default=None):
        self._by_text = by_text or {}
        self._default = default
        self.calls = []

    def parse(self, raw_command, *, now=None):
        self.calls.append((raw_command, now))
        return self._by_text.get(raw_command, self._default)


def _intent_from_expect(case) -> ParsedIntent:
    """Build the EXACT expected intent so a perfect parser scores a pass."""
    e = case.expect
    return ParsedIntent(
        status=e["status"],
        recipient_name=e.get("recipient_name"),
        recipient_type=e.get("recipient_type"),
        message_type=e.get("message_type"),
        scheduled_at_local=e.get("scheduled_at_local"),
        is_explicit_time=e.get("is_explicit_time", False),
        related_event_date=e.get("related_event_date"),
    )


# ── dataset (decision 2a: imported directly from tests/assistant/nlp) ──────────

def test_dataset_imports_canonical_25_cases():
    assert len(CASES) == 25
    assert [c.id for c in CASES if c.must_pass] == [1, 12, 13, 14, 15, 21, 22, 23]


def test_anchored_now_is_jerusalem_noon():
    now = anchored_now()
    assert now.tzinfo is not None
    assert (now.year, now.month, now.day, now.hour) == (2026, 6, 15, 12)


def test_select_cases_filters_by_id():
    sel = select_cases([1, 13])
    assert [c.id for c in sel] == [1, 13]
    assert len(select_cases(None)) == 25
    assert len(select_cases([])) == 25


# ── compare ───────────────────────────────────────────────────────────────────

def test_perfect_match_passes():
    case = next(c for c in CASES if c.id == 1)
    res = compare_case(case, _intent_from_expect(case))
    assert res.passed and not res.diffs


def test_status_mismatch_fails_and_is_listed_first():
    case = next(c for c in CASES if c.id == 1)  # expects PARSED
    actual = _intent_from_expect(case)
    actual.status = ParseStatus.NEEDS_CLARIFICATION
    actual.scheduled_at_local = None  # also diverges
    res = compare_case(case, actual)
    assert not res.passed
    assert res.first_diff.field == "status"


def test_send_date_vs_event_date_divergence_caught():
    # Case 12: event-date-only -> needs_clarification, scheduled_at_local None.
    case = next(c for c in CASES if c.id == 12)
    wrong = _intent_from_expect(case)
    # A parser that wrongly treats the event date as a send time:
    wrong.status = ParseStatus.PARSED
    wrong.scheduled_at_local = "2026-06-29T10:00:00"
    res = compare_case(case, wrong)
    assert not res.passed
    fields = {d.field for d in res.diffs}
    assert "status" in fields and "scheduled_at_local" in fields


def test_clarification_text_is_not_a_pass_key():
    case = next(c for c in CASES if c.id == 12)
    intent = _intent_from_expect(case)
    intent.clarification = "totally different wording"
    intent.inferred_notes = ["whatever"]
    assert compare_case(case, intent).passed


def test_only_pinned_fields_are_compared():
    # Case 25 pins no scheduled_at_local; a value there must NOT fail it.
    case = next(c for c in CASES if c.id == 25)
    intent = _intent_from_expect(case)
    intent.scheduled_at_local = "2026-06-16T10:00:00"
    assert "scheduled_at_local" not in case.expect
    assert compare_case(case, intent).passed


# ── evaluate loop (parser-agnostic, no network) ───────────────────────────────

def test_evaluate_all_pass_with_oracle_parser():
    by_text = {c.text: _intent_from_expect(c) for c in CASES}
    parser = FakeParser(by_text=by_text)
    results = asyncio.run(evaluate_cases(parser, list(CASES), now=anchored_now()))
    assert len(results) == 25
    assert all(r.passed for r in results)
    assert len(parser.calls) == 25
    # the loop anchors with our tz-aware now
    assert parser.calls[0][1].tzinfo is not None


def test_evaluate_supports_async_parser():
    case = next(c for c in CASES if c.id == 1)

    class AsyncParser:
        async def parse(self, raw_command, *, now=None):
            return _intent_from_expect(case)

    results = asyncio.run(evaluate_cases(AsyncParser(), [case], now=anchored_now()))
    assert results[0].passed


# ── report ────────────────────────────────────────────────────────────────────

def test_summary_flags_must_pass_hard_fail():
    case = next(c for c in CASES if c.id == 1)  # must_pass
    good = compare_case(case, _intent_from_expect(case))
    bad_actual = _intent_from_expect(case)
    bad_actual.scheduled_at_local = "2099-01-01T00:00:00"
    bad = compare_case(case, bad_actual)
    assert summarize([good])["hard_fail"] is False
    s = summarize([bad])
    assert s["hard_fail"] is True and s["must_pass_failed_ids"] == [1]


def test_format_report_contains_marks_and_no_secrets(monkeypatch):
    monkeypatch.setenv(KEY_ENV, "sk-should-never-be-printed")
    case = next(c for c in CASES if c.id == 1)
    res = compare_case(case, _intent_from_expect(case))
    text = format_report([res], model="claude-sonnet-4-6",
                         now_anchor="2026-06-15T12:00:00", mode="live")
    assert "PASS" in text and "claude-sonnet-4-6" in text
    assert "sk-should-never-be-printed" not in text


def test_to_dict_is_json_serializable():
    import json
    case = next(c for c in CASES if c.id == 12)
    res = compare_case(case, _intent_from_expect(case))
    doc = to_dict([res], model="m", now_anchor="n", mode="live")
    json.dumps(doc, ensure_ascii=False)  # must not raise
    assert doc["summary"]["total"] == 1


# ── safety gates ──────────────────────────────────────────────────────────────

def test_gates_block_without_flag(monkeypatch):
    monkeypatch.delenv(RUN_FLAG, raising=False)
    monkeypatch.setenv(KEY_ENV, "present")
    assert not live_allowed()
    assert any("RUN_LIVE_EVAL" in b for b in gate_blockers())


def test_gates_block_without_key(monkeypatch):
    monkeypatch.setenv(RUN_FLAG, "1")
    monkeypatch.delenv(KEY_ENV, raising=False)
    assert not live_allowed()
    assert any("API_KEY" in b for b in gate_blockers())


def test_gates_allow_with_both(monkeypatch):
    monkeypatch.setenv(RUN_FLAG, "1")
    monkeypatch.setenv(KEY_ENV, "present")
    assert live_allowed() and gate_blockers() == []


def test_run_blocked_makes_no_client(monkeypatch, capsys):
    # Flag unset -> run() must return cleanly and construct no parser/client.
    monkeypatch.delenv(RUN_FLAG, raising=False)
    monkeypatch.setenv(KEY_ENV, "present")

    def _boom_parser(*a, **k):
        raise AssertionError("ClaudeParser must not be constructed when blocked")

    monkeypatch.setattr(
        "app.assistant.core.llm_parser.ClaudeParser", _boom_parser, raising=True
    )
    code, doc = run(do_print=True)
    assert code == 0 and doc is None
    out = capsys.readouterr().out
    assert "BLOCKED" in out
    assert "About to run" in out  # pre-flight count still shown


def test_gate_blockers_never_echo_key_value(monkeypatch):
    monkeypatch.delenv(RUN_FLAG, raising=False)
    monkeypatch.setenv(KEY_ENV, "super-secret-value")
    assert all("super-secret-value" not in b for b in gate_blockers())


# ── unicode-safe console output (regression: Windows cp1252 crash) ────────────

class _Cp1252Stream:
    """Simulates a default Windows console: only encodes cp1252; non-encodable
    chars (Hebrew, the ★ marker) raise UnicodeEncodeError on write — exactly
    the failure observed when printing the live report."""

    encoding = "cp1252"

    def __init__(self):
        self.data = ""

    def write(self, s):
        s.encode("cp1252")  # raises UnicodeEncodeError on Hebrew / ★
        self.data += s
        return len(s)


def test_safe_print_does_not_crash_on_cp1252_stream():
    stream = _Cp1252Stream()
    safe_print("ascii only", stream=stream)
    assert "ascii only" in stream.data


def test_full_report_with_unicode_survives_cp1252_stdout():
    # Regression: the live report contains Hebrew case text AND the ★ marker.
    case = next(c for c in CASES if c.id == 1)
    res = compare_case(case, _intent_from_expect(case))
    text = format_report([res], model="claude-sonnet-4-6",
                         now_anchor="2026-06-15T12:00:00 IDT", mode="live")
    assert "★" in text  # the offending glyph is present
    stream = _Cp1252Stream()
    safe_print(text, stream=stream)  # must NOT raise
    assert "case  1" in stream.data        # ASCII content preserved
    assert "claude-sonnet-4-6" in stream.data


def test_safe_print_preserves_unicode_on_utf8_stream():
    import io
    buf = io.StringIO()  # StringIO accepts any unicode (UTF-8-like)
    safe_print("שלום ★", stream=buf)
    assert "שלום ★" in buf.getvalue()


def test_configure_utf8_output_handles_missing_reconfigure(monkeypatch):
    class _NoReconfigure:
        encoding = "cp1252"

    monkeypatch.setattr(sys, "stdout", _NoReconfigure())
    monkeypatch.setattr(sys, "stderr", _NoReconfigure())
    _configure_utf8_output()  # must be a safe no-op, not raise


def test_configure_utf8_output_requests_utf8(monkeypatch):
    calls = []

    class _Reconfigurable:
        encoding = "cp1252"

        def reconfigure(self, **kw):
            calls.append(kw)

    monkeypatch.setattr(sys, "stdout", _Reconfigurable())
    monkeypatch.setattr(sys, "stderr", _Reconfigurable())
    _configure_utf8_output()
    assert all(c.get("encoding") == "utf-8" for c in calls)
    assert len(calls) == 2


# ── isolation: no Supabase/data adapter, no eager Anthropic ───────────────────

def _imported_modules(mod):
    tree = ast.parse(inspect.getsource(mod))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_harness_never_imports_data_layer():
    for mod in (dataset_mod, compare_mod, report_mod, run_eval_mod):
        imports = _imported_modules(mod)
        assert not any(n.startswith("app.assistant.data") for n in imports), imports
        assert not any("supabase" in n.lower() for n in imports), imports


def test_importing_harness_constructs_no_anthropic_client():
    # The autouse fixture booms on AsyncAnthropic(); re-importing the package
    # here must not trip it (construction is deferred to a gated live run).
    import importlib

    for mod in (dataset_mod, compare_mod, report_mod, run_eval_mod):
        importlib.reload(mod)  # would raise via _boom if it constructed a client

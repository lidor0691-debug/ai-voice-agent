"""
Fix tests — zero-caller-content calls must never be summarized by the LLM.

Incident 2026-07-21: a call whose transcript held only Maya's greeting
(caller_lines == 0) made the summary model fabricate a caller request
("...לבדוק את פוליסת הביטוח... להוזיל את הפרמיה") and a Maya reply
("אני אעביר את הבקשה שלך למומחה שלנו"). Neither was ever spoken.

The fix: skip the summarizer entirely when there is no valid caller content and
use a deterministic, truthful summary — consistently in the email payload and
leads.last_call_summary. Normal two-sided calls are unchanged.
"""
from __future__ import annotations

import os
import pathlib

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pytest

import app.routes.voice_openai_live as vol
import app.services.voice_shared as vs


# ── the caller-content guard ─────────────────────────────────────────────────

class TestHasValidCallerContent:
    def test_empty_and_whitespace_only_are_not_content(self):
        # requirement 2: empty/whitespace-only caller lines → no valid content
        assert vol._has_valid_caller_content([]) is False
        assert vol._has_valid_caller_content(None) is False
        assert vol._has_valid_caller_content([""]) is False
        assert vol._has_valid_caller_content(["   ", "\t", "\n"]) is False

    def test_any_non_empty_line_is_content(self):
        assert vol._has_valid_caller_content(["שלום"]) is True
        assert vol._has_valid_caller_content(["", "  ", "ביטוח רכב"]) is True


# ── deterministic summary content ────────────────────────────────────────────

class TestDeterministicSummary:
    def test_exact_required_text(self):
        assert vol._EMPTY_CALLER_SUMMARY == (
            "לא התקבל מהלקוח תוכן ברור שניתן לסכם. "
            "ייתכן שהשיחה נותקה או שהדיבור לא תומלל."
        )

    def test_no_dialogue_formatting(self):
        # requirement 4: never any "הלקוח:" / "מאיה:" dialogue lines
        assert "הלקוח:" not in vol._EMPTY_CALLER_SUMMARY
        assert "מאיה:" not in vol._EMPTY_CALLER_SUMMARY


# ── the finalization gate is wired correctly (source-level proof) ────────────

class TestFinalizationWiring:
    def _src(self):
        return pathlib.Path(vol.__file__).read_text(encoding="utf-8")

    def test_summarizer_gated_on_caller_content(self):
        src = self._src()
        assert "if _has_valid_caller_content(_caller_lines):" in src
        # the ONLY summarizer call sits inside that guarded branch
        gate = src.split("if _has_valid_caller_content(_caller_lines):")[1].split("print(")[0]
        assert "await _summarize_transcript(" in gate
        assert "_summary = _EMPTY_CALLER_SUMMARY" in gate
        # and there is exactly one summarizer call site in the whole module
        assert src.count("await _summarize_transcript(") == 1

    def test_summary_flows_to_both_destinations(self):
        src = self._src()
        # email payload uses _summary
        assert '"summary":               _summary,' in src
        # leads.last_call_summary prefers _summary (deterministic when empty-caller)
        assert "_last_call_summary = _summary or (" in src
        assert '"last_call_summary": _last_call_summary,' in src


# ── summarizer is not called; behavior preserved for two-sided calls ─────────

class TestSummarizerInvocation:
    @pytest.mark.asyncio
    async def test_two_sided_transcript_calls_llm_unchanged(self, monkeypatch):
        """requirement 3: normal call → existing summary flow, LLM invoked."""
        calls = {"n": 0}

        async def fake_summarize(full_transcript, caller_names_allowed=None):
            calls["n"] += 1
            return "סיכום אמיתי מהמודל."

        monkeypatch.setattr(vol, "_summarize_transcript", fake_summarize)

        caller_lines = ["אני רוצה לבדוק את הפוליסה שלי"]
        assistant_lines = ["היי, איך אפשר לעזור?"]
        # replicate the exact finalization decision
        if vol._has_valid_caller_content(caller_lines):
            summary = await vol._summarize_transcript(
                vol._full_transcript(caller_lines, assistant_lines))
        else:
            summary = vol._EMPTY_CALLER_SUMMARY
        assert calls["n"] == 1
        assert summary == "סיכום אמיתי מהמודל."

    @pytest.mark.asyncio
    async def test_assistant_only_transcript_skips_llm(self, monkeypatch):
        """requirement 1: assistant-only → LLM NOT called, deterministic summary,
        no fabricated dialogue."""
        calls = {"n": 0}

        async def fake_summarize(full_transcript, caller_names_allowed=None):
            calls["n"] += 1
            # If ever (wrongly) called, return a fabrication to make failure loud.
            return "הלקוח: אני רוצה להוזיל את הפרמיה.\nמאיה: אני אעביר למומחה שלנו."

        monkeypatch.setattr(vol, "_summarize_transcript", fake_summarize)

        caller_lines = []                       # only Maya's greeting existed
        assistant_lines = ["היי, הגעתם למשרד של רועי לוי, מדברת מאיה. איך אפשר לעזור?"]
        if vol._has_valid_caller_content(caller_lines):
            summary = await vol._summarize_transcript(
                vol._full_transcript(caller_lines, assistant_lines))
        else:
            summary = vol._EMPTY_CALLER_SUMMARY

        assert calls["n"] == 0                  # LLM never called
        assert summary == vol._EMPTY_CALLER_SUMMARY
        assert "הלקוח:" not in summary and "מאיה:" not in summary
        assert "פרמיה" not in summary and "מומחה" not in summary

    @pytest.mark.asyncio
    async def test_whitespace_only_caller_lines_skip_llm(self, monkeypatch):
        """requirement 2: whitespace-only caller lines → treated as no content."""
        calls = {"n": 0}

        async def fake_summarize(full_transcript, caller_names_allowed=None):
            calls["n"] += 1
            return "לא אמור להיקרא"

        monkeypatch.setattr(vol, "_summarize_transcript", fake_summarize)
        caller_lines = ["   ", "\t"]
        summary = (await vol._summarize_transcript("x")
                   if vol._has_valid_caller_content(caller_lines)
                   else vol._EMPTY_CALLER_SUMMARY)
        assert calls["n"] == 0
        assert summary == vol._EMPTY_CALLER_SUMMARY


# ── leads.last_call_summary receives the deterministic value ─────────────────

class TestLeadDestination:
    def test_empty_caller_last_call_summary_is_deterministic(self):
        # replicate line: _last_call_summary = _summary or (topic|notes or None)
        _summary = vol._EMPTY_CALLER_SUMMARY       # empty-caller path
        _summary_parts = []                        # extraction skipped → no topic/notes
        _last_call_summary = _summary or (" | ".join(_summary_parts) or None)
        assert _last_call_summary == vol._EMPTY_CALLER_SUMMARY

    def test_two_sided_last_call_summary_uses_model_output(self):
        _summary = "סיכום אמיתי."
        _summary_parts = ["נושא: ביטוח רכב"]
        _last_call_summary = _summary or (" | ".join(_summary_parts) or None)
        assert _last_call_summary == "סיכום אמיתי."


# ── defense-in-depth prompt instruction ──────────────────────────────────────

class TestPromptDefense:
    def test_no_caller_lines_rule_present(self):
        p = vs._build_summary_prompt("מאיה: היי", caller_names_allowed=[])
        assert "אם אין שורות \"לקוח:\"" in p
        assert "אל תחזיר דו-שיח" in p
        assert "לא התקבל מהלקוח תוכן ברור" in p

    def test_existing_rules_still_present(self):
        # smallest change: the RC3 name guard and format rules are untouched
        p = vs._build_summary_prompt("לקוח: שלום", caller_names_allowed=[])
        assert "אם שם פרטי מופיע רק בדברי מאיה" in p
        assert "החזר את הסיכום בלבד" in p

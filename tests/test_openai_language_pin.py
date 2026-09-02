"""
Output-language pin.

Incident 2026-09-02: Maya answered one of Roi's customers in ENGLISH. The
tenant's system_prompt carries no language instruction of any kind — she spoke
Hebrew only because that prompt is written in Hebrew. Nothing constrained the
model's OUTPUT language, and gpt-realtime defaults to English when the input is
unclear.

These tests pin the three facts that made the bug possible, so a future edit
cannot quietly undo the fix.
"""
from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import app.routes.voice_openai_live as vol


class TestLanguagePinContent:
    def test_is_a_suffix_that_composes(self):
        assert vol._LANGUAGE_PIN_INSTRUCTION.startswith("\n\n")

    def test_pins_hebrew_unconditionally(self):
        text = vol._LANGUAGE_PIN_INSTRUCTION
        assert "עברית" in text
        assert "תמיד" in text
        assert "ללא יוצא מן הכלל" in text

    def test_covers_the_unclear_audio_case(self):
        """The moment the model reaches for English is when it did not
        understand — so the rule has to name that case explicitly."""
        text = vol._LANGUAGE_PIN_INSTRUCTION
        assert "לא הבנת" in text
        assert "האודיו לא ברור" in text
        assert "בקשי בעברית שיחזור" in text

    def test_names_english_as_the_thing_to_avoid(self):
        assert "לעולם אל תעברי לאנגלית" in vol._LANGUAGE_PIN_INSTRUCTION

    def test_says_nothing_about_business_logic(self):
        """It constrains language only — insurance logic, tone and the office
        identity stay owned by the tenant prompt."""
        for foreign in ("ביטוח", "רועי", "פוליסה", "מאיה"):
            assert foreign not in vol._LANGUAGE_PIN_INSTRUCTION


class TestEveryAppAuthoredUtteranceIsAnchored:
    """The incident's natural experiment: the ONE utterance carrying the Hebrew
    anchor came out Hebrew, the one without it came out English. Every
    app-authored spoken instruction must therefore carry it — a verbatim Hebrew
    line does not anchor itself."""

    def test_stage1_is_anchored(self):
        assert vol._HEBREW_SPEECH_ANCHOR in vol._stage1_instruction()

    def test_exact_line_instructions_are_anchored(self):
        instr = vol._exact_line_instruction("שלום עולם")
        assert vol._HEBREW_SPEECH_ANCHOR in instr
        assert 'בלי שום תוספת: "שלום עולם"' in instr   # verbatim still enforced

    def test_reprompt_is_anchored(self):
        """Silence is an 'I don't know what is happening' moment — precisely
        where the model reached for English."""
        assert vol._HEBREW_SPEECH_ANCHOR in vol._REPROMPT_INSTRUCTION

    def test_legacy_alias_still_resolves(self):
        assert vol._STAGE1_HEBREW_ANCHOR == vol._HEBREW_SPEECH_ANCHOR

    def test_anchor_is_not_smuggled_into_the_session_prompt(self):
        """It is a per-response instruction; the session-level pin is separate."""
        assert vol._HEBREW_SPEECH_ANCHOR not in vol._NAME_PROTOCOL_INSTRUCTION

    def test_stt_language_pin_is_input_side_only(self):
        """transcription.language governs the caller transcript, not Maya's
        speech — it is a side-channel and cannot fix an output-language bug."""
        block = vol._build_input_transcription()
        assert block["language"] == "he"
        session = vol._build_session_update("PROMPT")["session"]
        # Nothing in the audio OUTPUT config carries a language at all.
        assert "language" not in session["audio"]["output"]

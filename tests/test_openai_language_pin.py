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


class TestExistingHebrewDirectiveIsNotASubstitute:
    def test_stage1_anchor_is_scoped_to_the_first_word_only(self):
        """The pre-existing Hebrew directive is attached to the Stage-1 "הלו?"
        response instruction; it never reaches the session instruction, which is
        why it could not prevent the incident."""
        assert "עברית" in vol._STAGE1_HEBREW_ANCHOR
        assert vol._STAGE1_HEBREW_ANCHOR in vol._stage1_instruction()
        assert vol._STAGE1_HEBREW_ANCHOR not in vol._NAME_PROTOCOL_INSTRUCTION

    def test_stt_language_pin_is_input_side_only(self):
        """transcription.language governs the caller transcript, not Maya's
        speech — it is a side-channel and cannot fix an output-language bug."""
        block = vol._build_input_transcription()
        assert block["language"] == "he"
        session = vol._build_session_update("PROMPT")["session"]
        # Nothing in the audio OUTPUT config carries a language at all.
        assert "language" not in session["audio"]["output"]

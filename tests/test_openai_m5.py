"""
M5 polish tests — native speaking speed (audio.output.speed) and the
chronological RTL-safe Hebrew transcript HTML for the email.

Both features are ADDITIVE: the default speed is 1.0 (deploy is behavior
neutral) and transcript_html sits alongside the untouched transcript_excerpt.
Nothing in M2/M3/M4 turn-taking, VAD, marks, extraction or summary changes.
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
from app.routes.voice_openai_live import (
    _parse_realtime_speed, _transcript_html, _transcript_excerpt, _full_transcript,
)

CALLER = "לקוח"
MAYA = "מאיה"


def _t(role, text):
    return {"role": role, "text": text}


# ── Task A: native speaking speed ────────────────────────────────────────────

class TestSpeed:
    def test_default_is_one_point_zero(self):
        # unset env → behavior-neutral default
        if not os.getenv("OPENAI_REALTIME_SPEED"):
            assert vol.OPENAI_REALTIME_SPEED == 1.0
        assert vol.OPENAI_REALTIME_SPEED_DEFAULT == 1.0
        assert _parse_realtime_speed(None) == 1.0
        assert _parse_realtime_speed("") == 1.0
        assert _parse_realtime_speed("   ") == 1.0

    def test_valid_pilot_value_accepted(self):
        assert _parse_realtime_speed("1.06") == 1.06
        assert _parse_realtime_speed(" 1.06 ") == 1.06

    def test_range_bounds_inclusive(self):
        assert _parse_realtime_speed("0.7") == 0.7
        assert _parse_realtime_speed("1.3") == 1.3

    @pytest.mark.parametrize("bad", ["10.6", "0.06", "1.31", "0.69", "-1", "abc",
                                     "nan", "inf", "-inf", "1,06"])
    def test_invalid_or_extreme_falls_back_to_one(self, bad):
        assert _parse_realtime_speed(bad) == 1.0

    def test_speed_present_in_session_payload(self):
        out = vol._build_session_update("P")["session"]["audio"]["output"]
        assert out["speed"] == vol.OPENAI_REALTIME_SPEED
        assert out["voice"] == vol.OPENAI_REALTIME_VOICE
        assert out["format"] == {"type": "audio/pcmu"}

    def test_speed_change_does_not_touch_vad_or_input(self):
        """Pace is output-only: the M3 VAD block and STT pin stay byte-identical."""
        s = vol._build_session_update("P")["session"]
        td = s["audio"]["input"]["turn_detection"]
        assert td == {
            "type": "server_vad",
            "threshold": 0.6,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 700,
            "create_response": False,
            "interrupt_response": False,
        }
        assert s["audio"]["input"]["transcription"]["language"] == "he"
        assert s["type"] == "realtime"
        assert s["output_modalities"] == ["audio"]

    def test_no_prompt_speed_instruction_introduced(self):
        """Native control ONLY — no wording about speaking faster anywhere."""
        src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
        for banned in ("מהר יותר", "דברי מהר", "בקצב מהיר", "speak faster",
                       "talk faster", "quickly"):
            assert banned not in src
        # the prompt builders are untouched
        assert "פתיחת שיחה (פעם אחת בלבד)" in vol._openai_opening_instruction("B", "fm")
        assert "רק כדי שאוכל לרשום את הפנייה כמו שצריך, עם מי אני מדברת?" in vol._NAME_PROTOCOL_INSTRUCTION


# ── Task B: chronological transcript HTML ────────────────────────────────────

class TestTranscriptHtml:
    def test_chronological_order_preserved(self):
        turns = [_t(CALLER, "שלום"), _t(MAYA, "היי"), _t(CALLER, "תודה"), _t(MAYA, "בבקשה")]
        out = _transcript_html(turns)
        # positions follow capture order, alternating caller/Maya
        assert out.index("שלום") < out.index("היי") < out.index("תודה") < out.index("בבקשה")

    def test_four_alternating_turns_labels_attached(self):
        turns = [_t(CALLER, "אחת"), _t(MAYA, "שתיים"), _t(CALLER, "שלוש"), _t(MAYA, "ארבע")]
        out = _transcript_html(turns)
        assert out.count('<div style="margin-bottom:12px;">') == 4
        assert out.count(f"<strong>{CALLER}</strong>") == 2
        assert out.count(f"<strong>{MAYA}</strong>") == 2
        # each label precedes its own message div
        for label, text in ((CALLER, "אחת"), (MAYA, "שתיים"), (CALLER, "שלוש"), (MAYA, "ארבע")):
            block = out.split(text)[0]
            assert block.rindex(f"<strong>{label}</strong>") > block.rindex('margin-bottom:12px;') - 1

    def test_rtl_container_and_per_message_bidi(self):
        out = _transcript_html([_t(CALLER, "שלום")])
        assert 'dir="rtl"' in out
        assert "direction:rtl" in out and "text-align:right" in out
        assert 'dir="auto"' in out
        assert "unicode-bidi:plaintext" in out

    def test_phone_numbers_isolated_ltr(self):
        for phone in ("+972 52-462-0550", "052-4620550", "+972524620550"):
            out = _transcript_html([_t(CALLER, f"תחזרו אליי ל־{phone}")])
            assert '<span dir="ltr">' in out, phone
            assert phone in out

    def test_mixed_hebrew_english_readable(self):
        out = _transcript_html([_t(CALLER, "אני רוצה ביטוח Term Life בבקשה")])
        assert "Term Life" in out
        assert 'dir="auto"' in out and "unicode-bidi:plaintext" in out

    def test_line_breaks_become_br(self):
        out = _transcript_html([_t(CALLER, "שורה ראשונה\nשורה שנייה")])
        assert "<br>" in out
        assert "\n" not in out.replace("\\n", "")

    def test_html_is_escaped(self):
        out = _transcript_html([_t(CALLER, "<script>alert('x')</script> & <b>")])
        assert "<script>" not in out
        assert "&lt;script&gt;" in out and "&amp;" in out

    def test_empty_and_blank_turns_yield_empty_string(self):
        assert _transcript_html([]) == ""
        assert _transcript_html(None) == ""
        assert _transcript_html([_t(CALLER, "   "), _t(MAYA, "")]) == ""

    @pytest.mark.parametrize("bad", [
        [{"role": CALLER}],                 # missing text
        [{"text": "שלום"}],                 # missing role
        ["not a dict"],                     # wrong type
        [None],
    ])
    def test_malformed_input_fails_safely(self, bad):
        assert _transcript_html(bad) == ""   # → Make falls back to raw excerpt

    def test_truncation_keeps_earliest_turns_and_never_reorders(self):
        turns = [_t(CALLER if i % 2 == 0 else MAYA, f"הודעה מספר {i} " + "א" * 60)
                 for i in range(40)]
        out = _transcript_html(turns, max_turns=20, max_chars=1200)
        assert len(out) <= 1200
        assert "הודעה מספר 0" in out          # earliest kept
        assert "…" in out                      # truncation marker
        assert out.index("הודעה מספר 0") < out.index("הודעה מספר 1")

    def test_max_turns_cap(self):
        turns = [_t(CALLER, f"שורה {i}") for i in range(30)]
        out = _transcript_html(turns, max_turns=5, max_chars=100000)
        assert out.count('<div style="margin-bottom:12px;">') == 5
        assert "…" in out


# ── Regression pins: nothing else changed ────────────────────────────────────

class TestNoRegression:
    def test_transcript_excerpt_unchanged_grouped_behavior(self):
        caller = ["שלום", "אני צריך עזרה"]
        assistant = ["היי", "בשמחה"]
        excerpt = _transcript_excerpt(caller, assistant)
        # still the raw, role-GROUPED string (M1.1 behavior, byte-identical)
        assert excerpt == "לקוח: שלום\nלקוח: אני צריך עזרה\nמאיה: היי\nמאיה: בשמחה"
        assert excerpt == _full_transcript(caller, assistant)

    def test_raw_full_transcript_untouched(self):
        assert _full_transcript(["א"], ["ב"]) == "לקוח: א\nמאיה: ב"

    def test_payload_has_additive_field_and_keeps_excerpt(self):
        src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
        assert '"transcript_html":       _transcript_html_value,' in src
        assert '"transcript_excerpt":    _excerpt,' in src
        assert '"summary":               _summary,' in src
        # summary is still built before/above the transcript fields
        assert src.index('"summary":               _summary,') < src.index('"transcript_html"')

    def test_turns_captured_at_both_sites_and_exclude_held_fragments(self):
        src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
        # caller capture guarded by the M4 held-greeting + barge false-trigger condition
        assert 'if _text and _decision not in ("held_greeting", "false_barge"):' in src
        caller_block = src.split('if _text and _decision not in ("held_greeting", "false_barge"):')[1][:300]
        assert '_transcript_turns.append({"role": "לקוח"' in caller_block
        assert '_transcript_turns.append({"role": "מאיה"' in src
        assert src.count("_transcript_turns.append(") == 2

    def test_turn_list_is_fresh_per_call(self):
        src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
        # declared inside the handler (indented), exactly once — never a module global
        assert "    _transcript_turns: list[dict] = []" in src
        assert "\n_transcript_turns" not in src
        assert src.count("_transcript_turns: list[dict] = []") == 1

    def test_extraction_and_summary_inputs_unchanged(self):
        src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
        # extraction still customer-lines-only; summary still both role buffers
        assert "transcript_text = _customer_transcript(_caller_lines)" in src
        assert "_full_text = _full_transcript(_caller_lines, _assistant_lines)" in src
        assert "caller_names_allowed=_allowed_names" in src

    def test_m4_gate_untouched(self):
        assert vol.GREETING_BARGE_MIN_CHARS == 10
        assert vol.GREETING_BARGE_MIN_DUR_S == 1.2
        assert vol.is_verified_greeting_interruption("תודה", 1.10) is False
        assert vol.is_verified_greeting_interruption("רק נשמע", 2.16) is False
        assert vol.is_verified_greeting_interruption("אני רוצה לברר לגבי הפנסיה שלי", 2.0) is True

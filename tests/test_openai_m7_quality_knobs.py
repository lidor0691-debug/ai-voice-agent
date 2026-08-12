"""
M7 conversation-quality knobs.

Hebrew phone quality is a calibration problem and every round costs a live
call, so the session-level levers (STT model + vocabulary prompt, input noise
reduction, turn detection, reply ceiling) are environment-driven rather than
hardcoded, and the turn-level dialogue discipline is a tenant-gated instruction.

THE LOAD-BEARING PROPERTY, asserted first and repeatedly below: with none of
the M7 variables set, the session payload is byte-identical to the M6 payload
and the instruction is untouched. Enabling anything is an explicit act.
"""
from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pytest

import app.routes.voice_openai_live as vol
import app.services.voice_shared as vs
from app.routes.voice_openai_live import _parse_bounded_float, _parse_bounded_int


@pytest.fixture
def neutral(monkeypatch):
    """Force every M7 knob to its unset/default value regardless of the ambient
    environment, so 'default == M6' is assertable on any machine."""
    monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_PROMPT", "")
    monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_KEYWORDS", [])
    monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_DELAY", "")
    monkeypatch.setattr(vol, "OPENAI_INPUT_NOISE_REDUCTION", "")
    monkeypatch.setattr(vol, "OPENAI_MAX_OUTPUT_TOKENS", None)
    monkeypatch.setattr(vol, "OPENAI_VAD_TYPE", "server_vad")
    monkeypatch.setattr(vol, "OPENAI_VAD_EAGERNESS", "medium")
    monkeypatch.setattr(vol, "OPENAI_VAD_THRESHOLD", 0.6)
    monkeypatch.setattr(vol, "OPENAI_VAD_SILENCE_MS", 700)
    monkeypatch.setattr(vol, "OPENAI_VAD_PREFIX_MS", 300)
    monkeypatch.setattr(vol, "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-realtime-whisper")
    monkeypatch.setattr(vol, "OPENAI_REALTIME_VOICE", "marin")
    monkeypatch.setattr(vol, "OPENAI_REALTIME_SPEED", 1.0)


# ── The regression fence: unset environment == M6 payload ────────────────────

# Byte-for-byte what the pre-M7 builder produced (M2 VAD numbers, M5 speed).
M6_SESSION = {
    "type": "session.update",
    "session": {
        "type": "realtime",
        "output_modalities": ["audio"],
        "instructions": "PROMPT",
        "audio": {
            "input": {
                "format": {"type": "audio/pcmu"},
                "transcription": {"model": "gpt-realtime-whisper", "language": "he"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.6,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 700,
                    "create_response": False,
                    "interrupt_response": False,
                },
            },
            "output": {
                "format": {"type": "audio/pcmu"},
                "voice": "marin",
                "speed": 1.0,
            },
        },
    },
}


class TestDefaultIsM6:
    def test_unset_environment_reproduces_m6_payload_exactly(self, neutral):
        assert vol._build_session_update("PROMPT") == M6_SESSION

    def test_no_optional_fields_leak_in_by_default(self, neutral):
        audio_in = vol._build_session_update("P")["session"]["audio"]["input"]
        assert "noise_reduction" not in audio_in
        assert "prompt" not in audio_in["transcription"]
        assert "max_output_tokens" not in vol._build_session_update("P")["session"]


# ── Bounded parsers ──────────────────────────────────────────────────────────

class TestParsers:
    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_float_unset_returns_default(self, raw):
        assert _parse_bounded_float(raw, 0.1, 0.9, 0.5, "X") == 0.5

    @pytest.mark.parametrize("bad", ["abc", "0,6", "nan", "inf", "-inf", "0.05", "0.95"])
    def test_float_invalid_or_out_of_range_returns_default(self, bad):
        assert _parse_bounded_float(bad, 0.1, 0.9, 0.5, "X") == 0.5

    def test_float_bounds_are_inclusive(self):
        assert _parse_bounded_float("0.1", 0.1, 0.9, 0.5, "X") == 0.1
        assert _parse_bounded_float("0.9", 0.1, 0.9, 0.5, "X") == 0.9

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_int_unset_returns_default(self, raw):
        assert _parse_bounded_int(raw, 1, 10, None, "Y") is None

    @pytest.mark.parametrize("bad", ["abc", "1.5", "0", "11", "-3"])
    def test_int_invalid_or_out_of_range_returns_default(self, bad):
        assert _parse_bounded_int(bad, 1, 10, None, "Y") is None

    def test_int_bounds_are_inclusive(self):
        assert _parse_bounded_int("1", 1, 10, None, "Y") == 1
        assert _parse_bounded_int("10", 1, 10, None, "Y") == 10

    def test_parsers_never_raise_on_non_string_input(self):
        """Config parsing must be total: a wrong-typed value degrades to the
        default, it never crashes the module at import time."""
        for weird in [object(), [], {}, b"3"]:
            assert _parse_bounded_float(weird, 0.0, 1.0, 0.5, "X") == 0.5
            assert _parse_bounded_int(weird, 0, 5, None, "Y") is None

    def test_already_numeric_input_is_accepted(self):
        assert _parse_bounded_float(0.75, 0.0, 1.0, 0.5, "X") == 0.75
        assert _parse_bounded_int(3, 0, 5, None, "Y") == 3


# ── STT: model + Hebrew pin + vocabulary prompt ──────────────────────────────

class TestTranscription:
    def test_language_stays_pinned_to_hebrew(self, neutral):
        assert vol._build_input_transcription()["language"] == "he"

    def test_model_is_env_driven(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
        block = vol._build_input_transcription()
        assert block["model"] == "gpt-4o-transcribe"
        assert block["language"] == "he"

    def test_prompt_omitted_when_unset(self, neutral):
        assert "prompt" not in vol._build_input_transcription()

    def test_prompt_included_when_set(self, neutral, monkeypatch):
        hint = "שיחה בעברית עם משרד ביטוח. רועי לוי, ביטוח חיים, חידוש פוליסה."
        monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_PROMPT", hint)
        assert vol._build_input_transcription()["prompt"] == hint

    def test_prompt_reaches_the_session_payload(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_PROMPT", "מונחי ביטוח")
        tr = vol._build_session_update("P")["session"]["audio"]["input"]["transcription"]
        assert tr["prompt"] == "מונחי ביטוח"

    def test_plural_languages_field_is_never_sent(self, neutral, monkeypatch):
        """The API rejects a session carrying both `language` and `languages`.
        We always send the singular; the newer models normalise it themselves."""
        for model in ["gpt-realtime-whisper", "gpt-4o-transcribe", "gpt-live-transcribe"]:
            monkeypatch.setattr(vol, "OPENAI_REALTIME_TRANSCRIBE_MODEL", model)
            block = vol._build_input_transcription()
            assert "languages" not in block
            assert block["language"] == "he"


class TestKeywordsAndDelay:
    """These fields exist only on the newer transcribe models. gpt-4o-transcribe
    REJECTS `keywords` outright, and a rejected session.update drops the call —
    so an unsupported pairing must degrade, never reach the wire."""

    def test_keyword_parsing_strips_and_drops_empties(self):
        assert vol._parse_keywords(" רועי לוי , ביטוח חיים ,, ") == ["רועי לוי", "ביטוח חיים"]

    @pytest.mark.parametrize("raw", [None, "", "   ", ",,,"])
    def test_keyword_parsing_of_nothing_is_empty(self, raw):
        assert vol._parse_keywords(raw) == []

    @pytest.mark.parametrize("bad", ["a<b", "a>b", "a\nb", "a\rb"])
    def test_forbidden_characters_are_dropped(self, bad):
        assert vol._parse_keywords(f"טוב,{bad}") == ["טוב"]

    def test_keywords_sent_for_capable_model(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-live-transcribe")
        monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_KEYWORDS", ["רועי לוי"])
        assert vol._build_input_transcription()["keywords"] == ["רועי לוי"]

    @pytest.mark.parametrize(
        "model", ["gpt-4o-transcribe", "gpt-realtime-whisper", "whisper-1", "gpt-4o-mini-transcribe"]
    )
    def test_keywords_never_sent_to_a_model_that_rejects_them(self, neutral, monkeypatch, model):
        monkeypatch.setattr(vol, "OPENAI_REALTIME_TRANSCRIBE_MODEL", model)
        monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_KEYWORDS", ["רועי לוי"])
        assert "keywords" not in vol._build_input_transcription()

    @pytest.mark.parametrize("delay", ["minimal", "low", "medium", "high", "xhigh"])
    def test_valid_delay_values(self, neutral, monkeypatch, delay):
        monkeypatch.setattr(vol, "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-live-transcribe")
        monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_DELAY", delay)
        assert vol._build_input_transcription()["delay"] == delay

    def test_invalid_delay_is_omitted(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-live-transcribe")
        monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_DELAY", "instant")
        assert "delay" not in vol._build_input_transcription()

    def test_delay_not_sent_to_incapable_model(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
        monkeypatch.setattr(vol, "OPENAI_TRANSCRIBE_DELAY", "medium")
        assert "delay" not in vol._build_input_transcription()


# ── Turn detection ───────────────────────────────────────────────────────────

class TestTurnDetection:
    def test_server_vad_defaults_are_the_m2_values(self, neutral):
        assert vol._build_turn_detection() == M6_SESSION["session"]["audio"]["input"][
            "turn_detection"
        ]

    def test_server_vad_numbers_are_env_driven(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_VAD_THRESHOLD", 0.5)
        monkeypatch.setattr(vol, "OPENAI_VAD_SILENCE_MS", 500)
        monkeypatch.setattr(vol, "OPENAI_VAD_PREFIX_MS", 200)
        td = vol._build_turn_detection()
        assert (td["threshold"], td["silence_duration_ms"], td["prefix_padding_ms"]) == (
            0.5, 500, 200
        )

    def test_semantic_vad_shape(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_VAD_TYPE", "semantic_vad")
        monkeypatch.setattr(vol, "OPENAI_VAD_EAGERNESS", "low")
        td = vol._build_turn_detection()
        assert td["type"] == "semantic_vad"
        assert td["eagerness"] == "low"
        # semantic_vad takes no numeric timing fields
        assert "threshold" not in td and "silence_duration_ms" not in td

    def test_unknown_eagerness_falls_back_to_medium(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_VAD_TYPE", "semantic_vad")
        monkeypatch.setattr(vol, "OPENAI_VAD_EAGERNESS", "turbo")
        assert vol._build_turn_detection()["eagerness"] == "medium"

    def test_unknown_vad_type_falls_back_to_server_vad(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_VAD_TYPE", "magic_vad")
        assert vol._build_turn_detection()["type"] == "server_vad"

    @pytest.mark.parametrize("vad_type", ["server_vad", "semantic_vad"])
    def test_app_owned_turn_taking_is_never_surrendered(self, neutral, monkeypatch, vad_type):
        """The M2/RC1 invariant: the server must never create or cancel a
        response on its own, in ANY turn-detection mode."""
        monkeypatch.setattr(vol, "OPENAI_VAD_TYPE", vad_type)
        td = vol._build_turn_detection()
        assert td["create_response"] is False
        assert td["interrupt_response"] is False


# ── Input noise reduction ────────────────────────────────────────────────────

class TestNoiseReduction:
    @pytest.mark.parametrize("value", ["near_field", "far_field"])
    def test_valid_profiles_are_applied(self, neutral, monkeypatch, value):
        monkeypatch.setattr(vol, "OPENAI_INPUT_NOISE_REDUCTION", value)
        audio_in = vol._build_session_update("P")["session"]["audio"]["input"]
        assert audio_in["noise_reduction"] == {"type": value}

    @pytest.mark.parametrize("value", ["", "off", "none", "true", "nearfield", "NEAR FIELD"])
    def test_invalid_values_omit_the_field_entirely(self, neutral, monkeypatch, value):
        monkeypatch.setattr(vol, "OPENAI_INPUT_NOISE_REDUCTION", value)
        audio_in = vol._build_session_update("P")["session"]["audio"]["input"]
        assert "noise_reduction" not in audio_in


# ── Reply ceiling ────────────────────────────────────────────────────────────

class TestMaxOutputTokens:
    def test_absent_by_default(self, neutral):
        assert "max_output_tokens" not in vol._build_session_update("P")["session"]

    def test_applied_when_configured(self, neutral, monkeypatch):
        monkeypatch.setattr(vol, "OPENAI_MAX_OUTPUT_TOKENS", 300)
        assert vol._build_session_update("P")["session"]["max_output_tokens"] == 300

    def test_env_parse_rejects_absurd_values(self):
        # A cap this low would truncate ordinary replies mid-sentence.
        assert _parse_bounded_int("5", 64, 4096, None, "OPENAI_MAX_OUTPUT_TOKENS") is None
        assert _parse_bounded_int("999999", 64, 4096, None, "OPENAI_MAX_OUTPUT_TOKENS") is None


# ── Dialogue discipline: tenant gate + instruction content ───────────────────

class TestDialogueStyleGate:
    def test_empty_allowlist_is_off_for_everyone(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_DIALOGUE_STYLE_CLIENT_IDS", set())
        assert vs.dialogue_style_enabled("any-client") is False
        assert vs.dialogue_style_enabled("") is False

    def test_only_allowlisted_client_is_enabled(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_DIALOGUE_STYLE_CLIENT_IDS", {"roi-id"})
        assert vs.dialogue_style_enabled("roi-id") is True
        assert vs.dialogue_style_enabled("eliran-id") is False

    def test_blank_client_id_never_matches(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_DIALOGUE_STYLE_CLIENT_IDS", {""})
        assert vs.dialogue_style_enabled("") is False


class TestDialogueStyleInstruction:
    def test_is_a_suffix_that_composes(self):
        # Appended to an existing prompt — must not open with content that would
        # collide with the tenant's own first line.
        assert vol._DIALOGUE_STYLE_INSTRUCTION.startswith("\n\n")

    def test_covers_each_observed_failure(self):
        text = vol._DIALOGUE_STYLE_INSTRUCTION
        assert "משפט אחד" in text            # monologue replies
        assert "שאלה אחת" in text            # bundled questions
        assert "אל תחזרי" in text            # repeated closing script
        assert "מתקן" in text                # caller correction wins
        assert "סיום השיחה" in text          # no racing to close
        assert "עני עליה ישירות" in text     # answer a question, don't acknowledge it

    def test_scopes_the_acknowledgment_softener(self):
        """Roi's own prompt lists "בסדר גמור" as an opener to use *before a
        question she asks*. The model was applying it before ANSWERS too, which
        is what made replies feel disconnected from the question. The rule must
        name the misfiring openers and confine them to her own questions."""
        text = vol._DIALOGUE_STYLE_INSTRUCTION
        assert "בסדר גמור" in text
        assert "רק לפני שאלה שאת שואלת" in text
        assert "לא לפני תשובה" in text

    def test_says_nothing_about_tone_or_business_logic(self):
        """It constrains turn SHAPE only — tone, wording and insurance logic
        stay owned by the tenant prompt in Supabase."""
        text = vol._DIALOGUE_STYLE_INSTRUCTION
        for foreign in ("ביטוח", "רועי", "מאיה", "חמה", "ידידותית"):
            assert foreign not in text


# ── Post-call extraction: the caller's correction wins ───────────────────────

class TestExtractionCorrectionRules:
    def test_prompt_states_later_lines_win(self):
        assert "סדר הזמן" in vs._EXTRACT_PROMPT
        assert "הגרסה המאוחרת" in vs._EXTRACT_PROMPT

    def test_prompt_forbids_a_denied_topic(self):
        assert "שלל נושא" in vs._EXTRACT_PROMPT
        assert "אסור להחזיר אותו נושא" in vs._EXTRACT_PROMPT

    def test_existing_name_rules_are_untouched(self):
        # M7 adds rules; it must not weaken the anti-hallucination guarantees.
        assert "אל תנחש. אל תמציא." in vs._EXTRACT_PROMPT
        assert "phone_number תמיד null" in vs._EXTRACT_PROMPT

    def test_transcript_placeholder_still_present(self):
        assert "{transcript}" in vs._EXTRACT_PROMPT

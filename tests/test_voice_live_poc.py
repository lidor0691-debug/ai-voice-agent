"""
GPT-Live 1 POC — pure helpers and the isolation gates.

The two properties that matter most are asserted first: with nothing set, the
POC is unreachable (flag off AND empty number allowlist), and Roi's production
number is refused even when the flag is on unless it is explicitly listed.
"""
from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pytest

import app.routes.voice_live_poc as poc

ROI_NUMBER = "+972533470757"


# ── Isolation gates ──────────────────────────────────────────────────────────

class TestGates:
    def test_default_is_fully_closed(self, monkeypatch):
        monkeypatch.setattr(poc, "LIVE_POC_ENABLED", False)
        monkeypatch.setattr(poc, "LIVE_POC_ALLOWED_TO_NUMBERS", set())
        assert poc.live_poc_enabled() is False
        assert poc.live_poc_number_allowed(ROI_NUMBER) is False

    def test_flag_alone_never_captures_a_number(self, monkeypatch):
        """Turning the flag on must not make ANY number answerable."""
        monkeypatch.setattr(poc, "LIVE_POC_ENABLED", True)
        monkeypatch.setattr(poc, "LIVE_POC_ALLOWED_TO_NUMBERS", set())
        assert poc.live_poc_number_allowed(ROI_NUMBER) is False
        assert poc.live_poc_number_allowed("+972500000000") is False

    def test_only_allowlisted_number_is_served(self, monkeypatch):
        monkeypatch.setattr(poc, "LIVE_POC_ALLOWED_TO_NUMBERS", {"+972535666375"})
        assert poc.live_poc_number_allowed("+972535666375") is True
        assert poc.live_poc_number_allowed(ROI_NUMBER) is False

    def test_number_normalisation_applies(self, monkeypatch):
        monkeypatch.setattr(poc, "LIVE_POC_ALLOWED_TO_NUMBERS", {"+972535666375"})
        assert poc.live_poc_number_allowed(" +972535666375 ") is True
        assert poc.live_poc_number_allowed("") is False

    @pytest.mark.parametrize("raw,expected", [
        (None, False), ("", False), ("false", False), ("0", False),
        ("true", True), ("1", True), ("YES", True), (" on ", True),
    ])
    def test_truthy_parser(self, raw, expected):
        assert poc._truthy(raw) is expected

    def test_csv_parser_strips_and_drops_empties(self):
        assert poc._csv_set(" +1 , ,+2,, ") == {"+1", "+2"}


# ── session.start payload ────────────────────────────────────────────────────

class TestSessionStart:
    def test_shape_matches_the_probed_contract(self):
        s = poc.build_session_start("VOICE", "BACKEND")
        assert s["type"] == "session.start"
        sess = s["session"]
        assert sess["model"] == "gpt-live-1"
        assert sess["instructions"] == "VOICE"
        # µ-law 8 kHz passthrough — the one format that needs no transcoding
        assert sess["audio"]["format"] == {"type": "audio/pcmu", "rate": 8000}
        assert sess["audio"]["output"]["voice"] == "marin"

    def test_no_realtime_fields_leak_in(self):
        """Strict config: any of these would be rejected as unknown_parameter
        and kill the session (verified by live probe)."""
        sess = poc.build_session_start("V", "B")["session"]
        for forbidden in ("turn_detection", "input_audio_transcription", "modalities",
                          "output_modalities", "speed", "temperature", "max_output_tokens",
                          "tools", "type"):
            assert forbidden not in sess
        assert "input" not in sess["audio"]     # Live has ONE format, not input/output

    def test_responses_delegation_carries_backend_prompt(self):
        sess = poc.build_session_start("V", "BACKEND RULES", delegation="responses",
                                       backend_model="gpt-5.6-luna", backend_reasoning="low")["session"]
        d = sess["delegation"]
        assert d["type"] == "responses"
        assert d["responses"]["model"] == "gpt-5.6-luna"
        assert d["responses"]["instructions"] == "BACKEND RULES"
        assert d["responses"]["reasoning"] == {"effort": "low"}

    def test_client_delegation_has_no_backend(self):
        sess = poc.build_session_start("V", "B", delegation="client")["session"]
        assert sess["delegation"] == {"type": "client"}

    def test_invalid_reasoning_degrades_to_low(self):
        sess = poc.build_session_start("V", "B", backend_reasoning="turbo")["session"]
        assert sess["delegation"]["responses"]["reasoning"] == {"effort": "low"}


# ── Prompts ──────────────────────────────────────────────────────────────────

class TestPrompts:
    def test_voice_prompt_is_short_and_hebrew_pinned(self):
        p = poc.build_voice_instructions("מהמשרד של רועי")
        assert len(p) < 1600                    # the point: short
        assert "מהמשרד של רועי" in p
        assert "רק בעברית" in p
        assert "לעולם אל תעברי לאנגלית" in p

    def test_voice_prompt_carries_turn_policies(self):
        p = poc.build_voice_instructions("מהמשרד")
        assert "עצרי מיד והקשיבי" in p            # interruption policy
        assert "קולות הקשבה" in p                 # backchannel policy
        assert "האצילי" in p                      # delegation policy
        assert "בסדר גמור" in p                   # no filler before answers
        assert "פעם אחת בלבד" in p                # close once

    def test_voice_prompt_contains_no_business_rules(self):
        """Business logic belongs on the backend; the voice prompt must not
        become the long tenant prompt again."""
        p = poc.build_voice_instructions("מהמשרד של רועי")
        for foreign in ("פוליסה", "משכנתא", "סיעודי", "מחיר"):
            assert foreign not in p

    def test_backend_prompt_wraps_tenant_rules(self):
        p = poc.build_backend_instructions("TENANT RULES", "מהמשרד של רועי", True)
        assert p.startswith("אתה ה-backend של מאיה")
        assert "TENANT RULES" in p
        assert "תיקון של הפונה תמיד גובר" in p
        assert "אל תמציא" in p

    def test_backend_prompt_can_exclude_tenant_rules(self):
        p = poc.build_backend_instructions("TENANT RULES", "מהמשרד", False)
        assert "TENANT RULES" not in p

    def test_greeting_prefers_tenant_first_message(self):
        assert poc.build_greeting_line("  שלום, הגעתם  ", "מהמשרד") == "שלום, הגעתם"
        assert poc.build_greeting_line("", "מהמשרד של רועי") == \
            "היי, מדברת מאיה מהמשרד של רועי. איך אפשר לעזור?"


# ── Playback clock + barge-in flush decision ─────────────────────────────────

class TestPlaybackClock:
    def test_tracks_unheard_audio(self):
        c = poc.PlaybackClock()
        c.on_sent(now=10.0, n_bytes=8000)        # 1s of µ-law
        assert c.is_playing(10.5)
        assert c.buffered_seconds(10.5) == pytest.approx(0.5)
        assert not c.is_playing(11.0)

    def test_bursts_queue_behind_each_other(self):
        c = poc.PlaybackClock()
        c.on_sent(10.0, 8000)
        c.on_sent(10.0, 8000)                    # second burst plays after the first
        assert c.play_until == pytest.approx(12.0)

    def test_flush_returns_dropped_seconds(self):
        c = poc.PlaybackClock()
        c.on_sent(10.0, 16000)
        assert c.flush(10.5) == pytest.approx(1.5)
        assert not c.is_playing(10.5)


class TestFlushDecision:
    def test_no_flush_when_nothing_is_playing(self):
        assert poc.should_flush_playback(now=5.0, caller_speech_at=4.0,
                                         last_output_delta_at=3.0, is_playing=False,
                                         grace_s=0.25) is False

    def test_no_flush_while_model_keeps_talking(self):
        """Backchannel / model chose not to yield: new audio arrived AFTER the
        caller started → leave Twilio's buffer alone."""
        assert poc.should_flush_playback(now=5.0, caller_speech_at=4.0,
                                         last_output_delta_at=4.5, is_playing=True,
                                         grace_s=0.25) is False

    def test_flush_after_grace_when_model_yielded(self):
        assert poc.should_flush_playback(now=4.3, caller_speech_at=4.0,
                                         last_output_delta_at=3.9, is_playing=True,
                                         grace_s=0.25) is True

    def test_not_before_grace(self):
        assert poc.should_flush_playback(now=4.1, caller_speech_at=4.0,
                                         last_output_delta_at=3.9, is_playing=True,
                                         grace_s=0.25) is False


# ── Closing decision ─────────────────────────────────────────────────────────

class TestClosingDecision:
    def test_requires_a_closing_phrase(self):
        assert poc.should_close_on_closing_phrase("תודה, נשמע טוב", 10.0, 0.0, 8.0, 2.5) is False

    def test_closes_when_caller_quiet_and_output_settled(self):
        assert poc.should_close_on_closing_phrase("תודה ולהתראות", now=10.0,
                                                  last_caller_speech_at=5.0,
                                                  last_output_delta_at=8.5,
                                                  caller_quiet_s=2.5) is True

    def test_never_hangs_up_while_caller_is_objecting(self):
        """The production incident: Maya said להתראות while the caller was
        mid-correction and the call dropped."""
        assert poc.should_close_on_closing_phrase("להתראות", now=10.0,
                                                  last_caller_speech_at=9.0,
                                                  last_output_delta_at=8.5,
                                                  caller_quiet_s=2.5) is False

    def test_waits_for_output_to_settle(self):
        assert poc.should_close_on_closing_phrase("להתראות", now=10.0,
                                                  last_caller_speech_at=5.0,
                                                  last_output_delta_at=9.8,
                                                  caller_quiet_s=2.5) is False


# ── Transcript accumulation ──────────────────────────────────────────────────

class TestTranscriptAccumulator:
    def test_merges_same_role_fragments_into_one_turn(self):
        t = poc.TranscriptAccumulator()
        t.assistant("היי, ")
        t.assistant("מדברת מאיה.")
        t.caller("אני ")
        t.caller("לידור")
        assert t.turns == [{"role": "מאיה", "text": "היי, מדברת מאיה."},
                           {"role": "לקוח", "text": "אני לידור"}]
        assert t.caller_lines == ["אני לידור"]
        assert t.assistant_lines == ["היי, מדברת מאיה."]

    def test_role_change_opens_a_new_turn(self):
        t = poc.TranscriptAccumulator()
        t.assistant("א")
        t.caller("ב")
        t.assistant("ג")
        assert [x["role"] for x in t.turns] == ["מאיה", "לקוח", "מאיה"]

    def test_empty_deltas_are_ignored(self):
        t = poc.TranscriptAccumulator()
        t.caller("")
        t.assistant(None)
        assert t.turns == []

    def test_assistant_tail(self):
        t = poc.TranscriptAccumulator()
        t.assistant("x" * 100 + " להתראות")
        assert t.assistant_tail(20).endswith("להתראות")

    def test_language_check_counts_english_only_turns(self):
        t = poc.TranscriptAccumulator()
        t.assistant("הלו?")
        t.caller("פעם")
        t.assistant("Hi there, I'm here. How can I help?")     # the incident line
        t.caller("כן")
        t.assistant("בסדר, 052-1234567")                       # digits + Hebrew OK
        assert t.assistant_non_hebrew_turns() == 1

    def test_turns_feed_transcript_html_shape(self):
        """Same {"role","text"} shape the production RTL renderer consumes."""
        from app.routes.voice_openai_live import _transcript_html
        t = poc.TranscriptAccumulator()
        t.assistant("היי")
        t.caller("שלום")
        html = _transcript_html(t.turns)
        assert "היי" in html and "שלום" in html

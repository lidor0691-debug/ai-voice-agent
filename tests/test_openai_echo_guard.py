"""
Echo guard (self-speech rejection) — transcript-level, tenant-scoped, SHADOW-first.

Incident (Roi live call, Aug 10 2026): Maya's Stage-2 greeting
"היי, מדברת מאיה מהמשרד של רועי. איך אפשר לעזור?" echoed off the caller device,
was transcribed by inbound STT as "היי מדברת מיה", passed the M4 gate as a real
caller turn (13 chars, 2.4s), cut the greeting, and polluted the email name
field ("מיה").

Design: compare caller transcripts against Maya's last 1–2 played utterances —
fuzzy ORDERED token matching (catches STT garbles like מאיה→מיה) gated by the
physical playback window (echo requires Maya's audio playing at the device).
Modes (voice_shared.echo_guard_mode, allowlist + global mode):
  off      — no analysis work at all (default; empty allowlist = off for all)
  shadow   — echo_would_reject diagnostic ONLY; zero behavior change
  enforce  — echo_rejected: phantom never becomes a turn (implemented, NOT enabled)
M4, onset-barge, recovery/circuit-breaker, VAD, STT: untouched.
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
from app.routes.voice_openai_live import (
    TurnController, CallState, Action,
    _echo_check, _echo_normalize, _echo_match_score, _echo_token_sim,
)

# The exact production incident texts.
GREETING = "היי, מדברת מאיה מהמשרד של רועי. איך אפשר לעזור?"
ECHO_STT = "היי מדברת מיה"


def _playing(text=GREETING, start=10.0, end=None):
    return [{"text": text, "play_start": start, "play_end": end}]


# ── tenant-scoped mode resolution ────────────────────────────────────────────

class TestModeResolution:
    ROI = "c3a8c2a0-8841-4c9b-9a59-3f9795c4e7de"
    ELIRAN = "ec87b6ae-b28c-4bef-8562-fd4f530d41d5"

    def test_default_is_off_for_everyone(self):
        # shipped defaults: empty allowlist + mode 'off'
        assert vs.echo_guard_mode(self.ROI) == "off"
        assert vs.echo_guard_mode(self.ELIRAN) == "off"
        assert vs.echo_guard_mode("") == "off"
        assert vs.echo_guard_mode(None) == "off"

    def test_shadow_only_for_allowlisted(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_ECHO_GUARD_CLIENT_IDS", {self.ROI})
        monkeypatch.setattr(vs, "OPENAI_ECHO_GUARD_MODE", "shadow")
        assert vs.echo_guard_mode(self.ROI) == "shadow"
        assert vs.echo_guard_mode(self.ELIRAN) == "off"     # Eliran unaffected

    def test_enforce_only_for_allowlisted(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_ECHO_GUARD_CLIENT_IDS", {self.ROI})
        monkeypatch.setattr(vs, "OPENAI_ECHO_GUARD_MODE", "enforce")
        assert vs.echo_guard_mode(self.ROI) == "enforce"
        assert vs.echo_guard_mode(self.ELIRAN) == "off"

    def test_invalid_mode_resolves_off(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_ECHO_GUARD_CLIENT_IDS", {self.ROI})
        monkeypatch.setattr(vs, "OPENAI_ECHO_GUARD_MODE", "on")   # not a valid mode
        assert vs.echo_guard_mode(self.ROI) == "off"

    def test_empty_allowlist_off_even_with_mode_set(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_ECHO_GUARD_CLIENT_IDS", set())
        monkeypatch.setattr(vs, "OPENAI_ECHO_GUARD_MODE", "shadow")
        assert vs.echo_guard_mode(self.ROI) == "off"


# ── normalization + fuzzy matching primitives ────────────────────────────────

class TestMatchingPrimitives:
    def test_normalize_strips_punctuation_conservatively(self):
        assert _echo_normalize("היי, מדברת מאיה!") == ["היי", "מדברת", "מאיה"]
        assert _echo_normalize("  הלו?  ") == ["הלו"]
        assert _echo_normalize("") == []

    def test_stt_garble_fuzzy_token(self):
        # the exact production garble: מאיה transcribed as מיה
        assert _echo_token_sim("מיה", "מאיה") >= 0.75

    def test_ordered_containment_of_truncated_echo(self):
        containment, sim = _echo_match_score(ECHO_STT, GREETING)
        assert containment == 1.0
        assert sim > 0.9

    def test_bag_of_words_without_order_scores_low(self):
        # same words, reversed order — ordered matching must not credit them all
        containment, _ = _echo_match_score("לעזור אפשר איך היי", GREETING)
        assert containment < 0.70

    def test_genuine_sentence_with_topic_overlap_scores_low(self):
        # caller genuinely says "אני רוצה ביטוח רכב" after Maya mentioned רכב —
        # most caller tokens are the caller's own words
        containment, _ = _echo_match_score("אני רוצה ביטוח רכב", "זה לגבי ביטוח רכב או דירה?")
        assert containment < 0.70


# ── the required scenario matrix ─────────────────────────────────────────────

class TestEchoCheck:
    def test_1_production_regression_would_reject(self):
        # assistant line playing; echo STT arrives 1.5s into playback
        hit = _echo_check(ECHO_STT, _playing(start=10.0, end=None), onset_ts=11.5)
        assert hit is not None
        assert hit["containment"] >= 0.70
        assert hit["similarity"] > 0.9
        assert hit["onset_offset_s"] == pytest.approx(1.5)

    def test_2_genuine_maya_question_not_matched(self):
        # caller genuinely asks "מאיה?" — 1 token, below the floor → NEVER echo
        assert _echo_check("מאיה?", _playing(start=10.0, end=13.0), onset_ts=11.0) is None

    def test_3_genuine_short_topic_repetition_not_matched(self):
        # caller repeats "ביטוח רכב" right after Maya says it — 2 tokens → NEVER
        recent = _playing(text="זה לגבי ביטוח רכב או דירה?", start=10.0, end=13.0)
        assert _echo_check("ביטוח רכב", recent, onset_ts=12.0) is None

    def test_4_similar_text_outside_window_not_matched(self):
        # identical echo text but speech onset long after playback ended
        assert _echo_check(ECHO_STT, _playing(start=10.0, end=11.0), onset_ts=20.0) is None
        # and before playback started
        assert _echo_check(ECHO_STT, _playing(start=10.0, end=13.0), onset_ts=9.0) is None

    def test_window_trails_playback_end_by_one_second(self):
        assert _echo_check(ECHO_STT, _playing(start=10.0, end=13.0), onset_ts=13.9) is not None
        assert _echo_check(ECHO_STT, _playing(start=10.0, end=13.0), onset_ts=14.2) is None

    def test_no_onset_timestamp_never_matches(self):
        assert _echo_check(ECHO_STT, _playing(), onset_ts=None) is None

    def test_unrelated_caller_sentence_not_matched(self):
        assert _echo_check("אני צריך לדבר עם רועי על תביעה",
                           _playing(start=10.0, end=None), onset_ts=11.0) is None


# ── ENFORCE path (implemented, config-gated, not enabled) ────────────────────

class TestEnforceControllerPath:
    def _to_barged(self):
        c = TurnController(onset_barge=True)
        c.state = CallState.WAITING_FOR_CALLER
        c.on_speech_started(0.0)
        c.on_speech_stopped(1.0, item_id="seed")
        c.on_input_transcription("אני רוצה ביטוח רכב", dur=1.0, item_id="seed")
        c.on_response_created()
        c.on_output_delta()
        assert c.state == CallState.RESPONDING_PLAYING
        c.on_speech_started(10.0)
        c.on_onset_confirmed()
        assert c.state == CallState.BARGED_LISTENING
        return c

    def test_echo_in_barged_listening_reuses_false_barge_recovery(self):
        c = self._to_barged()
        c.resp_audio_ms = 200                      # barely started → re-issue once
        acts = c.on_echo_rejected()
        assert c.last_decision == "echo_rejected"
        assert acts == [(Action.RESPONSE_CREATE, None)]
        assert c._barge_recover_count == 1         # counts against the same cap

    def test_echo_in_barged_listening_yields_when_mostly_played(self):
        c = self._to_barged()
        c.resp_audio_ms = 3000
        acts = c.on_echo_rejected()
        assert acts == []
        assert c.state in (CallState.WAITING_FOR_CALLER, CallState.ACTIVE_CONVERSATION)

    def test_echo_outside_barge_is_a_silent_consume(self):
        c = TurnController()
        c.state = CallState.CALLER_SPEAKING
        c.valid_turns = 1
        c.on_speech_stopped(5.0, item_id="x")
        acts = c.on_echo_rejected()
        assert acts == []
        assert c.last_decision == "echo_rejected"
        assert c.state == CallState.ACTIVE_CONVERSATION
        assert c._unconsumed_segment is None       # segment consumed

    def test_circuit_breaker_shared_with_false_barge(self):
        c = self._to_barged()
        c.resp_audio_ms = 3000
        for _ in range(vol.OPENAI_ONSET_FALSE_BARGE_CIRCUIT):
            c.state = CallState.BARGED_LISTENING
            c.on_echo_rejected()
        assert c.onset_disabled_for_call           # same per-call breaker applies


# ── shadow / off wiring guarantees (source pins) ─────────────────────────────

class TestWiringSource:
    def _src(self):
        return pathlib.Path(vol.__file__).read_text(encoding="utf-8")

    def test_mode_resolved_per_call_from_allowlist(self):
        src = self._src()
        assert '_echo_mode = _echo_guard_mode(client_id or "")' in src
        # no analysis structures for non-enabled calls
        assert '_echo_state = {"recent": [], "cur_start": None} if _echo_mode != "off" else None' in src

    def test_shadow_branch_is_diag_only(self):
        src = self._src()
        shadow = src.split('if _echo_hit is not None and _echo_mode == "shadow":')[1]
        shadow_block = shadow.split('if _echo_hit is not None and _echo_mode == "enforce":')[0]
        assert '_diag("echo_would_reject"' in shadow_block
        # shadow must not touch state or skip the normal path
        for forbidden in ("on_echo_rejected", "continue", "break", "_release_segment"):
            assert forbidden not in shadow_block
        # the normal controller call still runs after the shadow block
        after = src.split('if _echo_hit is not None and _echo_mode == "enforce":')[1]
        assert "_ctrl.on_input_transcription(_text" in after

    def test_shadow_diag_carries_required_fields(self):
        src = self._src()
        i = src.index('_diag("echo_would_reject"')
        block = src[i:i + 450]
        for field in ("caller_text", "matched_assistant", "similarity",
                      "containment", "onset_offset_s", "state", "mode"):
            assert field in block, f"echo_would_reject missing field: {field}"

    def test_enforce_branch_consumes_phantom_turn(self):
        src = self._src()
        enforce = src.split('if _echo_hit is not None and _echo_mode == "enforce":')[1]
        enforce_block = enforce.split("_ctrl.on_input_transcription(_text")[0]
        assert '_diag("echo_rejected"' in enforce_block
        assert "on_echo_rejected()" in enforce_block
        assert "continue" in enforce_block          # never reaches the normal path

    def test_playback_window_tracked_from_real_events(self):
        src = self._src()
        assert '_echo_state["cur_start"] = _now' in src            # first audio
        assert '"play_start": _echo_state["cur_start"]' in src     # transcript.done
        # def + exactly two call sites: playback-mark return + barge clear
        assert src.count("_echo_close_playback()") == 3

    def test_off_mode_zero_work(self):
        # with _echo_state None, every echo hook is behind a None-check
        src = self._src()
        assert "if _echo_state is not None and _text:" in src
        assert "if _echo_state is not None:" in src

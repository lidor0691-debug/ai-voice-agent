"""
Onset-based interruption (barge-in) — Phase: barge-in.

Moves the yield-the-floor decision from transcription-gated (~2.9s measured) to
speech-onset + a ~150ms energy-persistence guard, scoped to RESPONDING_PLAYING.
GREETING_PLAYING keeps the M4 path untouched; interrupt_response stays FALSE;
with OPENAI_ONSET_BARGE_ENABLED off the controller is a complete no-op.

These are deterministic controller/helper tests. The async energy-guard task,
Twilio flush, and true stop latency are integration/live concerns (validated
with the new diags: onset_to_vad_ms, vad_to_clear_ms, onset_to_clear_ms).
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
    TurnController, CallState, Action, InboundSpeechTracker, _ulaw_frame_rms,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _acts(pairs):
    return [a for a, _ in pairs]


def _accept_a_turn(c, text="אני רוצה ביטוח רכב", dur=1.0):
    c.state = CallState.WAITING_FOR_CALLER
    c.on_speech_started(0.0)
    c.on_speech_stopped(dur, item_id="seed")
    return c.on_input_transcription(text, dur=dur, item_id="seed")


def _to_responding_playing(c):
    """Drive to a real reply playing (valid_turns≥1 → RESPONDING_PLAYING)."""
    _accept_a_turn(c)
    c.on_response_created()
    c.on_output_delta()
    assert c.state == CallState.RESPONDING_PLAYING
    return c


def _barge(c, t=10.0):
    """Onset while a reply plays → confirmed guard → BARGED_LISTENING."""
    c.on_speech_started(t)
    return c.on_onset_confirmed()


# ── tenant scoping: client allowlist (not a global boolean) ──────────────────

class TestTenantGating:
    ROI = "c3a8c2a0-8841-4c9b-9a59-3f9795c4e7de"
    ELIRAN = "ec87b6ae-b28c-4bef-8562-fd4f530d41d5"

    def test_1_allowlisted_client_enabled(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_ONSET_BARGE_CLIENT_IDS", {self.ROI})
        assert vs.onset_barge_enabled(self.ROI) is True
        # …and an enabled call arms the onset guard
        c = TurnController(onset_barge=vs.onset_barge_enabled(self.ROI))
        _to_responding_playing(c)
        assert _acts(c.on_speech_started(9.0)) == [Action.ARM_ONSET_GUARD]

    def test_2_non_allowlisted_client_legacy_only(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_ONSET_BARGE_CLIENT_IDS", {self.ROI})
        assert vs.onset_barge_enabled(self.ELIRAN) is False        # Eliran unaffected
        # …and a non-enabled call never arms; legacy transcription path is sole
        c = TurnController(onset_barge=vs.onset_barge_enabled(self.ELIRAN))
        _to_responding_playing(c)
        assert c.on_speech_started(9.0) == []
        c.on_speech_stopped(10.0, item_id="k")
        acts = c.on_input_transcription("רגע רגע תקשיבי בבקשה", dur=1.0, item_id="k")
        assert (Action.CANCEL_AND_CLEAR, {"cancel": True}) in acts   # legacy still works

    def test_3_empty_allowlist_off_for_everyone(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_ONSET_BARGE_CLIENT_IDS", set())
        assert vs.onset_barge_enabled(self.ROI) is False
        assert vs.onset_barge_enabled(self.ELIRAN) is False
        assert vs.onset_barge_enabled("") is False
        assert vs.onset_barge_enabled(None) is False

    def test_4_no_onset_work_for_disabled_call(self):
        # a disabled call: controller never arms, guard/energy paths are inert
        c = TurnController(onset_barge=False)
        _to_responding_playing(c)
        assert c.on_speech_started(5.0) == []          # no ARM_ONSET_GUARD
        assert c.on_onset_confirmed() == []            # guarded no-op
        assert c.state == CallState.RESPONDING_PLAYING
        assert not c._onset_active()


# ── µ-law RMS + energy tracker ────────────────────────────────────────────────

class TestUlawRms:
    def test_silence_is_zero(self):
        import base64
        assert _ulaw_frame_rms(base64.b64encode(bytes([0xFF] * 160)).decode()) == 0.0

    def test_full_scale_is_large(self):
        import base64
        assert _ulaw_frame_rms(base64.b64encode(bytes([0x00] * 160)).decode()) > 30000

    def test_empty_or_bad_is_zero(self):
        assert _ulaw_frame_rms("") == 0.0
        assert _ulaw_frame_rms("!!!not-base64!!!") == 0.0


class TestInboundSpeechTracker:
    def test_quiet_frames_never_onset(self):
        t = InboundSpeechTracker(ratio=3.0, abs_min=500, min_frames=6)
        for i in range(20):
            t.push(i * 0.02, 100.0)
        assert t.onset_ts is None

    def test_short_burst_below_min_frames_no_onset(self):
        # 5-frame (~100ms) burst < min_frames(6) → no sustained onset
        t = InboundSpeechTracker(ratio=3.0, abs_min=500, min_frames=6)
        for i in range(5):
            t.push(1.0 + i * 0.02, 6000.0)
        assert t.onset_ts is None
        assert t.sustained_frames(1.0, 1.15) == 5    # counted, but < min_frames

    def test_sustained_speech_sets_onset_and_counts(self):
        t = InboundSpeechTracker(ratio=3.0, abs_min=500, min_frames=6)
        for i in range(8):                            # ~160ms sustained
            t.push(1.0 + i * 0.02, 6000.0)
        assert t.onset_ts is not None
        assert t.onset_ts == pytest.approx(1.0, abs=1e-6)   # first frame of the run
        assert t.sustained_frames(1.0, 1.15) >= 6

    def test_onset_clears_after_silence(self):
        t = InboundSpeechTracker(ratio=3.0, abs_min=500, min_frames=6)
        for i in range(8):
            t.push(1.0 + i * 0.02, 6000.0)
        assert t.onset_ts is not None
        for i in range(6):                            # ~120ms silence (>5 frames)
            t.push(2.0 + i * 0.02, 100.0)
        assert t.onset_ts is None


# ── flag OFF = complete no-op (regression pin) ───────────────────────────────

class TestFlagOff:
    def test_no_arm_and_guarded_noop(self):
        c = TurnController(onset_barge=False)
        _to_responding_playing(c)
        assert c.on_speech_started(5.0) == []          # no ARM
        assert c.on_onset_confirmed() == []            # guarded no-op
        assert c.state == CallState.RESPONDING_PLAYING

    def test_legacy_transcription_barge_still_fires(self):
        # the OLD ≥0.6s transcription-gated barge-in is unchanged when flag off
        c = TurnController(onset_barge=False)
        _to_responding_playing(c)
        c.on_speech_started(2.0)
        c.on_speech_stopped(3.0, item_id="k")
        acts = c.on_input_transcription("רגע רגע בבקשה תקשיבי", dur=1.0, item_id="k")
        assert (Action.CANCEL_AND_CLEAR, {"cancel": True}) in acts

    def test_legacy_short_turn_does_not_barge(self):
        # preserved OLD limitation (<0.6s never cut playback) — proves parity
        c = TurnController(onset_barge=False)
        _to_responding_playing(c)
        c.on_speech_started(2.0)
        c.on_speech_stopped(2.3, item_id="k")
        acts = c.on_input_transcription("לא", dur=0.3, item_id="k")
        assert Action.CANCEL_AND_CLEAR not in _acts(acts)


# ── onset arm / confirm / abort ──────────────────────────────────────────────

class TestOnsetGuard:
    def test_arm_only_while_reply_playing(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        acts = c.on_speech_started(10.0)
        assert acts == [(Action.ARM_ONSET_GUARD, 10.0)]
        assert c.state == CallState.RESPONDING_PLAYING   # arming doesn't change state

    def test_confirm_cancels_and_enters_barged_listening(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        acts = _barge(c)
        assert acts == [(Action.CANCEL_AND_CLEAR, {"cancel": True})]
        assert c.state == CallState.BARGED_LISTENING
        assert c.pending_marks == set()

    def test_abort_leaves_maya_playing(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        c.on_speech_started(10.0)
        assert c.on_onset_aborted() == []
        assert c.state == CallState.RESPONDING_PLAYING

    def test_stale_confirm_ignored(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        _barge(c)                              # now BARGED_LISTENING
        assert c.on_onset_confirmed() == []    # second confirm is a no-op


# ── real interruption content after yielding ─────────────────────────────────

class TestInterruptionContent:
    @pytest.mark.parametrize("word", ["רגע", "לא", "כן אבל רגע"])
    def test_short_interruption_answered(self, word):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        turns_before = c.valid_turns
        _barge(c)
        acts = c.on_input_transcription(word, dur=0.5)
        assert acts == [(Action.RESPONSE_CREATE, None)]
        assert c.last_decision == "accepted"
        assert c.valid_turns == turns_before + 1
        assert c.state == CallState.ASSISTANT_RESPONDING

    def test_rapid_lo_lo_lo(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        _barge(c)
        acts = c.on_input_transcription("לא לא לא", dur=0.8)
        assert acts == [(Action.RESPONSE_CREATE, None)]
        assert c.last_decision == "accepted"


# ── false-barge recovery (bounded, played-progress aware) ────────────────────

class TestFalseBargeRecovery:
    def test_reissue_when_barely_started(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        c.resp_audio_ms = 200                  # barely played
        _barge(c)
        acts = c.on_input_transcription("", dur=0.3)   # empty → false barge
        assert c.last_decision == "false_barge"
        assert acts == [(Action.RESPONSE_CREATE, None)]   # re-issue once
        assert c._barge_recover_count == 1
        assert c.state == CallState.ASSISTANT_RESPONDING

    def test_yield_when_mostly_played(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        c.resp_audio_ms = 3000                 # near-complete answer
        _barge(c)
        acts = c.on_input_transcription("", dur=0.3)
        assert c.last_decision == "false_barge"
        assert acts == []                      # yield, do NOT replay
        assert c.state in (CallState.WAITING_FOR_CALLER, CallState.ACTIVE_CONVERSATION)
        assert c._barge_recover_count == 0

    def test_never_reissue_more_than_once(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        c.resp_audio_ms = 200
        _barge(c)
        c.on_input_transcription("", dur=0.3)             # reissue #1
        assert c._barge_recover_count == 1
        # the re-issued reply plays, then is falsely barged again
        c.on_response_created(); c.on_output_delta()      # resp_audio_ms reset → 0
        c.resp_audio_ms = 100
        _barge(c)
        acts = c.on_input_transcription("", dur=0.3)      # cap reached → yield
        assert acts == []
        assert c.state in (CallState.WAITING_FOR_CALLER, CallState.ACTIVE_CONVERSATION)

    def test_real_content_resets_reissue_budget(self):
        c = TurnController(onset_barge=True)
        _to_responding_playing(c)
        c.resp_audio_ms = 200
        _barge(c); c.on_input_transcription("", dur=0.3)  # reissue, count=1
        # caller now says something real
        c.on_response_created(); c.on_output_delta()
        _barge(c)
        c.on_input_transcription("אני רוצה לבדוק פוליסה", dur=1.0)
        assert c._barge_recover_count == 0


# ── circuit breaker ──────────────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_opens_after_n_false_barges_and_disables_onset(self):
        c = TurnController(onset_barge=True)
        c.valid_turns = 1
        c.resp_audio_ms = 3000                 # force yield each time (no reissue)
        for _ in range(2):
            c.state = CallState.BARGED_LISTENING
            c._recover_after_false_barge()
        assert not c.onset_disabled_for_call and c._onset_active()
        c.state = CallState.BARGED_LISTENING
        c._recover_after_false_barge()         # 3rd → circuit opens
        assert c.onset_disabled_for_call
        assert not c._onset_active()
        # onset no longer arms; legacy path resumes
        c.state = CallState.RESPONDING_PLAYING
        assert c.on_speech_started(9.0) == []


# ── greeting (M4) is untouched ───────────────────────────────────────────────

class TestGreetingUntouched:
    def test_no_onset_arm_during_greeting(self):
        c = TurnController(two_stage=True, onset_barge=True, office="מהמשרד של רועי")
        c.on_session_updated(); c.on_response_created(); c.on_output_delta()
        assert c.state == CallState.GREETING_PLAYING
        assert c.on_speech_started(1.0) == []           # NOT armed during greeting

    def test_m4_held_fragment_behavior_preserved(self):
        c = TurnController(two_stage=True, onset_barge=True, office="מהמשרד של רועי")
        c.on_session_updated(); c.on_response_created(); c.on_output_delta()
        c.on_speech_started(1.0)
        c.on_speech_stopped(1.3, item_id="g")
        c.on_input_transcription("כן", dur=0.3, item_id="g")   # weak → held
        assert c.last_decision == "held_greeting"


# ── wiring/diag source pins (latency instrumentation refinement) ─────────────

class TestWiringSource:
    def _src(self):
        return pathlib.Path(vol.__file__).read_text(encoding="utf-8")

    def test_tenant_scoped_construction(self):
        src = self._src()
        # gate resolved per-call from the client allowlist, then threaded through
        assert '_onset_barge = _onset_barge_enabled(client_id or "")' in src
        assert "onset_barge=_onset_barge)" in src
        assert "InboundSpeechTracker() if _onset_barge else None" in src
        # resp_audio_ms tracking uses the resolved per-call flag, not a global env
        assert "if _onset_barge:" in src
        # the old process-global boolean must be gone entirely
        assert "OPENAI_ONSET_BARGE_ENABLED" not in src

    def test_three_latency_components_instrumented(self):
        src = self._src()
        # refinement 1: onset-detection, guard, and cancel/clear are separable
        assert "onset_to_vad_ms" in src        # caller-onset → OpenAI speech_started
        assert "vad_to_clear_ms" in src        # speech_started → clear (≤250ms target)
        assert "onset_to_clear_ms" in src      # caller-onset → clear (end-to-end)

    def test_energy_tap_and_guard_task_present(self):
        src = self._src()
        assert "_energy.push(time.monotonic(), _ulaw_frame_rms(payload))" in src
        assert "_onset_guard_runner" in src
        assert "on_onset_confirmed()" in src and "on_onset_aborted()" in src
        assert "_cancel_onset_guard()" in src  # cleaned up in finally

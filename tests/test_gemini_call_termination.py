"""
Focused tests for the Gemini call-termination logic in app/routes/voice_gemini.py:
  - _contains_closing_phrase   (broadened natural closings)
  - _is_caller_activity        (only real caller speech resets the idle timer)
  - _should_idle_hangup        (idle safety-timeout decision)
  - _run_idle_watchdog         (fires once, cancellation-safe, no orphan)

Required cases:
  1. closing phrase triggers hangup after response completion
  2. raw silent media does NOT reset the timeout
  3. real caller speech resets the timeout
  4. no hangup during an active response (or before the first Maya turn)
  5. cleanup/finalization (on_hangup) runs exactly once
"""
from __future__ import annotations

import os
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

import asyncio
import pytest

import app.routes.voice_gemini as vg


# ── 1. Closing-phrase detection (the hangup trigger) ─────────────────────────

@pytest.mark.parametrize("phrase", ["להתראות", "המשך יום", "יום טוב", "ביי", "תודה ויום טוב"])
def test_closing_phrase_each_broadened_phrase_triggers(phrase):
    assert vg._contains_closing_phrase(phrase) is True


def test_closing_phrase_in_full_sentence_and_roi_closings():
    assert vg._contains_closing_phrase("תודה רבה, להתראות!") is True
    assert vg._contains_closing_phrase("שיהיה לך המשך יום נעים") is True   # contains "המשך יום"
    assert vg._contains_closing_phrase("אז נתראה, ביי ביי") is True


def test_closing_phrase_not_in_midconversation():
    assert vg._contains_closing_phrase("אני רוצה לבדוק ביטוח רכב") is False
    assert vg._contains_closing_phrase("") is False
    assert vg._contains_closing_phrase(None) is False


# ── 2 & 3. Idle-timer reset only on real caller speech, not media/audio ──────

def test_real_caller_speech_resets_timer():
    assert vg._is_caller_activity({"inputTranscription": {"text": "היי, שם ומספר"}}) is True
    assert vg._is_caller_activity({"interrupted": True}) is True


def test_silent_media_and_model_output_do_not_reset_timer():
    # Model audio only (this is what streams during Maya speaking / silence gaps)
    assert vg._is_caller_activity({"modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm", "data": "AAA"}}]}}) is False
    # Maya's own transcription is NOT caller activity
    assert vg._is_caller_activity({"outputTranscription": {"text": "מאיה מדברת"}}) is False
    # Turn boundary is not caller activity
    assert vg._is_caller_activity({"turnComplete": True}) is False
    # Empty / whitespace transcription does not count
    assert vg._is_caller_activity({"inputTranscription": {"text": "   "}}) is False
    assert vg._is_caller_activity({}) is False
    # NOTE: raw Twilio media frames are handled in the Twilio loop and never
    # reach _is_caller_activity, so they can never reset the idle timer.


# ── 4. Idle-hangup decision ──────────────────────────────────────────────────

def test_no_hangup_before_first_maya_turn():
    # 999s idle, but no turn completed yet → never hang up
    assert vg._should_idle_hangup(now=1000.0, last_activity=1.0,
                                  turn_completed_once=False, gemini_speaking=False,
                                  idle_seconds=25.0) is False


def test_no_hangup_during_active_response():
    assert vg._should_idle_hangup(now=1000.0, last_activity=1.0,
                                  turn_completed_once=True, gemini_speaking=True,
                                  idle_seconds=25.0) is False


def test_no_hangup_within_idle_window():
    assert vg._should_idle_hangup(now=110.0, last_activity=100.0,
                                  turn_completed_once=True, gemini_speaking=False,
                                  idle_seconds=25.0) is False


def test_hangup_after_idle_window_elapsed():
    assert vg._should_idle_hangup(now=126.0, last_activity=100.0,
                                  turn_completed_once=True, gemini_speaking=False,
                                  idle_seconds=25.0) is True


# ── 5. Watchdog fires once and is cancellation-safe (no orphan) ──────────────

@pytest.mark.asyncio
async def test_watchdog_calls_on_hangup_exactly_once_then_stops():
    calls = {"n": 0}
    ticks = {"n": 0}

    def should_hangup():
        ticks["n"] += 1
        return ticks["n"] >= 3          # fire on the 3rd poll

    async def on_hangup():
        calls["n"] += 1

    # returns on its own after firing once
    await asyncio.wait_for(
        vg._run_idle_watchdog(should_hangup, on_hangup, poll_seconds=0.01),
        timeout=2.0,
    )
    assert calls["n"] == 1              # exactly once — finalization not double-run


@pytest.mark.asyncio
async def test_watchdog_is_cancellable_without_orphan_or_hangup():
    calls = {"n": 0}

    async def on_hangup():
        calls["n"] += 1

    task = asyncio.create_task(
        vg._run_idle_watchdog(lambda: False, on_hangup, poll_seconds=0.01)
    )
    await asyncio.sleep(0.05)           # let it poll a few times
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()             # no orphan left running
    assert calls["n"] == 0             # never hung up (should_hangup stayed False)

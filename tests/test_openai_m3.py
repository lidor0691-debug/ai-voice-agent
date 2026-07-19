"""
M3 tests — transport diagnostics/hardening, watchdog generation lifecycle, and
the single authoritative name wording.

Covers OPUS_PACKET_M3.md §F plus every explicit M3 requirement:
heartbeat marks are diagnostic-only, media-only dead-socket detection, watchdog
generations, reprompt-after-mark, statusCallback telemetry, Procfile ws flags,
and the removal of the old ambiguous name question.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pytest

import app.routes.voice_openai_live as vol
from app.routes.voice_openai_live import TurnController, CallState, Action


# ── helpers ───────────────────────────────────────────────────────────────────

def _acts(pairs):
    return [a for a, _ in pairs]


def _mark_name(pairs):
    for a, v in pairs:
        if a == Action.SEND_MARK:
            return v
    return None


def _make_ctrl():
    clk = [0.0]
    return TurnController(monotonic=lambda: clk[0]), clk


def _greet_to_waiting(c, clk, at=1.0):
    c.on_session_updated()
    c.on_response_created()
    c.on_output_delta()
    done = c.on_response_done("completed")
    clk[0] = at
    c.on_twilio_mark(_mark_name(done))
    assert c.state == CallState.WAITING_FOR_CALLER


def _valid_turn(c, text="אני רוצה לברר לגבי הפנסיה", dur=0.7):
    c.on_speech_started(0.0)
    c.on_speech_stopped(dur)
    return c.on_input_transcription(text, dur=dur)


def _play_one_response_to_waiting(c, clk, at):
    """Drive a just-created response (ASSISTANT_RESPONDING) through playback →
    mark return → back to a waiting state at time `at`."""
    c.on_response_created()
    c.on_output_delta()
    done = c.on_response_done("completed")
    clk[0] = at
    c.on_twilio_mark(_mark_name(done))


T1 = vol.OPENAI_WAITING_REPROMPT_SECONDS
T2 = vol.OPENAI_WAITING_CLOSE_SECONDS


# ── 1. active conversation never times out ───────────────────────────────────

def test_1_active_conversation_never_times_out():
    c, clk = _make_ctrl()
    _greet_to_waiting(c, clk, at=1.0)
    t = 2.0
    for _ in range(3):
        # caller turn well within T1 → generating (never a waiting state)
        clk[0] = t
        acts = _valid_turn(c)
        assert Action.RESPONSE_CREATE in _acts(acts)
        assert c.state == CallState.ASSISTANT_RESPONDING
        assert c.check_waiting_timeout(t + T1 + T2 + 100) == []   # not waiting
        # response plays, mark returns → ACTIVE
        _play_one_response_to_waiting(c, clk, at=t + 3)
        assert c.state == CallState.ACTIVE_CONVERSATION
        # within T1 of the fresh interval → no timeout
        assert c.check_waiting_timeout(t + 3 + T1 - 1) == []
        t += 10


# ── 2. valid caller turn resets the timeout (fresh generation) ───────────────

def test_2_valid_turn_resets_timeout():
    c, clk = _make_ctrl()
    _greet_to_waiting(c, clk, at=1.0)
    gen0 = c._timeout_gen
    # almost at T1, then a real caller turn arrives
    clk[0] = 1.0 + T1 - 1
    _valid_turn(c)
    _play_one_response_to_waiting(c, clk, at=1.0 + T1 + 5)
    assert c._timeout_gen > gen0            # a new generation armed
    assert c._reprompted is False
    # the new interval has not elapsed → no reprompt
    assert c.check_waiting_timeout(1.0 + T1 + 5 + T1 - 1) == []


# ── 3. stale generation cannot close a later state ───────────────────────────

def test_3_stale_generation_cannot_close_later_state():
    c, clk = _make_ctrl()
    _greet_to_waiting(c, clk, at=1.0)
    c._waiting_since = 0.0                  # force a very old arm
    # a new response is now generating/playing
    _valid_turn(c)
    c.on_response_created(); c.on_output_delta()
    assert c.state == CallState.RESPONDING_PLAYING
    # even with a long-past _waiting_since, a non-waiting state never times out
    assert c.check_waiting_timeout(10_000.0) == []


# ── 4. exactly one watchdog task and one heartbeat task, both cancelled ──────

def test_4_single_watchdog_and_heartbeat_tasks():
    src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
    assert src.count("asyncio.create_task(waiting_watchdog())") == 1
    assert src.count("asyncio.create_task(heartbeat_loop())") == 1
    # both cancelled together in the finally
    assert "for _t in (_watchdog_task, _heartbeat_task):" in src
    assert src.count("_t.cancel()") == 1


# ── 5. re-prompt: close countdown starts only after its playback mark ────────

def test_5_reprompt_timer_starts_after_mark_echo():
    c, clk = _make_ctrl()
    _greet_to_waiting(c, clk, at=1.0)
    # T1 elapses → REPROMPT; _waiting_since must NOT advance here
    a1 = c.check_waiting_timeout(1.0 + T1)
    assert _acts(a1) == [Action.REPROMPT]
    assert c.state == CallState.ASSISTANT_RESPONDING
    assert c._waiting_since == 1.0          # unchanged at emission
    # while the check-in is generating/playing, NO close no matter how long
    assert c.check_waiting_timeout(1.0 + T1 + T2 + 10_000) == []
    # check-in plays and its mark returns at t=1000 → fresh close interval
    _play_one_response_to_waiting(c, clk, at=1000.0)
    assert c._waiting_since == 1000.0
    assert c._reprompted is True
    assert c.check_waiting_timeout(1000.0 + T2 - 1) == []   # not yet
    a2 = c.check_waiting_timeout(1000.0 + T2 + 1)
    assert _acts(a2) == [Action.HANGUP_GRACE]
    assert c.state == CallState.CLOSING


# ── 6. closing phrase outside a closing context never hangs up ───────────────

def test_6_closing_phrase_before_any_turn_no_hangup():
    c, clk = _make_ctrl()
    c.on_session_updated(); c.on_response_created(); c.on_output_delta()
    c.on_assistant_transcript("להתראות ויום טוב")   # greeting only, valid_turns=0
    done = c.on_response_done("completed")
    assert Action.HANGUP_GRACE not in _acts(done)
    assert Action.SEND_MARK in _acts(done)


def test_6b_active_caller_speech_not_closed_by_watchdog():
    c, clk = _make_ctrl()
    _greet_to_waiting(c, clk, at=1.0)
    c.on_speech_started(2.0)                # state → CALLER_SPEAKING
    assert c.state == CallState.CALLER_SPEAKING
    c._waiting_since = 0.0                  # even with an ancient arm
    assert c.check_waiting_timeout(10_000.0) == []   # never during speech


# ── 7. natural name question appears exactly once ────────────────────────────

def test_7_natural_name_question_once():
    p = vol._NAME_PROTOCOL_INSTRUCTION
    q = "רק כדי שאוכל לרשום את הפנייה כמו שצריך, עם מי אני מדברת?"
    assert p.count(q) == 1
    # assembled into a full system instruction, still exactly once
    full = vol._openai_opening_instruction("BODY", "היי, מדברת מאיה") + p
    assert full.count(q) == 1


# ── 8. old ambiguous wording is gone from runtime construction ───────────────

def test_8_old_wording_absent_from_runtime():
    src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
    assert "ולמי אני מעבירה את הפנייה" not in src
    assert "ולמי אני מעבירה את הפנייה" not in vol._NAME_PROTOCOL_INSTRUCTION
    full = vol._openai_opening_instruction("BODY", "היי") + vol._NAME_PROTOCOL_INSTRUCTION
    assert "ולמי אני מעבירה את הפנייה" not in full


# ── 9 + transport: media-only dead-socket detector ──────────────────────────

class _HbEchoPump:
    """One media frame, then heartbeat echoes forever — media path is dead."""
    def __init__(self):
        self.n = 0
        self.close_calls = 0
        self.marks = []
        self.gap_ev = None

    async def receive_text(self):
        if self.n == 0:
            self.n += 1
            return json.dumps({"event": "media", "media": {"payload": "AA"}})
        await asyncio.sleep(0.05)          # real time so the media gap grows
        self.n += 1
        return json.dumps({"event": "mark", "mark": {"name": f"hb:{self.n}"}})

    async def forward_audio(self, p):
        pass

    async def close_openai(self):
        self.close_calls += 1

    def on_mark(self, name):
        self.marks.append(name)

    def diag(self, event, **kw):
        if event == "dead_socket_gap":
            self.gap_ev = kw

    async def run(self):
        return await vol._pump_twilio(
            receive_text=self.receive_text, forward_audio=self.forward_audio,
            close_openai=self.close_openai, diag=self.diag, on_mark=self.on_mark,
            gap_seconds=0.3, send_timeout=0.1,
            gap_context=lambda: {"probe": "ctx"},
        )


@pytest.mark.asyncio
async def test_9_media_gap_fires_despite_heartbeat_echoes():
    h = _HbEchoPump()
    reason = await h.run()
    assert reason == "dead_socket_gap"
    assert h.close_calls == 1                       # finalize once
    assert len(h.marks) >= 2                         # echoes DID flow through
    assert all(m.startswith("hb:") for m in h.marks)
    # forensic diag fields present (media-only + gap_context merged)
    assert h.gap_ev is not None
    assert h.gap_ev["elapsed_seconds"] >= 0.29
    assert h.gap_ev["seconds_since_media"] >= 0.29
    assert h.gap_ev["threshold"] == 0.3
    assert h.gap_ev.get("probe") == "ctx"


def test_heartbeat_marks_do_not_complete_playback_at_controller():
    # Defense-in-depth: even if a hb echo reached the controller, it is not in
    # pending_marks, so playback stays PLAYING (the wiring also filters hb:).
    c, clk = _make_ctrl()
    _greet_to_waiting(c, clk, at=1.0)
    _valid_turn(c)
    c.on_response_created(); c.on_output_delta()
    done = c.on_response_done("completed")
    assert c.state == CallState.RESPONDING_PLAYING
    c.on_twilio_mark("hb:99")                        # stray heartbeat name
    assert c.state == CallState.RESPONDING_PLAYING   # NOT completed
    c.on_twilio_mark(_mark_name(done))               # the real playback mark
    assert c.state == CallState.ACTIVE_CONVERSATION


def test_heartbeat_prefix_distinct_from_playback():
    assert vol._HEARTBEAT_MARK_PREFIX == "hb:"
    assert not "resp:1".startswith(vol._HEARTBEAT_MARK_PREFIX)


# ── statusCallback endpoint: telemetry only, no finalization ─────────────────

def test_status_callback_logs_and_returns_204():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(vol.router, prefix="/voice-ai")
    client = TestClient(app)
    for evt in ("stream-started", "stream-stopped", "stream-error"):
        r = client.post("/voice-ai/stream-status", data={
            "CallSid": "CAtest", "StreamSid": "MZtest",
            "StreamEvent": evt, "StreamError": "boom" if "error" in evt else "",
            "Timestamp": "2026-07-19T00:00:00Z",
        })
        assert r.status_code == 204            # accepted, no body, no finalize


# ── Procfile: ws ping flags present, no worker change ────────────────────────

def test_procfile_ws_ping_flags_and_no_workers():
    proc = pathlib.Path(vol.__file__).parents[2] / "Procfile"
    text = proc.read_text(encoding="utf-8")
    assert "--ws-ping-interval 5" in text
    assert "--ws-ping-timeout 10" in text
    assert "--workers" not in text             # single-process assumption kept

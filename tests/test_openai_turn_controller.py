"""
M2 tests — TurnController state machine, valid-caller-turn gate, one-time
greeting, playback-mark clock, barge-in guard, response.create guard, name
status/summary safety, and pump finalization-once (incl. mark forwarding).

Covers all 18 packet cases (OPUS_PACKET_M2.md §E) plus the closing-guard and
name-status distinctions. The controller is pure/synchronous, so most cases are
deterministic unit tests with no asyncio.
"""
from __future__ import annotations

import asyncio
import json
import os

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pytest
import websockets
from websockets.frames import Close
from starlette.websockets import WebSocketDisconnect

import app.routes.voice_openai_live as vol
import app.services.voice_shared as vs
from app.routes.voice_openai_live import (
    TurnController, CallState, Action, is_valid_caller_turn, _name_status,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _acts(pairs):
    """Extract the Action enums from a list of (Action, value) tuples."""
    return [a for a, _ in pairs]


def _mark_name(pairs):
    for a, v in pairs:
        if a == Action.SEND_MARK:
            return v
    return None


def _greeting_to_playing(c: TurnController):
    assert _acts(c.on_session_updated()) == [Action.RESPONSE_CREATE]
    c.on_response_created()
    c.on_output_delta()
    assert c.state == CallState.GREETING_PLAYING


def _greeting_to_waiting(c: TurnController):
    _greeting_to_playing(c)
    done = c.on_response_done("completed")
    mark = _mark_name(done)
    assert mark is not None
    c.on_twilio_mark(mark)
    assert c.state == CallState.WAITING_FOR_CALLER


def _valid_turn(c: TurnController, text="אני צריך ביטוח רכב", dur=0.7):
    c.on_speech_started(0.0)
    c.on_speech_stopped(dur)
    return c.on_input_transcription(text, dur=dur)


def _to_responding_playing(c: TurnController):
    """From WAITING → one valid turn → response generating → playing."""
    acts = _valid_turn(c)
    assert Action.RESPONSE_CREATE in _acts(acts)
    assert c.state == CallState.ASSISTANT_RESPONDING
    c.on_response_created()
    c.on_output_delta()
    assert c.state == CallState.RESPONDING_PLAYING


# ── 1. greeting created exactly once ─────────────────────────────────────────

def test_1_greeting_response_create_exactly_once():
    c = TurnController()
    a1 = c.on_session_updated()
    a2 = c.on_session_updated()   # duplicate session.updated
    a3 = c.on_session_updated()
    total = _acts(a1) + _acts(a2) + _acts(a3)
    assert total.count(Action.RESPONSE_CREATE) == 1
    assert c.greeting_done is True


# ── 2. no response.create before a valid caller turn (junk storm) ────────────

def test_2_no_response_create_before_valid_turn():
    c = TurnController()
    _greeting_to_playing(c)
    emitted = []
    for junk in ["", "   ", "Oh", "hello", "うん"]:
        c.on_speech_started(0.0)
        c.on_speech_stopped(0.3)
        emitted += _acts(c.on_input_transcription(junk, dur=0.3))
    assert Action.RESPONSE_CREATE not in emitted
    assert c.valid_turns == 0


# ── 3. silence-only call → honest name + guarded summary (post-call) ─────────

def test_3_silence_only_call_name_and_summary_guard():
    email_name, status = _name_status(None, [])
    assert email_name == "לא זוהה בבירור"
    assert status == "unclear_audio"
    prompt = vs._build_summary_prompt("מאיה: היי, איך אפשר לעזור?", caller_names_allowed=[])
    assert "אם שם פרטי מופיע רק בדברי מאיה" in prompt
    assert "שמות שהלקוח מסר" not in prompt   # nothing allowed


# ── 4. startup noise during greeting → no cancel, greeting completes ─────────

def test_4_startup_noise_does_not_cancel_greeting():
    c = TurnController()
    _greeting_to_playing(c)
    c.on_speech_started(0.0)
    c.on_speech_stopped(0.1)
    acts = c.on_input_transcription("", dur=0.1)     # empty transcription
    assert acts == []
    assert c.state == CallState.GREETING_PLAYING
    # greeting still completes normally → mark → waiting
    done = c.on_response_done("completed")
    assert Action.SEND_MARK in _acts(done)


# ── 5. valid Hebrew barge-in during greeting ≥600ms → cancel+clear + create ──

def test_5_valid_barge_in_during_greeting():
    c = TurnController()
    _greeting_to_playing(c)
    acts = _valid_turn(c, "רגע, יש לי שאלה", dur=0.7)
    assert _acts(acts) == [Action.CANCEL_AND_CLEAR, Action.RESPONSE_CREATE]
    assert c.state == CallState.ASSISTANT_RESPONDING


# ── 6. valid barge-in during a normal response → exactly one clear ───────────

def test_6_valid_barge_in_during_response_one_clear():
    c = TurnController()
    _greeting_to_waiting(c)
    _to_responding_playing(c)
    acts = _valid_turn(c, "רגע רגע", dur=0.8)
    assert _acts(acts).count(Action.CANCEL_AND_CLEAR) == 1
    assert Action.RESPONSE_CREATE in _acts(acts)


# ── 7. bare speech_started / short blip → zero actions ───────────────────────

def test_7_bare_speech_started_creates_nothing():
    c = TurnController()
    _greeting_to_waiting(c)
    assert c.on_speech_started(0.0) == []
    assert c.on_speech_stopped(0.05) == []
    # a sub-250ms blip with no real content is not a turn
    assert c.on_input_transcription("א", dur=0.05) == []
    assert c.valid_turns == 0


# ── 8. short whitelist Hebrew word is a valid turn ───────────────────────────

def test_8_short_hebrew_whitelist_accepted():
    c = TurnController()
    _greeting_to_waiting(c)
    acts = _valid_turn(c, "כן", dur=0.3)
    assert Action.RESPONSE_CREATE in _acts(acts)
    assert c.valid_turns == 1
    assert is_valid_caller_turn("סבבה", 0.3) is True


# ── 9. multilingual junk rejected ────────────────────────────────────────────

def test_9_multilingual_junk_rejected():
    c = TurnController()
    _greeting_to_waiting(c)
    acts = _valid_turn(c, "Quand elle dort", dur=1.0)
    assert acts == []
    assert c.valid_turns == 0
    assert is_valid_caller_turn("どっちなんですか?", 1.0) is False


# ── 10. racing segments → no duplicate response.create ───────────────────────

def test_10_racing_segments_no_duplicate_create():
    c = TurnController()
    _greeting_to_waiting(c)
    a1 = _valid_turn(c, "אני רוצה ביטוח", dur=0.6)       # accepted → generating
    assert c.state == CallState.ASSISTANT_RESPONDING
    # second transcription arrives while still generating (pre-first-delta)
    a2 = c.on_input_transcription("ועוד משהו", dur=0.6)
    assert a2 == []                                       # dropped, no dup create
    creates = _acts(a1).count(Action.RESPONSE_CREATE) + _acts(a2).count(Action.RESPONSE_CREATE)
    assert creates == 1
    assert c.valid_turns == 1


# ── 11–14. pump finalization-once (incl. mark forwarding) ────────────────────
# The four exit paths (twilio_stop / twilio_disconnect / openai_closed /
# dead_socket_gap) are exhaustively covered in test_openai_ab_m1_1.py. Here we
# add the M2-specific guarantee: mark events are forwarded AND the pump still
# closes OpenAI exactly once on a normal stop.

class _Pump:
    def __init__(self, frames, forward="ok"):
        self.frames = list(frames)
        self.forward = forward
        self.close_calls = 0
        self.marks = []

    async def receive_text(self):
        if self.frames:
            return self.frames.pop(0)
        await asyncio.Event().wait()

    async def forward_audio(self, payload):
        if self.forward == "closed":
            raise websockets.exceptions.ConnectionClosed(Close(1006, "x"), None)

    async def close_openai(self):
        self.close_calls += 1

    def on_mark(self, name):
        self.marks.append(name)

    async def run(self, **kw):
        return await vol._pump_twilio(
            receive_text=self.receive_text, forward_audio=self.forward_audio,
            close_openai=self.close_openai, diag=lambda e, **k: None,
            on_mark=self.on_mark, gap_seconds=0.05, send_timeout=0.05, **kw,
        )


def _media(p="AA"):
    return json.dumps({"event": "media", "media": {"payload": p}})


def _mark(name):
    return json.dumps({"event": "mark", "mark": {"name": name}})


STOP = json.dumps({"event": "stop"})


@pytest.mark.asyncio
async def test_11_14_pump_forwards_marks_and_finalizes_once():
    h = _Pump([_media(), _mark("resp:1"), _media(), STOP])
    reason = await h.run()
    assert reason == "twilio_stop"
    assert h.close_calls == 1
    assert h.marks == ["resp:1"]


@pytest.mark.asyncio
async def test_12_openai_closed_finalizes_once():
    h = _Pump([_media()], forward="closed")
    reason = await h.run()
    assert reason == "openai_closed"
    assert h.close_calls == 1


@pytest.mark.asyncio
async def test_13_dead_socket_gap_finalizes_once():
    h = _Pump([_media()])   # then receive hangs → gap fires
    reason = await h.run()
    assert reason == "dead_socket_gap"
    assert h.close_calls == 1


@pytest.mark.asyncio
async def test_11_twilio_disconnect_finalizes_once():
    class H(_Pump):
        async def receive_text(self):
            if self.frames:
                return self.frames.pop(0)
            raise WebSocketDisconnect(code=1006)
    h = H([_media()])
    reason = await h.run()
    assert reason == "twilio_disconnect"
    assert h.close_calls == 1


# ── 15. summary guard: assistant-only name never attributed ──────────────────

def test_15_summary_guard_assistant_only_name():
    transcript = "לקוח: אני\nמאיה: נעים מאוד, דניאל, איך אפשר לעזור?"
    prompt = vs._build_summary_prompt(transcript, caller_names_allowed=[])
    assert "אם שם פרטי מופיע רק בדברי מאיה" in prompt   # hard rule present
    assert "כנה את המתקשר \"הלקוח\"" in prompt
    assert "שמות שהלקוח מסר" not in prompt              # empty allow-list


def test_15b_summary_allows_caller_provided_name():
    prompt = vs._build_summary_prompt(
        "לקוח: אני דוד\nמאיה: נעים מאוד", caller_names_allowed=["דוד"]
    )
    assert "שמות שהלקוח מסר" in prompt and "דוד" in prompt


# ── 16/17. name-status distinctions ──────────────────────────────────────────

def test_16_garbled_transcript_unclear_audio():
    name, status = _name_status(None, ["Quand elle dort", "どうも"])
    assert name == "לא זוהה בבירור"
    assert status == "unclear_audio"


def test_17_clean_no_name_not_provided():
    name, status = _name_status(None, ["אני רוצה לברר לגבי הפנסיה", "תודה רבה"])
    assert name == "לא נמסר"
    assert status == "not_provided"


def test_name_confirmed_requires_caller_line():
    assert _name_status("דוד", ["שלום, מדבר דוד"]) == ("דוד", "confirmed")


def test_name_unconfirmed_when_not_in_caller_lines():
    name, status = _name_status("דוד", ["אני רוצה ביטוח רכב"])
    assert status == "unconfirmed"
    assert name == "דוד (לא אומת)"


# ── 18. summary + excerpt always available ───────────────────────────────────

def test_18_excerpt_always_present_even_empty():
    assert vol._transcript_excerpt([], []) == ""          # a string, always
    assert isinstance(vol._transcript_excerpt(["היי"], ["שלום"]), str)


@pytest.mark.asyncio
async def test_18b_summary_empty_transcript_returns_string():
    out = await vs.summarize_transcript("", caller_names_allowed=[])
    assert out == ""


# ── closing guard (state + tail) ─────────────────────────────────────────────

def test_closing_phrase_ignored_before_any_valid_turn():
    c = TurnController()
    _greeting_to_playing(c)
    c.on_assistant_transcript("להתראות ויום טוב")   # greeting-only, valid_turns=0
    done = c.on_response_done("completed")
    assert Action.HANGUP_GRACE not in _acts(done)
    assert Action.SEND_MARK in _acts(done)


def test_closing_phrase_mid_sentence_not_in_tail_no_hangup():
    c = TurnController()
    _greeting_to_waiting(c)
    _to_responding_playing(c)
    # "יום טוב" appears but NOT in the last 30 chars → not a closing
    long_tail = "יום טוב, עכשיו בוא נמשיך לדבר על הביטוח שלך ועל האפשרויות שיש לך כרגע"
    c.on_assistant_transcript(long_tail)
    done = c.on_response_done("completed")
    assert Action.HANGUP_GRACE not in _acts(done)


def test_closing_phrase_in_tail_after_valid_turn_hangs_up():
    c = TurnController()
    _greeting_to_waiting(c)
    _to_responding_playing(c)
    c.on_assistant_transcript("רשמתי הכל, תודה רבה ולהתראות")   # closing in tail
    done = c.on_response_done("completed")
    assert Action.HANGUP_GRACE in _acts(done)
    assert c.state == CallState.CLOSING


# ── waiting watchdog (silence → reprompt → close) ────────────────────────────

def test_waiting_watchdog_reprompt_then_close():
    c = TurnController()
    _greeting_to_waiting(c)
    c._waiting_since = 0.0
    # before threshold → nothing
    assert c.check_waiting_timeout(vol.OPENAI_WAITING_REPROMPT_SECONDS - 1) == []
    # first timeout → one re-prompt
    a1 = c.check_waiting_timeout(vol.OPENAI_WAITING_REPROMPT_SECONDS + 1)
    assert _acts(a1) == [Action.REPROMPT]
    assert c.state == CallState.ASSISTANT_RESPONDING
    # simulate the re-prompt response completing back to waiting
    c.on_response_created(); c.on_output_delta()
    done = c.on_response_done("completed")
    c.on_twilio_mark(_mark_name(done))
    c._waiting_since = 100.0
    a2 = c.check_waiting_timeout(100.0 + vol.OPENAI_WAITING_REPROMPT_SECONDS + 1)
    assert _acts(a2) == [Action.HANGUP_GRACE]
    assert c.state == CallState.CLOSING


def test_valid_turn_resets_reprompt():
    c = TurnController()
    _greeting_to_waiting(c)
    c._reprompted = True
    _valid_turn(c, "אני רוצה ביטוח", dur=0.6)
    assert c._reprompted is False


# ── playback clock: response.done is NOT playback-done ───────────────────────

def test_marks_gate_waiting_transition():
    c = TurnController()
    _greeting_to_playing(c)
    done = c.on_response_done("completed")
    # still PLAYING until Twilio echoes the mark back
    assert c.state == CallState.GREETING_PLAYING
    c.on_twilio_mark(_mark_name(done))
    assert c.state == CallState.WAITING_FOR_CALLER


def test_cancelled_response_sends_no_mark():
    c = TurnController()
    _greeting_to_playing(c)
    # a cancelled (barged) response emits no mark and does not strand state
    assert c.on_response_done("cancelled") == []


# ── invariant: response.create is sent from exactly one place ────────────────

def test_response_create_single_send_site():
    import pathlib
    src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
    assert src.count('"type": "response.create"') == 1

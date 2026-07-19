"""
M1.1 tests — zombie/dead-socket fixes, Hebrew STT pin, natural opening,
name-fallback distinctions, summary/excerpt.

The core proof the incident review demanded: `_pump_twilio` invokes
`close_openai()` EXACTLY ONCE on every exit path (stop, disconnect,
dead-socket gap, send timeout, OpenAI close, unexpected error), which is what
guarantees the handler's single `finally` finalization always runs.
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


# ── Pump harness ──────────────────────────────────────────────────────────────

class PumpHarness:
    """Drives _pump_twilio with scripted frames / failure behaviors."""

    def __init__(self, frames=None, receive_exc=None, hang_receive_after=None,
                 forward_behavior="ok"):
        self.frames = list(frames or [])
        self.receive_exc = receive_exc
        self.hang_receive_after = hang_receive_after  # hang once frames exhausted
        self.forward_behavior = forward_behavior      # ok | hang | closed
        self.close_calls = 0
        self.forwarded: list[str] = []
        self.diag_events: list[dict] = []

    async def receive_text(self):
        if self.frames:
            return self.frames.pop(0)
        if self.receive_exc is not None:
            raise self.receive_exc
        # hang forever (dead socket) — pump's wait_for must fire
        await asyncio.Event().wait()

    async def forward_audio(self, payload):
        if self.forward_behavior == "hang":
            await asyncio.Event().wait()
        if self.forward_behavior == "closed":
            raise websockets.exceptions.ConnectionClosed(Close(1006, "abnormal"), None)
        self.forwarded.append(payload)

    async def close_openai(self):
        self.close_calls += 1

    def diag(self, event, **kw):
        self.diag_events.append({"event": event, **kw})

    async def run(self, gap_seconds=0.08, send_timeout=0.08):
        return await vol._pump_twilio(
            receive_text=self.receive_text,
            forward_audio=self.forward_audio,
            close_openai=self.close_openai,
            diag=self.diag,
            gap_seconds=gap_seconds,
            send_timeout=send_timeout,
        )


def _media(payload="AAAA"):
    return json.dumps({"event": "media", "media": {"payload": payload}})


STOP = json.dumps({"event": "stop"})


# ── 1. Exit paths: finalization-enabling close, exactly once ─────────────────

class TestPumpExitPaths:
    @pytest.mark.asyncio
    async def test_normal_stop(self):
        h = PumpHarness(frames=[_media("p1"), _media("p2"), STOP])
        reason = await h.run()
        assert reason == "twilio_stop"
        assert h.close_calls == 1
        assert h.forwarded == ["p1", "p2"]

    @pytest.mark.asyncio
    async def test_disconnect_without_stop_logs_code_and_closes_once(self):
        """The incident case: Twilio socket dies with no stop event."""
        h = PumpHarness(frames=[_media("p1")], receive_exc=WebSocketDisconnect(code=1006))
        reason = await h.run()
        assert reason == "twilio_disconnect"
        assert h.close_calls == 1
        ev = [e for e in h.diag_events if e["event"] == "twilio_ws_disconnect"]
        assert len(ev) == 1 and ev[0]["code"] == 1006

    @pytest.mark.asyncio
    async def test_dead_socket_gap_terminates_and_logs_elapsed(self):
        """No frames at all → dead socket detected at the gap threshold."""
        h = PumpHarness(frames=[_media("p1")])  # then receive hangs forever
        reason = await h.run(gap_seconds=0.08)
        assert reason == "dead_socket_gap"
        assert h.close_calls == 1
        ev = [e for e in h.diag_events if e["event"] == "dead_socket_gap"]
        assert len(ev) == 1
        assert ev[0]["elapsed_seconds"] >= 0.07
        assert ev[0]["threshold"] == 0.08

    @pytest.mark.asyncio
    async def test_send_timeout_backpressure(self):
        h = PumpHarness(frames=[_media("p1")], forward_behavior="hang")
        reason = await h.run(send_timeout=0.08)
        assert reason == "openai_send_timeout"
        assert h.close_calls == 1
        ev = [e for e in h.diag_events if e["event"] == "openai_send_timeout"]
        assert len(ev) == 1 and ev[0]["operation"] == "input_audio_buffer.append"

    @pytest.mark.asyncio
    async def test_openai_closed_during_send(self):
        h = PumpHarness(frames=[_media("p1")], forward_behavior="closed")
        reason = await h.run()
        assert reason == "openai_closed"
        assert h.close_calls == 1

    @pytest.mark.asyncio
    async def test_unexpected_error_still_closes_once(self):
        h = PumpHarness(frames=["NOT JSON"])
        reason = await h.run()
        assert reason.startswith("error:")
        assert h.close_calls == 1

    @pytest.mark.asyncio
    async def test_gap_not_triggered_by_flowing_frames(self):
        """Frames arriving faster than the gap threshold never trip the guard —
        the detector fires on dead sockets, not on caller silence (Twilio keeps
        sending media frames during silence)."""
        frames = [_media(f"p{i}") for i in range(5)] + [STOP]
        h = PumpHarness(frames=frames)
        reason = await h.run(gap_seconds=0.5)
        assert reason == "twilio_stop"
        assert not [e for e in h.diag_events if e["event"] == "dead_socket_gap"]


# ── 2. Config ────────────────────────────────────────────────────────────────

class TestM11Config:
    def test_gap_default_8s_env_tunable(self):
        if not os.getenv("OPENAI_INBOUND_GAP_SECONDS"):
            assert vol.OPENAI_INBOUND_GAP_SECONDS == 8.0
        if not os.getenv("OPENAI_SEND_TIMEOUT_SECONDS"):
            assert vol.OPENAI_SEND_TIMEOUT_SECONDS == 2.0

    def test_transcription_language_pinned_hebrew(self):
        s = vol._build_session_update("P")["session"]
        t = s["audio"]["input"]["transcription"]
        assert t["language"] == "he"
        assert t["model"] == vol.OPENAI_REALTIME_TRANSCRIBE_MODEL


# ── 3. Natural opening + name protocol ───────────────────────────────────────

class TestOpening:
    def test_opening_is_natural_one_time_not_verbatim(self):
        # M2: greeting-as-intent, one opening turn, no second question, never
        # replayed. Text updated per OPUS_PACKET_M2.md §C.
        base = "PROMPT BODY"
        fm = "היי, מדברת מאיה מהמשרד של רועי. איך אפשר לעזור?"
        out = vol._openai_opening_instruction(base, fm)
        assert out.count(fm) == 1
        assert "פעם אחת בלבד" in out
        assert "ברוח" in out
        assert "בלי שאלה נוספת באותו תור" in out   # one opening turn only
        assert "בדיוק" not in out       # no forced word-for-word recitation
        assert "תמיד" not in out        # no re-greeting trigger
        assert out.endswith(base)

    def test_no_first_message_returns_base(self):
        assert vol._openai_opening_instruction("BASE", "") == "BASE"

    def test_name_protocol_ask_after_reason_neutral_never_invent(self):
        # M3: single authoritative natural phrasing (replaces the ambiguous M2
        # "ולמי אני מעבירה את הפנייה?"). Ask after the reason, one clarification.
        p = vol._NAME_PROTOCOL_INSTRUCTION
        assert "אל תשאלי לשם מיד" in p                 # not immediate
        assert "רק כדי שאוכל לרשום את הפנייה כמו שצריך, עם מי אני מדברת?" in p  # new wording
        assert "ולמי אני מעבירה את הפנייה?" not in p    # old ambiguous wording gone
        assert "פעם אחת" in p                           # ask once
        assert "לאישור" in p                            # confirm once
        assert "בקשי פעם אחת לחזור עליו" in p           # one clarification if unclear
        assert "אם הפונה מסרב או מתחמק — המשיכי" in p    # refusal → continue
        assert "לעולם אל תאמרי שם שהפונה לא אמר במפורש" in p  # never invent
        assert "דוד" not in p                            # no literal example name


# ── 4. Name fallback distinctions ────────────────────────────────────────────

class TestNameFallback:
    def test_clean_hebrew_no_name_means_not_provided(self):
        lines = ["רוצה לברר לגבי הפנסיה שלי", "אשמח שיחזרו אליי"]
        assert vol._name_fallback(lines) == "לא נמסר"

    def test_garbled_transcript_means_unclear(self):
        # the real call-3 signature: junk languages on short utterances
        lines = ["Quand elle dort", "どっちなんですか?", "רוצה לברר לגבי הפנסיה"]
        assert vol._name_fallback(lines) == "לא זוהה בבירור"

    def test_empty_transcript_means_unclear(self):
        assert vol._name_fallback([]) == "לא זוהה בבירור"
        assert vol._name_fallback(["", "  "]) == "לא זוהה בבירור"


# ── 5. Summary + excerpt ─────────────────────────────────────────────────────

class TestSummaryExcerpt:
    @pytest.mark.asyncio
    async def test_summary_returns_empty_without_key_never_raises(self, monkeypatch):
        monkeypatch.setattr(vs, "_OPENAI_API_KEY", "")
        assert await vs.summarize_transcript("לקוח: שלום\nמאיה: שלום") == ""

    @pytest.mark.asyncio
    async def test_summary_empty_transcript_short_circuits(self):
        assert await vs.summarize_transcript("   ") == ""

    def test_excerpt_role_tagged_and_truncated(self):
        excerpt = vol._transcript_excerpt(["א" * 400], ["ב" * 400], max_chars=100)
        assert excerpt.startswith("לקוח:")
        assert len(excerpt) <= 101  # 100 + ellipsis
        full = vol._transcript_excerpt(["היי"], ["שלום"])
        assert "לקוח: היי" in full and "מאיה: שלום" in full

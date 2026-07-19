"""
OpenAI Realtime (GA) voice path — Milestone 1 A/B bridge.

Routes registered under the /voice-ai prefix (see main.py):
  WS /voice-ai/stream-openai — bidirectional Twilio Media Stream ↔ OpenAI Realtime

There is NO separate TwiML entry point: the existing POST /voice-ai/voice-gemini
entry dispatches here when the A/B gate matches (flag ON + client_id
allowlisted — Roi only). Everything else (fail-closed agent resolution, Twilio
<Stream><Parameter> handoff, in-memory fallback) is reused from voice_gemini.

Milestone 1 scope (deliberately minimal):
  - Twilio µ-law (PCMU) passthrough both directions — zero transcoding.
  - Same Roi system prompt + same one-time greeting injection.
  - Separate caller / assistant transcript buffers.
  - Post-call reuse of the existing lead/email pipeline (same helpers, same
    webhook payload shape → Make scenario unchanged; source="voice_openai").
  - [OPENAI-DIAG] structured logs for A/B comparison against [GEMINI-DIAG].
  - NO function calling, NO idle-watchdog redesign (natural closing-phrase
    hangup is reused as-is for parity), NO studio-tenant changes.

Rollback: OPENAI_REALTIME_AB_ENABLED=false (or drop the client_id from
OPENAI_REALTIME_CLIENT_IDS) — every call routes back to the Gemini path.
Model rollback: OPENAI_REALTIME_MODEL=gpt-realtime-2 (handshake-verified).
"""

import asyncio
import json
import os
import time
from datetime import datetime

import websockets
from fastapi import APIRouter, WebSocket, Query, Request
from fastapi.responses import Response
from starlette.websockets import WebSocketDisconnect

from app.services.lead_capture import save_lead
from app.services.voice_shared import extract_lead_from_transcript as _extract_lead_from_transcript
from app.services.voice_shared import send_voice_webhook as _send_voice_webhook
from app.services.voice_shared import get_customer_history as _get_customer_history
from app.services.voice_shared import summarize_transcript as _summarize_transcript
from app.integrations.twilio_client import _get_client as _get_twilio_client

# One-way reuse from the Gemini route (voice_gemini NEVER imports this module —
# it only reads the A/B gate from voice_shared, so there is no import cycle).
from app.routes.voice_gemini import (
    _GEMINI_CALL_CONTEXT,
    _resolve_gemini_context,
    _contains_closing_phrase,
    CLOSING_GRACE_SECONDS,
)

router = APIRouter()


# ── Twilio <Stream> status callback (M3) — AUTHORITATIVE TELEMETRY ONLY ───────
# Twilio POSTs stream lifecycle events here (stream-started / stream-stopped /
# stream-error) with its OWN view of what happened — the discriminator for
# "who stalled" during a dead-socket gap. It NEVER finalizes a call, closes a
# socket, or changes any conversational state: logging only.

@router.post("/stream-status")
async def stream_status(request: Request):
    try:
        form = await request.form()
    except Exception as exc:
        print(f"[STREAM-STATUS] could not parse form: {exc}")
        return Response(status_code=204)
    call_sid    = form.get("CallSid", "")
    stream_sid  = form.get("StreamSid", "")
    stream_evt  = form.get("StreamEvent", "")
    stream_err  = form.get("StreamError", "")
    timestamp   = form.get("Timestamp", "")
    # client_id only if safely resolvable from the in-memory handoff store
    # (never from the callback body, which carries no tenant identity). Best
    # effort — absent under cross-process routing, which is fine for telemetry.
    client_id = ""
    try:
        _ctx = _GEMINI_CALL_CONTEXT.get(call_sid) or {}
        client_id = str((_ctx.get("agent_cfg") or {}).get("client_id") or "")
    except Exception:
        client_id = ""
    print(
        "[STREAM-STATUS] " + json.dumps({
            "call_sid": call_sid, "stream_sid": stream_sid,
            "stream_event": stream_evt, "stream_error": stream_err,
            "timestamp": timestamp, "client_id": client_id,
        }, ensure_ascii=False)
    )
    return Response(status_code=204)

# ── Config ────────────────────────────────────────────────────────────────────

_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)

# GA model — verified available on this project AND WebSocket-handshake-tested.
# Rollback option (also verified): gpt-realtime-2.
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1").strip()

# Realtime output voice (GA voices include marin/cedar + the classic set).
OPENAI_REALTIME_VOICE = os.getenv("OPENAI_REALTIME_VOICE", "marin").strip()

# Streaming STT model for caller-side transcription (must be enabled explicitly
# in the GA session config; feeds the caller transcript buffer).
OPENAI_REALTIME_TRANSCRIBE_MODEL = os.getenv(
    "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-realtime-whisper"
).strip()

# Dead-socket detector (M1.1): Twilio sends a media frame every ~20ms for the
# whole call — even during total caller silence (the PSTN line always produces
# audio). A multi-second gap therefore means the Twilio socket is DEAD (proxy
# stall / half-open connection), never "the caller is quiet". 8s default per
# incident review; env-tunable without deploy.
OPENAI_INBOUND_GAP_SECONDS = float(os.getenv("OPENAI_INBOUND_GAP_SECONDS", "8.0"))

# Backpressure trap (M1.1): openai_ws.send() should complete in microseconds.
# If it blocks, OpenAI stopped reading (TCP backpressure) and the bridge is
# effectively dead — fail fast into finalization instead of zombie-hanging.
OPENAI_SEND_TIMEOUT_SECONDS = float(os.getenv("OPENAI_SEND_TIMEOUT_SECONDS", "2.0"))

# Transport heartbeat (M3): every N seconds send a uniquely-named Twilio mark
# ("hb:<n>"). Purpose is DIAGNOSTIC + keepalive only — its echo is an inbound
# frame that proves the Railway→Twilio→Railway control path is alive, and it
# keeps the outbound direction non-idle through any proxy. Heartbeat marks and
# their echoes NEVER touch the TurnController and NEVER reset the media-frame
# dead-socket detector (which measures caller-audio liveness specifically).
OPENAI_HEARTBEAT_SECONDS = float(os.getenv("OPENAI_HEARTBEAT_SECONDS", "5.0"))

_OPENAI_WS_URL = "wss://api.openai.com/v1/realtime?model={model}"

# Heartbeat mark name prefix — kept distinct from response playback marks
# ("resp:") so the pump can route echoes correctly (diag only vs controller).
_HEARTBEAT_MARK_PREFIX = "hb:"


# ── Pure helpers (unit-tested) ────────────────────────────────────────────────

def _build_session_update(system_instruction: str) -> dict:
    """
    GA session.update payload.

    - audio/pcmu both directions: Twilio Media Streams speak µ-law 8 kHz
      natively, so audio passes through base64-verbatim with NO transcoding.
    - server_vad tuned for a noisy Israeli phone line (M2): threshold 0.6,
      prefix_padding 300ms, silence 700ms.
    - create_response=false / interrupt_response=false (M2, RC1): the SERVER
      must NOT auto-create a reply from any speech_started/stopped, nor
      auto-cancel a response on caller speech. Response creation and barge-in
      are owned by the application (TurnController) and only ever happen after a
      gated valid caller turn — so noise, echo, silence, and junk transcription
      can never spawn or cancel a reply.
    - Input transcription ON, language pinned to Hebrew (M1.1) — short phone
      utterances otherwise hallucinate into other languages, which is exactly
      where caller names live.
    """
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "output_modalities": ["audio"],
            "instructions": system_instruction,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "transcription": {
                        "model": OPENAI_REALTIME_TRANSCRIBE_MODEL,
                        "language": "he",
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.6,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 700,
                        # App-owned turn-taking — see docstring (M2/RC1).
                        "create_response": False,
                        "interrupt_response": False,
                    },
                },
                "output": {
                    "format": {"type": "audio/pcmu"},
                    "voice": OPENAI_REALTIME_VOICE,
                },
            },
        },
    }


def _openai_opening_instruction(base_prompt: str, first_message: str) -> str:
    """
    OpenAI-path opening (M2): the greeting is an INTENT, not a script — one
    short opening turn, no name question in the opening, never replayed even if
    interrupted. Exact authoritative text per OPUS_PACKET_M2.md §C.
    Gemini path untouched — it keeps its own injection.
    """
    fm = (first_message or "").strip()
    if not fm:
        return base_prompt
    return (
        "פתיחת שיחה (פעם אחת בלבד): פתחי בברכה קצרה, חמה וטבעית ברוח: "
        f"\"{fm}\" — משפט פתיחה אחד בלבד, בלי שאלה נוספת באותו תור. "
        "עברית ישראלית יומיומית, לא הודעה מוקלטת. "
        "אל תחזרי על הברכה לעולם, גם אם קטעו אותך.\n\n"
        + base_prompt
    )


# Name protocol (M3): ONE authoritative natural phrasing. Ask only after the
# reason is understood; ask once; confirm once; accept a correction; one
# clarification if unclear; never invent; never re-ask after refusal. Exact
# text per OPUS_PACKET_M3.md §C. (Replaces the ambiguous M2 "ולמי אני מעבירה
# את הפנייה?" — which sounded like asking where to TRANSFER the call.)
_NAME_PROTOCOL_INSTRUCTION = (
    "\n\nשם הפונה: אל תשאלי לשם מיד. קודם תני לפונה להסביר במה מדובר. "
    "אחרי שהבנת את הסיבה, שאלי פעם אחת: "
    "\"רק כדי שאוכל לרשום את הפנייה כמו שצריך, עם מי אני מדברת?\". "
    "כשנמסר שם — חזרי עליו פעם אחת לאישור, בטבעיות, וקבלי תיקון אם יש. "
    "אם לא שמעת את השם ברור — בקשי פעם אחת לחזור עליו; אם עדיין לא ברור, המשיכי בשיחה. "
    "אם הפונה מסרב או מתחמק — המשיכי ואל תשאלי שוב. "
    "לעולם אל תאמרי שם שהפונה לא אמר במפורש."
)

# Natural one-off check-in spoken when the caller is silent (WAITING watchdog,
# M3). App-created, single, no re-greeting — one short sentence.
_REPROMPT_INSTRUCTION = (
    "שאלי בקצרה וטבעי אם עדיין שומעים אותך, למשל: \"הלו? עדיין איתי?\""
)


def _has_hebrew(text: str) -> bool:
    return any("֐" <= ch <= "׿" for ch in text or "")


def _name_fallback(caller_lines: list[str]) -> str:
    """
    Post-call name value when extraction found no name — NEVER a guess:
      - "לא זוהה בבירור" — speech/transcription quality was insufficient
        (no usable caller lines at all, or a meaningful share of the caller's
        lines came back without any Hebrew — the STT-garble signature).
      - "לא נמסר"       — transcription looks fine; the caller simply did not
        provide a name (refused / never asked to).
    """
    lines = [ln.strip() for ln in caller_lines if (ln or "").strip()]
    if not lines:
        return "לא זוהה בבירור"
    garbled = sum(1 for ln in lines if not _has_hebrew(ln))
    if garbled * 3 >= len(lines):  # ≥ one third garbled → quality problem
        return "לא זוהה בבירור"
    return "לא נמסר"


def _transcript_excerpt(caller_lines: list[str], assistant_lines: list[str], max_chars: int = 500) -> str:
    """Short role-tagged excerpt for the email — always available even when
    structured extraction fails. Grouped by role (M1 buffers are separate)."""
    full = _full_transcript(caller_lines, assistant_lines)
    if len(full) <= max_chars:
        return full
    return full[:max_chars].rstrip() + "…"


def _customer_transcript(caller_lines: list[str]) -> str:
    """Customer-only text for lead extraction — assistant speech NEVER included
    (prevents extracting a name the assistant said)."""
    return "\n".join(f"לקוח: {ln}" for ln in caller_lines if (ln or "").strip())


def _full_transcript(caller_lines: list[str], assistant_lines: list[str]) -> str:
    """Interleaving is not preserved in M1 (separate buffers); grouped by role.
    Used for logging/inspection only — extraction uses _customer_transcript."""
    parts = [f"לקוח: {ln}" for ln in caller_lines if (ln or "").strip()]
    parts += [f"מאיה: {ln}" for ln in assistant_lines if (ln or "").strip()]
    return "\n".join(parts)


def _diag(event: str, call_sid: str, **kw) -> None:
    """Structured A/B diagnostic log line (mirrors [GEMINI-DIAG] coverage)."""
    rec = {"event": event, "call_sid": call_sid, "t": round(time.monotonic(), 3)}
    rec.update(kw)
    print(f"[OPENAI-DIAG] {json.dumps(rec, ensure_ascii=False)}")


def _compute_appointment_at(appt_day: str, appt_time: str) -> str | None:
    """Next occurrence of Hebrew weekday + HH:MM as ISO timestamp (mirrors the
    Gemini path; extraction into a shared helper is queued for Milestone 2)."""
    if not (appt_day and appt_time):
        return None
    try:
        from datetime import timedelta
        _DAY_MAP = {
            "ראשון": 6, "שני": 0, "שלישי": 1,
            "רביעי": 2, "חמישי": 3, "שישי": 4, "שבת": 5,
        }
        target = _DAY_MAP.get(appt_day)
        if target is None:
            return None
        now = datetime.utcnow()
        days_ahead = (target - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        h, m = map(int, appt_time.split(":"))
        return (now + timedelta(days=days_ahead)).replace(
            hour=h, minute=m, second=0, microsecond=0
        ).isoformat()
    except Exception as exc:
        print(f"[OPENAI-LEAD] ⚠️ Failed to compute appointment_at: {exc}")
        return None


# ── Turn-taking state machine (M2) ────────────────────────────────────────────
# Pure, synchronous, unit-testable. It owns response creation, barge-in, the
# playback clock (Twilio marks), and the valid-caller-turn gate. It performs NO
# I/O — every method returns a list of Action tuples that the async wiring
# executes. This is what removes server-VAD auto-response (RC1) and the
# generation-vs-playback race (RC2).

import enum


class CallState(enum.Enum):
    INITIALIZING          = "INITIALIZING"
    GREETING_REQUESTED    = "GREETING_REQUESTED"
    GREETING_PLAYING      = "GREETING_PLAYING"
    WAITING_FOR_CALLER    = "WAITING_FOR_CALLER"
    CALLER_SPEAKING       = "CALLER_SPEAKING"
    PROCESSING_CALLER_TURN = "PROCESSING_CALLER_TURN"
    ASSISTANT_RESPONDING  = "ASSISTANT_RESPONDING"   # generating (pre-first-delta)
    RESPONDING_PLAYING    = "RESPONDING_PLAYING"     # audio playing, awaiting mark
    ACTIVE_CONVERSATION   = "ACTIVE_CONVERSATION"    # == waiting, after ≥1 turn
    CLOSING               = "CLOSING"
    FINALIZING            = "FINALIZING"
    CLOSED                = "CLOSED"


class Action(enum.Enum):
    RESPONSE_CREATE  = "RESPONSE_CREATE"
    CANCEL_AND_CLEAR = "CANCEL_AND_CLEAR"
    SEND_MARK        = "SEND_MARK"        # value = mark name
    HANGUP_GRACE     = "HANGUP_GRACE"
    REPROMPT         = "REPROMPT"


# Valid-caller-turn gate (packet §B)
_TURN_WHITELIST = {"כן", "לא", "היי", "שלום", "אוקיי", "סבבה"}
MIN_TURN_DURATION_S      = 0.25   # reject sub-250ms blips
BARGE_IN_MIN_DURATION_S  = 0.6    # only a strong turn interrupts playback
CLOSING_TAIL_CHARS       = 30     # closing phrase must be near the end
# WAITING watchdog (M3, conservative pilot timers): after this long in a genuine
# waiting state with no valid caller turn → ONE natural check-in (re-prompt).
OPENAI_WAITING_REPROMPT_SECONDS = float(os.getenv("OPENAI_WAITING_REPROMPT_SECONDS", "50.0"))
# After the check-in's playback mark returns (a fresh waiting interval), this
# much more silence → close. Counted only from the re-prompt's mark return.
OPENAI_WAITING_CLOSE_SECONDS = float(os.getenv("OPENAI_WAITING_CLOSE_SECONDS", "40.0"))

_WAITING_STATES = (
    CallState.WAITING_FOR_CALLER,
    CallState.ACTIVE_CONVERSATION,
    CallState.CALLER_SPEAKING,
)
_PLAYING_STATES = (
    CallState.GREETING_PLAYING,
    CallState.RESPONDING_PLAYING,
)


def is_valid_caller_turn(text: str, dur: float) -> bool:
    """A gated valid caller turn: non-empty, contains Hebrew, and either ≥2
    chars or an explicit short-Hebrew whitelist word, and ≥250ms of speech.
    Multilingual junk (no Hebrew) is never a turn."""
    t = (text or "").strip()
    if not t or not _has_hebrew(t):
        return False
    if not (len(t) >= 2 or t in _TURN_WHITELIST):
        return False
    return dur >= MIN_TURN_DURATION_S


def _phrase_in_tail(text: str, tail_chars: int = CLOSING_TAIL_CHARS) -> bool:
    return _contains_closing_phrase((text or "")[-tail_chars:])


class TurnController:
    """See module comment. All methods are pure and return list[(Action, value)]."""

    def __init__(self, monotonic=None):
        self.state = CallState.INITIALIZING
        self.greeting_done = False       # one-time greeting guard (create side)
        self.valid_turns = 0
        self.pending_marks: set[str] = set()
        self._resp_seq = 0               # mark id counter
        self._got_first_delta = False    # per-response first-delta flag
        self._speech_started_at = None
        self._last_segment_dur = 0.0
        self._closing_armed = False
        self._waiting_since = None
        self._reprompted = False
        self._timeout_gen = 0            # M3: generation id for the waiting timer
        self._now = monotonic or time.monotonic

    # — greeting —
    def on_session_updated(self):
        if self.state == CallState.INITIALIZING and not self.greeting_done:
            self.greeting_done = True
            self.state = CallState.GREETING_REQUESTED
            self._got_first_delta = False
            return [(Action.RESPONSE_CREATE, None)]
        return []

    # — response lifecycle —
    def on_response_created(self):
        self._got_first_delta = False
        return []

    def on_output_delta(self):
        # First audio chunk of a response → we are now PLAYING.
        if not self._got_first_delta:
            self._got_first_delta = True
            self.state = (
                CallState.GREETING_PLAYING if self.valid_turns == 0
                else CallState.RESPONDING_PLAYING
            )
        return []

    def on_response_done(self, status: str):
        # Closing phrase (state-guarded) wins.
        if self._closing_armed and status != "cancelled":
            self._closing_armed = False
            self.state = CallState.CLOSING
            return [(Action.HANGUP_GRACE, None)]
        # Cancelled (barge-in) responses played nothing new worth a mark — the
        # Twilio clear already flushed and the new turn is driving the flow.
        if status == "cancelled":
            return []
        # Completed response with audio → send a playback mark; stay *_PLAYING
        # until Twilio echoes it back (the real playback clock, RC2).
        if self.state in _PLAYING_STATES:
            self._resp_seq += 1
            name = f"resp:{self._resp_seq}"
            self.pending_marks.add(name)
            return [(Action.SEND_MARK, name)]
        # Completed without audio (rare) → go straight to a waiting state.
        self._enter_waiting()
        return []

    def on_twilio_mark(self, name: str):
        self.pending_marks.discard(name)
        if not self.pending_marks and self.state in _PLAYING_STATES:
            self._enter_waiting()
        return []

    def _enter_waiting(self):
        self.state = (
            CallState.ACTIVE_CONVERSATION if self.valid_turns >= 1
            else CallState.WAITING_FOR_CALLER
        )
        self._waiting_since = self._now()
        # M3: every fresh waiting interval (greeting mark, or any assistant
        # playback-mark return — including the re-prompt's) arms a NEW timeout
        # generation. Logged by the wiring so a stale generation is detectable.
        self._timeout_gen += 1
        # NOTE: _reprompted is reset ONLY by a genuine caller turn
        # (on_input_transcription) — never here. Otherwise the re-prompt's OWN
        # completion would clear it and the second silence timeout would
        # re-prompt again instead of closing (packet: reprompt once, then close).

    # — caller speech / turns —
    def on_speech_started(self, t: float):
        # NEVER creates or cancels by itself. Only a status marker; must not
        # disturb a PLAYING state (needed for the barge-in decision).
        self._speech_started_at = t
        if self.state in (CallState.WAITING_FOR_CALLER, CallState.ACTIVE_CONVERSATION):
            self.state = CallState.CALLER_SPEAKING
        return []

    def on_speech_stopped(self, t: float):
        if self._speech_started_at is not None:
            self._last_segment_dur = max(0.0, t - self._speech_started_at)
        return []

    def on_input_transcription(self, text: str, dur: float = None):
        d = self._last_segment_dur if dur is None else dur
        # Only a waiting state (fresh turn) or a PLAYING state (barge-in) may
        # accept a caller turn. While a response is generating
        # (ASSISTANT_RESPONDING/PROCESSING) or CLOSING, drop the transcription —
        # this prevents a duplicate response.create for overlapping segments.
        if not (self.state in _WAITING_STATES or self.state in _PLAYING_STATES):
            return []
        if not is_valid_caller_turn(text, d):
            # Junk / noise / echo — revert a bare CALLER_SPEAKING marker.
            if self.state == CallState.CALLER_SPEAKING:
                self.state = (
                    CallState.ACTIVE_CONVERSATION if self.valid_turns >= 1
                    else CallState.WAITING_FOR_CALLER
                )
            return []
        self.valid_turns += 1
        self._reprompted = False
        actions = []
        if self.state in _PLAYING_STATES:
            if d >= BARGE_IN_MIN_DURATION_S:
                self.pending_marks.clear()            # Twilio clear flushes all
                actions.append((Action.CANCEL_AND_CLEAR, None))
            # else: let playback finish; the turn is still created below.
        self.state = CallState.PROCESSING_CALLER_TURN
        actions.append((Action.RESPONSE_CREATE, None))
        self.state = CallState.ASSISTANT_RESPONDING
        self._got_first_delta = False
        return actions

    # — assistant transcript (closing detection) —
    def on_assistant_transcript(self, text: str):
        # Closing hangup allowed ONLY after ≥1 real caller turn AND the phrase is
        # near the end of Maya's line (never mid-conversation false positive).
        if self.valid_turns >= 1 and _phrase_in_tail(text):
            self._closing_armed = True
        return []

    # — waiting watchdog (M3: generation-owned, two-stage) —
    def check_waiting_timeout(self, now: float):
        # Never during CALLER_SPEAKING / PROCESSING / ASSISTANT_RESPONDING /
        # *_PLAYING / CLOSING — a stale generation can never close a later state.
        if self.state not in (CallState.WAITING_FOR_CALLER, CallState.ACTIVE_CONVERSATION):
            return []
        if self._waiting_since is None:
            return []
        # T1 (REPROMPT) before the check-in; T2 (CLOSE) after it. T2 is counted
        # from the re-prompt's playback-mark return (_enter_waiting), NOT from
        # the REPROMPT emission — so the close countdown starts only once the
        # caller has actually heard the check-in.
        threshold = (
            OPENAI_WAITING_CLOSE_SECONDS if self._reprompted
            else OPENAI_WAITING_REPROMPT_SECONDS
        )
        if (now - self._waiting_since) < threshold:
            return []
        gen = self._timeout_gen
        if not self._reprompted:
            self._reprompted = True
            # Leave _waiting_since UNCHANGED: the close countdown must not start
            # until the re-prompt's mark returns and re-arms a fresh interval.
            self.state = CallState.ASSISTANT_RESPONDING
            self._got_first_delta = False
            return [(Action.REPROMPT, gen)]
        self.state = CallState.CLOSING
        return [(Action.HANGUP_GRACE, gen)]


def _name_status(extracted_name, caller_lines: list[str]) -> tuple[str, str]:
    """Post-call name value + status — NEVER a guess (packet §D):
      confirmed     — extracted name AND it appears in ≥1 caller line
      unconfirmed   — extracted name not verifiable in caller lines → "name (לא אומת)"
      not_provided  — no name, clean transcript → "לא נמסר"
      unclear_audio — no name, garbled/empty transcript → "לא זוהה בבירור"
    """
    name = (extracted_name or "").strip()
    if name:
        if any(name in (ln or "") for ln in caller_lines):
            return name, "confirmed"
        return f"{name} (לא אומת)", "unconfirmed"
    fb = _name_fallback(caller_lines)
    return fb, ("not_provided" if fb == "לא נמסר" else "unclear_audio")


# ── Twilio → OpenAI pump (M1.1: testable, exit-guaranteed) ────────────────────

async def _pump_twilio(
    receive_text,
    forward_audio,
    close_openai,
    diag,
    gap_seconds: float = None,
    send_timeout: float = None,
    on_mark=None,
    gap_context=None,
) -> str:
    """
    Pull Twilio frames and forward media payloads to OpenAI. Returns a terminal
    exit-reason string; `close_openai()` is invoked on EVERY exit path (the
    zombie-session fix), so the OpenAI receive loop is always unblocked and the
    handler's single `finally` finalization is guaranteed to run.

    `on_mark(name)` (M2, optional, sync): called for each Twilio `mark` event —
    the playback clock AND heartbeat echoes. All other non-media/non-stop
    events are ignored.

    M3 — MEDIA-ONLY dead-socket detector: the gap is measured strictly from the
    last inbound MEDIA frame. Mark echoes (playback marks AND heartbeat marks)
    are received and dispatched to `on_mark` but do NOT reset the media timer —
    otherwise a live heartbeat echo would mask a real caller-audio stall. This
    is why the loop re-checks the media gap on every iteration rather than
    relying solely on a receive timeout. `gap_context()` (optional) supplies
    extra forensic fields for the dead_socket_gap diag (hb ids/echo age, state).

    Exit reasons:
      twilio_stop            — Twilio sent the normal stop event
      twilio_disconnect      — WS disconnect surfaced (code/reason diag'd)
      twilio_exhausted       — receive ended without stop/disconnect exception
      dead_socket_gap        — no inbound MEDIA frame for gap_seconds (media
                               normally arrives every ~20ms — a gap means the
                               caller-audio path is DEAD, never caller silence)
      openai_send_timeout    — openai_ws.send blocked (backpressure)
      openai_closed          — OpenAI WS closed mid-forward
      error:<...>            — anything else
    """
    gap = OPENAI_INBOUND_GAP_SECONDS if gap_seconds is None else gap_seconds
    tmo = OPENAI_SEND_TIMEOUT_SECONDS if send_timeout is None else send_timeout
    poll = min(gap, 1.0)   # wake at least this often to re-check the media gap
    reason = "twilio_exhausted"
    last_media_ts = time.monotonic()
    try:
        while True:
            # Media-only gap check FIRST — fires even while mark/hb echoes flow.
            media_gap = time.monotonic() - last_media_ts
            if media_gap >= gap:
                reason = "dead_socket_gap"
                fields = {"elapsed_seconds": round(media_gap, 3),
                          "seconds_since_media": round(media_gap, 3),
                          "threshold": gap}
                if gap_context is not None:
                    try:
                        fields.update(gap_context())
                    except Exception:
                        pass
                diag("dead_socket_gap", **fields)
                break
            try:
                raw = await asyncio.wait_for(receive_text(), timeout=poll)
            except asyncio.TimeoutError:
                continue   # re-check the media gap at the top of the loop
            evt = json.loads(raw)
            if evt["event"] == "media":
                last_media_ts = time.monotonic()   # ONLY media resets the timer
                try:
                    await asyncio.wait_for(
                        forward_audio(evt["media"]["payload"]), timeout=tmo
                    )
                except asyncio.TimeoutError:
                    reason = "openai_send_timeout"
                    diag(
                        "openai_send_timeout",
                        operation="input_audio_buffer.append",
                        timeout_seconds=tmo,
                    )
                    break
                except websockets.exceptions.ConnectionClosed as e:
                    reason = "openai_closed"
                    diag("openai_closed_during_send", code=e.code, reason=str(e.reason or ""))
                    break
            elif evt["event"] == "mark":
                # Playback + heartbeat echoes — dispatched, but NEVER reset the
                # media timer (M3 media-only detector).
                if on_mark is not None:
                    on_mark((evt.get("mark") or {}).get("name", ""))
            elif evt["event"] == "stop":
                reason = "twilio_stop"
                break
    except WebSocketDisconnect as e:
        reason = "twilio_disconnect"
        diag("twilio_ws_disconnect", code=e.code, reason=str(getattr(e, "reason", "") or ""))
    except Exception as e:
        reason = f"error:{type(e).__name__}"
        diag("twilio_pump_error", error=str(e)[:300])
    finally:
        try:
            await close_openai()
        except Exception:
            pass
    return reason


# ── WebSocket bridge ──────────────────────────────────────────────────────────

@router.websocket("/stream-openai")
async def stream_openai(twilio_ws: WebSocket, call_sid: str = Query(default="")):
    """
    Bridges a Twilio Media Stream to an OpenAI Realtime (GA) session.

    Audio flow (passthrough, no transcoding):
      Twilio media payload (base64 µ-law 8 kHz) → input_audio_buffer.append
      response.output_audio.delta (base64 µ-law 8 kHz) → Twilio media payload
    """
    await twilio_ws.accept()
    _call_started_at = datetime.utcnow().isoformat()
    print(f"[OPENAI-WS] Twilio connection accepted — call_sid={call_sid!r}")

    if not _OPENAI_API_KEY:
        print("[OPENAI-WS] ERROR: OPENAI_API_KEY is not set — closing stream")
        await twilio_ws.close()
        return

    # ── Wait for the Twilio start event (same pattern as the Gemini path) ─────
    stream_sid: str | None = None
    agent_cfg: dict = {}
    caller_phone = ""
    client_id = None
    client_name = ""
    webhook_url = ""
    try:
        async for raw in twilio_ws.iter_text():
            evt = json.loads(raw)
            if evt["event"] == "start":
                stream_sid = evt["start"]["streamSid"]
                _custom = evt["start"].get("customParameters", {}) or {}
                if not call_sid:
                    call_sid = _custom.get("call_sid") or evt["start"].get("callSid", "")
                print(f"[OPENAI-WS] Start event — stream_sid={stream_sid} call_sid={call_sid!r} custom_keys={list(_custom.keys())}")
                # Durable handoff — identical resolution to the Gemini path.
                _resolved    = await _resolve_gemini_context(_custom, call_sid)
                agent_cfg    = _resolved["agent_cfg"]
                caller_phone = _resolved["caller_phone"]
                client_id    = _resolved["client_id"]
                client_name  = _resolved["client_name"]
                webhook_url  = agent_cfg.get("webhook_url", "")
                print(f"[OPENAI-WS] context source={_resolved['source']} caller={caller_phone} client='{client_name}' webhook={'yes' if webhook_url else 'no'}")
                break
            # Pre-start media is ignored (ringback/noise); OpenAI VAD starts
            # fresh once real audio flows after session setup.
    except Exception as e:
        print(f"[OPENAI-WS] ERROR waiting for start event: {e}")
        await twilio_ws.close()
        return

    # Fail closed — same defense-in-depth contract as the Gemini path.
    if agent_cfg.get("fallback_used") or not agent_cfg.get("prompt_override"):
        print(f"[OPENAI-WS] ❌ No active agent prompt for client='{client_name}' — closing (fail closed)")
        try:
            await twilio_ws.close()
        except Exception:
            pass
        return

    # ── Prompt: same Roi system prompt + natural one-time opening (M1.1) ──────
    base_prompt = agent_cfg["prompt_override"].replace("{{caller_phone}}", caller_phone)
    first_message = (agent_cfg.get("first_message") or "").strip()
    system_instruction = _openai_opening_instruction(base_prompt, first_message)
    system_instruction += _NAME_PROTOCOL_INSTRUCTION
    if first_message:
        print("[OPENAI-WS] natural one-time opening instruction injected into system prompt")

    # ── Connect to OpenAI Realtime (GA) ──────────────────────────────────────
    # NOTE: default ping_interval kept ON (WS keepalive) — unlike the Gemini
    # path, half-open sockets are detected at the protocol level.
    openai_url = _OPENAI_WS_URL.format(model=OPENAI_REALTIME_MODEL)
    try:
        openai_ws = await websockets.connect(
            openai_url,
            additional_headers={"Authorization": f"Bearer {_OPENAI_API_KEY}"},
        )
        print(f"[OPENAI-WS] OpenAI Realtime connected — model={OPENAI_REALTIME_MODEL}")
    except Exception as e:
        print(f"[OPENAI-WS] ERROR: could not connect to OpenAI Realtime: {e}")
        await twilio_ws.close()
        return

    try:
        await openai_ws.send(json.dumps(_build_session_update(system_instruction)))
    except Exception as e:
        print(f"[OPENAI-WS] ERROR sending session.update: {e}")
        try:
            await openai_ws.close()
        except Exception:
            pass
        await twilio_ws.close()
        return

    # ── Shared state ──────────────────────────────────────────────────────────
    _caller_lines: list[str] = []      # caller speech only (input transcription)
    _assistant_lines: list[str] = []   # assistant speech only (output transcript)
    _response_first_audio_logged = False
    _ctrl = TurnController()

    # ── Action executor — the ONLY place I/O side-effects happen ─────────────
    # Every response.create in this module is sent from here (RESPONSE_CREATE /
    # REPROMPT), so the "app owns response creation" invariant is grep-checkable.
    async def _send_response_create(instructions: str = None):
        payload = {"type": "response.create"}
        if instructions:
            payload["response"] = {"instructions": instructions}
        await openai_ws.send(json.dumps(payload))

    async def _execute(actions) -> bool:
        """Run controller actions. Returns True if the session should terminate."""
        terminal = False
        for act, val in actions:
            if act == Action.RESPONSE_CREATE:
                await _send_response_create()
                _diag("response_create_sent", call_sid, reason="valid_turn_or_greeting")
            elif act == Action.REPROMPT:
                await _send_response_create(_REPROMPT_INSTRUCTION)
                _diag("reprompt_sent", call_sid, gen=val)
            elif act == Action.CANCEL_AND_CLEAR:
                await openai_ws.send(json.dumps({"type": "response.cancel"}))
                if stream_sid:
                    await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                _diag("barge_in_cancel_and_clear", call_sid)
            elif act == Action.SEND_MARK:
                if stream_sid:
                    await twilio_ws.send_json({
                        "event": "mark", "streamSid": stream_sid,
                        "mark": {"name": val},
                    })
                _diag("playback_mark_sent", call_sid, mark=val)
            elif act == Action.HANGUP_GRACE:
                _diag("closing_hangup", call_sid, state=_ctrl.state.value, gen=val)
                await asyncio.sleep(CLOSING_GRACE_SECONDS)
                try:
                    await openai_ws.close()
                except Exception:
                    pass
                terminal = True
        return terminal

    # ── Twilio → OpenAI (µ-law passthrough via exit-guaranteed pump) ─────────
    async def _forward_audio(payload: str):
        # Twilio payload is already base64 µ-law — append verbatim.
        await openai_ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": payload,
        }))

    # ── Transport heartbeat state (M3) — diagnostics only ────────────────────
    _hb = {"seq": 0, "sent_id": "", "ack_id": "", "echo_ts": None}

    def _on_twilio_mark(name: str):
        # M3: route marks. Heartbeat echoes ("hb:…") are pure transport
        # diagnostics — they NEVER touch the TurnController, NEVER count as
        # playback completion, NEVER reset caller timers. Response playback
        # marks ("resp:…") drive the RC2 playback clock as before.
        if name.startswith(_HEARTBEAT_MARK_PREFIX):
            _hb["ack_id"] = name
            _hb["echo_ts"] = time.monotonic()
            _diag("heartbeat_returned", call_sid, hb=name)
            return
        _ctrl.on_twilio_mark(name)
        _diag("playback_mark_returned", call_sid, mark=name, state=_ctrl.state.value)
        # A returned playback mark may have re-armed a fresh waiting generation.
        if _ctrl.state in (CallState.WAITING_FOR_CALLER, CallState.ACTIVE_CONVERSATION):
            _diag("waiting_armed", call_sid, gen=_ctrl._timeout_gen,
                  state=_ctrl.state.value,
                  timeout=(OPENAI_WAITING_CLOSE_SECONDS if _ctrl._reprompted
                           else OPENAI_WAITING_REPROMPT_SECONDS))

    def _gap_context():
        # Forensic fields attached to a dead_socket_gap diag (media-vs-hb
        # divergence tells Twilio-side vs proxy-side stall apart).
        now = time.monotonic()
        echo_age = None if _hb["echo_ts"] is None else round(now - _hb["echo_ts"], 3)
        return {
            "stream_sid": stream_sid,
            "seconds_since_hb_echo": echo_age,
            "last_hb_sent": _hb["sent_id"],
            "last_hb_ack": _hb["ack_id"],
            "state": _ctrl.state.value,
            "caller_active": _ctrl.state in (CallState.CALLER_SPEAKING,
                                             CallState.PROCESSING_CALLER_TURN),
            "assistant_active": _ctrl.state in (CallState.GREETING_REQUESTED,
                                                CallState.GREETING_PLAYING,
                                                CallState.ASSISTANT_RESPONDING,
                                                CallState.RESPONDING_PLAYING),
        }

    async def twilio_to_openai_loop():
        exit_reason = await _pump_twilio(
            receive_text=twilio_ws.receive_text,
            forward_audio=_forward_audio,
            close_openai=openai_ws.close,
            diag=lambda event, **kw: _diag(event, call_sid, **kw),
            on_mark=_on_twilio_mark,
            gap_context=_gap_context,
        )
        print(f"[OPENAI-WS] Twilio pump exited — reason={exit_reason}")

    # ── Heartbeat task (M3): send hb marks every N s while the stream is up ──
    async def heartbeat_loop():
        try:
            while True:
                await asyncio.sleep(OPENAI_HEARTBEAT_SECONDS)
                if not stream_sid:
                    continue
                _hb["seq"] += 1
                name = f"{_HEARTBEAT_MARK_PREFIX}{_hb['seq']}"
                _hb["sent_id"] = name
                try:
                    await twilio_ws.send_json({
                        "event": "mark", "streamSid": stream_sid,
                        "mark": {"name": name},
                    })
                    _diag("heartbeat_sent", call_sid, hb=name)
                except Exception as e:
                    _diag("heartbeat_send_failed", call_sid, error=str(e)[:200])
                    return
        except asyncio.CancelledError:
            return
        except Exception as e:
            _diag("heartbeat_loop_error", call_sid, error=str(e)[:200])

    # ── OpenAI → Twilio (controller-driven) ──────────────────────────────────
    async def openai_to_twilio_loop():
        nonlocal _response_first_audio_logged
        try:
            async for raw in openai_ws:
                event = json.loads(raw)
                etype = event.get("type", "")

                if etype == "session.created":
                    _diag("session_created", call_sid, model=OPENAI_REALTIME_MODEL)

                elif etype == "session.updated":
                    # One-time greeting: the controller emits RESPONSE_CREATE
                    # exactly once (greeting_done guard). No caller-text trigger.
                    acts = _ctrl.on_session_updated()
                    if acts:
                        _diag("greeting_response_created", call_sid)
                        await _execute(acts)

                elif etype == "input_audio_buffer.speech_started":
                    _ctrl.on_speech_started(time.monotonic())
                    _diag("speech_started", call_sid, state=_ctrl.state.value)
                    # NOTE: bare speech_started never cancels/clears (RC1/RC2).

                elif etype == "input_audio_buffer.speech_stopped":
                    _ctrl.on_speech_stopped(time.monotonic())
                    _diag("speech_stopped", call_sid)

                elif etype == "conversation.item.input_audio_transcription.completed":
                    _text = (event.get("transcript") or "").strip()
                    if _text:
                        _caller_lines.append(_text)
                    acts = _ctrl.on_input_transcription(_text)
                    _diag("input_transcription", call_sid, text=_text,
                          valid_turn=bool(acts), state=_ctrl.state.value)
                    if acts:
                        if await _execute(acts):
                            break

                elif etype == "response.created":
                    _ctrl.on_response_created()
                    _response_first_audio_logged = False
                    _diag("response_created", call_sid)

                elif etype == "response.output_audio.delta":
                    delta = event.get("delta", "")
                    if delta and stream_sid:
                        _ctrl.on_output_delta()
                        if not _response_first_audio_logged:
                            _response_first_audio_logged = True
                            _diag("first_outbound_audio", call_sid)
                        # µ-law passthrough — forward the base64 verbatim.
                        await twilio_ws.send_json({
                            "event":     "media",
                            "streamSid": stream_sid,
                            "media":     {"payload": delta},
                        })

                elif etype == "response.output_audio_transcript.done":
                    _text = (event.get("transcript") or "").strip()
                    if _text:
                        _assistant_lines.append(_text)
                        _ctrl.on_assistant_transcript(_text)

                elif etype == "response.done":
                    _status = (event.get("response") or {}).get("status", "")
                    _diag("response_completed", call_sid, status=_status, state=_ctrl.state.value)
                    if _status == "cancelled":
                        _diag("response_cancelled", call_sid)
                    acts = _ctrl.on_response_done(_status)
                    if acts:
                        if await _execute(acts):
                            break

                elif etype == "error":
                    _diag("openai_error", call_sid, error=str(event.get("error", ""))[:300])

        except websockets.exceptions.ConnectionClosed as e:
            _diag("ws_closed", call_sid, code=e.code, reason=str(e.reason or ""))
        except Exception as e:
            _diag("openai_receiver_error", call_sid, error=str(e)[:300])

    # ── WAITING watchdog: silence after greeting → one re-prompt, then close ──
    async def waiting_watchdog():
        try:
            while True:
                await asyncio.sleep(1.0)
                acts = _ctrl.check_waiting_timeout(time.monotonic())
                if acts:
                    await _execute(acts)
        except asyncio.CancelledError:
            return
        except Exception as e:
            _diag("waiting_watchdog_error", call_sid, error=str(e)[:200])

    _watchdog_task = asyncio.create_task(waiting_watchdog())
    _heartbeat_task = asyncio.create_task(heartbeat_loop())

    # ── Run both loops, then the shared post-call pipeline ────────────────────
    try:
        await asyncio.gather(twilio_to_openai_loop(), openai_to_twilio_loop())
    finally:
        # Cancel the background tasks first so no orphan survives the session.
        for _t in (_watchdog_task, _heartbeat_task):
            _t.cancel()
            try:
                await _t
            except (asyncio.CancelledError, Exception):
                pass
        _diag(
            "session_ended", call_sid,
            caller_lines=len(_caller_lines), assistant_lines=len(_assistant_lines),
        )
        print("[OPENAI-WS] Session ended — running end-of-call business logic")

        # Extraction — customer lines ONLY (never assistant speech).
        extracted: dict = {}
        transcript_text = _customer_transcript(_caller_lines)
        if transcript_text.strip():
            print(f"[OPENAI-EXTRACT] Customer-only transcript ({len(_caller_lines)} lines) — running extraction")
            extracted = await _extract_lead_from_transcript(transcript_text, caller_phone)
            print(f"[OPENAI-EXTRACT] Result: {extracted}")
        else:
            print("[OPENAI-EXTRACT] No customer transcript captured — skipping extraction")

        # Name for the email + status — NEVER a guess (M2, packet §D):
        #   confirmed / unconfirmed / not_provided ("לא נמסר") / unclear_audio
        #   ("לא זוהה בבירור"). A name only "confirmed" if it appears in a
        #   caller line; otherwise it is suffixed "(לא אומת)".
        _email_name, _name_stat = _name_status(extracted.get("name"), _caller_lines)
        print(f"[OPENAI-NAME] status={_name_stat} email_name={_email_name!r}")

        # Real 2–3 sentence Hebrew summary from BOTH speakers (roles tagged).
        # RC3 guard: only names that actually appear in caller lines may be
        # attributed to the caller — a name spoken only by Maya must never leak.
        _confirmed_name = extracted.get("name") if _name_stat == "confirmed" else None
        _allowed_names = [_confirmed_name] if _confirmed_name else []
        _full_text = _full_transcript(_caller_lines, _assistant_lines)
        _excerpt   = _transcript_excerpt(_caller_lines, _assistant_lines)
        _summary   = (
            await _summarize_transcript(_full_text, caller_names_allowed=_allowed_names)
            if _full_text.strip() else ""
        )
        print(f"[OPENAI-SUMMARY] {(_summary or '(empty)')[:200]}")

        # Lead persistence — same fields/contract as the Gemini path.
        _appt_day  = extracted.get("appointment_day") or ""
        _appt_time = extracted.get("appointment_time") or ""
        _appointment_at = _compute_appointment_at(_appt_day, _appt_time)
        if caller_phone:
            _topic = extracted.get("topic") or None
            _notes = extracted.get("notes") or None
            _summary_parts = []
            if _topic:
                _summary_parts.append(f"נושא: {_topic}")
            if _notes:
                _summary_parts.append(f"פרטים: {_notes}")
            # Prefer the real conversation summary; legacy topic|notes as backup.
            _last_call_summary = _summary or (" | ".join(_summary_parts) or None)

            await save_lead({
                "phone":             caller_phone,
                "source":            "voice",
                "status":            "new",
                "client_id":         client_id,
                "name":              extracted.get("name") or None,
                "notes":             _notes,
                "last_call_summary": _last_call_summary,
                "last_call_topic":   _topic,
                "last_call_at":      datetime.utcnow().isoformat(),
                "appointment_at":    _appointment_at,
            })
            print(f"[OPENAI-LEAD] ✅ Lead upserted — phone={caller_phone} name={extracted.get('name')} client_id={client_id}")
        else:
            print("[OPENAI-LEAD] ⚠️  No caller phone available — lead not saved")

        # Webhook — SAME payload shape as the Gemini path (Make scenario
        # unchanged); source distinguishes the A/B arm.
        if caller_phone and webhook_url:
            _booking_status = "booked" if _appointment_at else "not_booked"
            _history = await _get_customer_history(caller_phone, _call_started_at)
            print(
                f"[OPENAI-HISTORY] status={_history['customer_status']} "
                f"prior_count={_history['prior_count']} last_date={_history['last_date']}"
            )
            webhook_payload = {
                "timestamp":             datetime.now().isoformat(),
                "source":                "voice_openai",
                "client":                client_name,
                "caller_phone":          caller_phone,
                "call_sid":              call_sid,
                "name":                  _email_name,
                "name_status":           _name_stat,
                "phone_number":          extracted.get("phone_number") or caller_phone,
                "topic":                 extracted.get("topic", ""),
                "notes":                 extracted.get("notes", ""),
                # M1.1: real conversation summary + raw excerpt fallback
                "summary":               _summary,
                "transcript_excerpt":    _excerpt,
                "appointment_day":       _appt_day,
                "appointment_time":      _appt_time,
                "appointment_at":        _appointment_at or "",
                "booking_status":        _booking_status,
                "followup_target_phone": caller_phone,
                "customer_status":       _history["customer_status"],
                "prior_count":           _history["prior_count"],
                "last_date":             _history["last_date"] or "",
            }
            await _send_voice_webhook(webhook_url, webhook_payload)
        elif not webhook_url:
            print("[OPENAI-WEBHOOK] ⚠️  No webhook URL in agent config — skipping")

        # REST hangup — closing the WS alone does not always end the call.
        if call_sid:
            try:
                twilio_client = _get_twilio_client()
                await asyncio.to_thread(
                    lambda: twilio_client.calls(call_sid).update(status="completed")
                )
                print(f"[OPENAI-HANGUP] ✅ Twilio call {call_sid} terminated via REST API")
            except Exception as exc:
                print(f"[OPENAI-HANGUP] ⚠️  Could not terminate call via REST: {exc}")

        _GEMINI_CALL_CONTEXT.pop(call_sid, None)

        try:
            await openai_ws.close()
        except Exception:
            pass
        try:
            await twilio_ws.close()
        except Exception:
            pass

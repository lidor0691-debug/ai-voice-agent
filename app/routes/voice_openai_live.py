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
import base64
import html
import json
import os
import re
import time
from collections import deque
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
from app.services.voice_shared import two_stage_greeting_enabled as _two_stage_greeting_enabled
from app.services.voice_shared import onset_barge_enabled as _onset_barge_enabled
from app.services.voice_shared import echo_guard_mode as _echo_guard_mode
from app.services.voice_shared import dialogue_style_enabled as _dialogue_style_enabled
from app.services.voice_shared import resolve_two_stage_office as _resolve_two_stage_office
from app.services.voice_shared import GENERIC_OFFICE_LABEL as _GENERIC_OFFICE_LABEL
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

# ── Vocal pace (M5) ───────────────────────────────────────────────────────────
# Native GA control `session.audio.output.speed` (live-probe verified on
# gpt-realtime-2.1). Scales DELIVERY pace only — it does not change wording,
# sentence structure, warmth, VAD, silence thresholds, interruption logic, or
# the state machine. Default 1.0 keeps deployment behavior-neutral; the pilot
# value (≈+6%) is set via the environment, so rollback = unset the variable.
# Deliberately NO prompt instruction about speed (native control only).
OPENAI_REALTIME_SPEED_DEFAULT = 1.0
OPENAI_REALTIME_SPEED_MIN = 0.7   # conservative guard: blocks typos like "0.06"
OPENAI_REALTIME_SPEED_MAX = 1.3   # conservative guard: blocks typos like "10.6"


def _parse_realtime_speed(raw, default: float = OPENAI_REALTIME_SPEED_DEFAULT) -> float:
    """Pure/testable. Return a safe speed within the conservative range.
    Unset, unparsable, NaN/inf, or out-of-range values fall back to `default`
    (1.0) with a non-secret warning. Never raises."""
    s = (raw or "").strip()
    if not s:
        return default
    try:
        value = float(s)
    except (TypeError, ValueError):
        print(f"[OPENAI-CONFIG] ⚠️ invalid OPENAI_REALTIME_SPEED={s!r} — using {default}")
        return default
    # NaN fails both comparisons, so it falls back too.
    if not (OPENAI_REALTIME_SPEED_MIN <= value <= OPENAI_REALTIME_SPEED_MAX):
        print(
            f"[OPENAI-CONFIG] ⚠️ OPENAI_REALTIME_SPEED={value} outside "
            f"[{OPENAI_REALTIME_SPEED_MIN}, {OPENAI_REALTIME_SPEED_MAX}] — using {default}"
        )
        return default
    return value


OPENAI_REALTIME_SPEED = _parse_realtime_speed(os.getenv("OPENAI_REALTIME_SPEED"))

# Streaming STT model for caller-side transcription (must be enabled explicitly
# in the GA session config; feeds the caller transcript buffer).
OPENAI_REALTIME_TRANSCRIBE_MODEL = os.getenv(
    "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-realtime-whisper"
).strip()

# ── Conversation-quality knobs (M7) ───────────────────────────────────────────
# Hebrew phone quality is a calibration problem, and every calibration round
# costs a live call. These knobs are therefore environment-driven: tuning a
# value is a variable change, not a deploy.
#
# INVARIANT: every knob below is ABSENT from the payload unless explicitly set,
# and the VAD numbers default to the exact M2 values. An unset environment
# therefore reproduces the M6 session byte-for-byte — verified by test.
#
# All four session fields were live-probe verified against gpt-realtime-2.1
# (accepted and echoed back in session.updated) before this code was written.

def _coerce_setting_text(raw) -> str:
    """Pure. Normalise any settings value to trimmed text. Callers pass
    os.getenv() results (str|None), but staying total means a non-string can
    never turn a config typo into a crash at import time."""
    if raw is None:
        return ""
    return (raw if isinstance(raw, str) else str(raw)).strip()


def _parse_bounded_float(raw, lo: float, hi: float, default, name: str):
    """Pure/testable. Parse an optional bounded float. Unset/invalid/NaN/
    out-of-range → `default` (with a non-secret warning). Never raises."""
    s = _coerce_setting_text(raw)
    if not s:
        return default
    try:
        value = float(s)
    except (TypeError, ValueError):
        print(f"[OPENAI-CONFIG] ⚠️ invalid {name}={s!r} — using {default}")
        return default
    if not (lo <= value <= hi):  # NaN fails both comparisons → falls back too
        print(f"[OPENAI-CONFIG] ⚠️ {name}={value} outside [{lo}, {hi}] — using {default}")
        return default
    return value


def _parse_bounded_int(raw, lo: int, hi: int, default, name: str):
    """Pure/testable. Parse an optional bounded int. Unset/invalid/out-of-range
    → `default` (with a non-secret warning). Never raises."""
    s = _coerce_setting_text(raw)
    if not s:
        return default
    try:
        value = int(s)
    except (TypeError, ValueError):
        print(f"[OPENAI-CONFIG] ⚠️ invalid {name}={s!r} — using {default}")
        return default
    if not (lo <= value <= hi):
        print(f"[OPENAI-CONFIG] ⚠️ {name}={value} outside [{lo}, {hi}] — using {default}")
        return default
    return value


# Vocabulary hint for the streaming STT. Israeli names and insurance terms are
# exactly what a general-purpose model mangles on a narrowband line; a domain
# prompt is the documented lever for it. Empty → field omitted entirely.
OPENAI_TRANSCRIBE_PROMPT = os.getenv("OPENAI_TRANSCRIBE_PROMPT", "").strip()

# Input noise reduction. A PSTN call is a near-field source (handset/headset),
# so "near_field" is the matching profile; "far_field" suits speakerphone.
# Anything else (including unset) → field omitted, i.e. no noise reduction.
_NOISE_REDUCTION_VALID = ("near_field", "far_field")
OPENAI_INPUT_NOISE_REDUCTION = os.getenv("OPENAI_INPUT_NOISE_REDUCTION", "").strip().lower()

# Hard ceiling on one spoken reply. This is a SAFETY NET, not a brevity tool:
# hitting it ends the response as "incomplete", i.e. audio stops mid-sentence.
# Brevity belongs in the instruction below; set this only high enough to stop a
# runaway monologue. Unset → no cap (API default).
OPENAI_MAX_OUTPUT_TOKENS = _parse_bounded_int(
    os.getenv("OPENAI_MAX_OUTPUT_TOKENS"), 64, 4096, None, "OPENAI_MAX_OUTPUT_TOKENS"
)

# Turn detection. Defaults are the exact M2-tuned server_vad values, so unset
# == today's behavior. `semantic_vad` swaps the fixed silence timer for a
# model-side end-of-turn judgement and takes `eagerness` instead of the three
# numeric fields — useful when a caller pauses mid-thought (very common in
# Hebrew speech) and the fixed timer cuts them off.
_VAD_VALID_EAGERNESS = ("low", "medium", "high", "auto")
OPENAI_VAD_TYPE = os.getenv("OPENAI_VAD_TYPE", "server_vad").strip().lower()
OPENAI_VAD_EAGERNESS = os.getenv("OPENAI_VAD_EAGERNESS", "medium").strip().lower()
OPENAI_VAD_THRESHOLD = _parse_bounded_float(
    os.getenv("OPENAI_VAD_THRESHOLD"), 0.1, 0.95, 0.6, "OPENAI_VAD_THRESHOLD"
)
OPENAI_VAD_SILENCE_MS = _parse_bounded_int(
    os.getenv("OPENAI_VAD_SILENCE_MS"), 200, 2000, 700, "OPENAI_VAD_SILENCE_MS"
)
OPENAI_VAD_PREFIX_MS = _parse_bounded_int(
    os.getenv("OPENAI_VAD_PREFIX_MS"), 0, 1000, 300, "OPENAI_VAD_PREFIX_MS"
)


def _build_turn_detection() -> dict:
    """Pure/testable. Turn-detection block for session.update.

    App-owned turn-taking is non-negotiable in BOTH modes: create_response and
    interrupt_response stay False so the server can never spawn or cancel a
    reply behind the TurnController's back (M2/RC1 invariant).
    """
    if OPENAI_VAD_TYPE == "semantic_vad":
        eagerness = (
            OPENAI_VAD_EAGERNESS if OPENAI_VAD_EAGERNESS in _VAD_VALID_EAGERNESS else "medium"
        )
        return {
            "type": "semantic_vad",
            "eagerness": eagerness,
            "create_response": False,
            "interrupt_response": False,
        }
    return {
        "type": "server_vad",
        "threshold": OPENAI_VAD_THRESHOLD,
        "prefix_padding_ms": OPENAI_VAD_PREFIX_MS,
        "silence_duration_ms": OPENAI_VAD_SILENCE_MS,
        "create_response": False,
        "interrupt_response": False,
    }


def _build_input_transcription() -> dict:
    """Pure/testable. Caller-side STT block. `language` stays pinned to Hebrew
    (M1.1); the newer transcribe models normalise it into `languages` server
    side. The vocabulary prompt is omitted unless configured."""
    block = {"model": OPENAI_REALTIME_TRANSCRIBE_MODEL, "language": "he"}
    if OPENAI_TRANSCRIBE_PROMPT:
        block["prompt"] = OPENAI_TRANSCRIBE_PROMPT
    return block


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
      prefix_padding 300ms, silence 700ms. M7 makes these env-tunable and adds
      an opt-in semantic_vad mode; the defaults are the M2 values, so an unset
      environment produces the identical payload.
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
    audio_input = {
        "format": {"type": "audio/pcmu"},
        "transcription": _build_input_transcription(),
        "turn_detection": _build_turn_detection(),
    }
    # M7: omitted unless configured, so an unset environment is byte-identical.
    if OPENAI_INPUT_NOISE_REDUCTION in _NOISE_REDUCTION_VALID:
        audio_input["noise_reduction"] = {"type": OPENAI_INPUT_NOISE_REDUCTION}

    session = {
        "type": "realtime",
        "output_modalities": ["audio"],
        "instructions": system_instruction,
        "audio": {
            "input": audio_input,
            "output": {
                "format": {"type": "audio/pcmu"},
                "voice": OPENAI_REALTIME_VOICE,
                # M5: native delivery pace. 1.0 = unchanged (API default).
                "speed": OPENAI_REALTIME_SPEED,
            },
        },
    }
    if OPENAI_MAX_OUTPUT_TOKENS is not None:
        session["max_output_tokens"] = OPENAI_MAX_OUTPUT_TOKENS

    return {"type": "session.update", "session": session}


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

# Dialogue discipline (M7): turn-level conversational rules, appended only for
# allowlisted tenants (voice_shared.dialogue_style_enabled). Deliberately
# minimal and behavioral — it constrains TURN SHAPE (length, one question,
# handling a correction, when it is allowed to close) and says nothing about
# tone, wording, or the tenant's own business logic, so it composes with any
# tenant prompt instead of competing with it.
#
# Each rule traces to an observed failure in a recorded call:
#   1-2  6-11s monologues; several questions bundled into one breath.
#   3    the full closing script spoken verbatim twice in one 56s call.
#   4    caller corrected a misheard topic; the model smoothed over it and the
#        wrong value still reached the lead email.
#   5    the model raced into the closing script (and a hangup) while the caller
#        was still objecting.
_DIALOGUE_STYLE_INSTRUCTION = (
    "\n\nניהול תור דיבור: "
    "עני קצר — משפט אחד, שניים לכל היותר, ואז עצרי והקשיבי. "
    "שאלה אחת בלבד בכל תור; אל תאגדי כמה שאלות יחד. "
    "אל תחזרי על מה שכבר אמרת ואל תסכמי את השיחה שוב אלא אם ביקשו ממך. "
    "אם הפונה מתקן אותך או שולל משהו שאמרת — אמצי מיד את הגרסה שלו, "
    "אל תתווכחי ואל תחזרי על הגרסה השגויה. "
    "אל תעברי לסיום השיחה כל עוד הפונה מדבר, מתקן, או שאל שאלה שלא נענתה."
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


# ── Chronological transcript rendering for the email (M5) ────────────────────
# The stored buffers (_caller_lines / _assistant_lines) are grouped BY ROLE, so
# `_full_transcript` / `transcript_excerpt` genuinely lose chronology. M5 adds a
# separate, additive per-call turn list captured in true event order and renders
# it as RTL-safe HTML for Gmail. Raw buffers, the excerpt, extraction, name
# status and the summary are all UNCHANGED — this is presentation only.

# A phone-ish run: optional +, then digits/dashes/spaces/parens, digit-terminated.
_PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{6,}\d)")

TRANSCRIPT_HTML_MAX_TURNS = 20
TRANSCRIPT_HTML_MAX_CHARS = 2500


def _bidi_phone_spans(escaped_text: str) -> str:
    """Isolate phone-like runs as LTR so they never render reversed inside RTL
    Hebrew. Must run AFTER HTML-escaping (it only matches digit-ish runs)."""
    return _PHONE_RE.sub(r'<span dir="ltr">\1</span>', escaped_text)


def _transcript_html(
    turns,
    max_turns: int = TRANSCRIPT_HTML_MAX_TURNS,
    max_chars: int = TRANSCRIPT_HTML_MAX_CHARS,
) -> str:
    """Render chronological turns as RTL-safe Gmail HTML.

    Pure and total: returns "" on empty or malformed input so the Make template
    falls back to the existing raw `transcript_excerpt` (never worse than today).
    Order is preserved exactly as captured — nothing is reordered or inferred.
    """
    try:
        items = [t for t in (turns or []) if (t.get("text") or "").strip()]
        if not items:
            return ""

        def build(count: int) -> str:
            blocks = []
            for turn in items[:count]:
                body = html.escape(turn["text"], quote=False)
                body = _bidi_phone_spans(body)
                body = body.replace("\n", "<br>")
                blocks.append(
                    '<div style="margin-bottom:12px;">'
                    f'<div><strong>{html.escape(turn["role"], quote=False)}</strong></div>'
                    f'<div dir="auto" style="unicode-bidi:plaintext;">{body}</div>'
                    "</div>"
                )
            out = (
                '<div dir="rtl" style="direction:rtl;text-align:right;">'
                + "".join(blocks)
                + "</div>"
            )
            if len(items) > count:
                out += '<div dir="rtl" style="direction:rtl;text-align:right;">…</div>'
            return out

        count = min(len(items), max_turns)
        rendered = build(count)
        # Trim from the END only (never reorder, never slice mid-tag).
        while count > 1 and len(rendered) > max_chars:
            count -= 1
            rendered = build(count)
        return rendered if len(rendered) <= max_chars else ""
    except Exception as exc:
        print(f"[OPENAI-TRANSCRIPT] ⚠️ transcript_html build failed: {exc}")
        return ""


def _customer_transcript(caller_lines: list[str]) -> str:
    """Customer-only text for lead extraction — assistant speech NEVER included
    (prevents extracting a name the assistant said)."""
    return "\n".join(f"לקוח: {ln}" for ln in caller_lines if (ln or "").strip())


# Deterministic, truthful summary for a call with NO valid caller content.
# Incident 2026-07-21: when the transcript held only Maya's greeting, the LLM
# summarizer fabricated an imaginary caller request + Maya reply. If the caller
# contributed nothing clear, we skip the summarizer entirely and use this.
_EMPTY_CALLER_SUMMARY = (
    "לא התקבל מהלקוח תוכן ברור שניתן לסכם. "
    "ייתכן שהשיחה נותקה או שהדיבור לא תומלל."
)


def _has_valid_caller_content(caller_lines) -> bool:
    """True iff at least one caller line has non-empty content after stripping.
    Empty / whitespace-only lines never count as caller content — the guard that
    decides whether the summary LLM may run at all."""
    return any((ln or "").strip() for ln in (caller_lines or []))


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
    BARGED_LISTENING      = "BARGED_LISTENING"       # onset-yielded; awaiting transcript
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
    SPEAK_SCRIPTED   = "SPEAK_SCRIPTED"   # value = per-response instruction (M6)
    ARM_ONSET_GUARD  = "ARM_ONSET_GUARD"  # value = speech_started monotonic ts (barge-in)


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


# ── Greeting-protection gate (M4) ─────────────────────────────────────────────
# Incident (calls 3–4 of the M3 acceptance): line noise/echo during greeting
# playback was transcribed by the Hebrew-pinned STT as plausible SHORT Hebrew
# ("תודה" @1.10s, "רק נשמע" @2.16s). Those passed the generic turn gate, were
# treated as verified barge-ins, truncated the greeting, and seeded a response
# with a content-free caller turn — so the model answered from the business
# prompt ("איזה ביטוח?"). During GREETING_PLAYING ONLY, an interruption must
# therefore clear a HIGHER bar: real length + real duration + not a bare
# pleasantry. Anything weaker is HELD (silently ignored, greeting continues).
GREETING_BARGE_MIN_CHARS = 10     # stripped length
GREETING_BARGE_MIN_DUR_S = 1.2    # sustained speech, not a blip
_GREETING_FRAGMENT_STOPLIST = {
    "תודה", "תודה רבה", "שלום", "היי", "הלו", "כן", "לא", "אוקיי", "סבבה", "בסדר",
}


def is_verified_greeting_interruption(text: str, dur: float) -> bool:
    """True only for a caller turn strong enough to justify cutting the greeting
    off. Callers of this must already have passed `is_valid_caller_turn`."""
    t = (text or "").strip()
    if t in _GREETING_FRAGMENT_STOPLIST:
        return False
    if len(t) < GREETING_BARGE_MIN_CHARS:
        return False
    return dur >= GREETING_BARGE_MIN_DUR_S


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


# ── Two-stage phone greeting (M6) ─────────────────────────────────────────────
# Roi-only (client-allowlisted in voice_shared). The opening is delivered as two
# human turns instead of one recorded-sounding line, so a caller is less likely
# to assume voicemail and hang up:
#   Stage 1  → a short "הלו?" (SPEAK_SCRIPTED), then wait for a real response.
#   Stage 2  → self-identification, chosen by what the caller actually said:
#              • only greeted / acknowledged / identity-checked → a FIXED question
#              • already gave substantive content → a normal model reply prefixed
#                with a brief self-intro (never re-asks the reason).
#   Fallback → if ~1.7s pass after "הלו?" with no accepted caller turn, Stage 2
#              (a warm fixed line) fires automatically via a one-shot task.
# `stage2_done` is the single guard, so Stage 2 can never play twice. With the
# client NOT allowlisted (two_stage=False) the controller is byte-identical to
# the M2–M5 single-greeting flow.
# Default tuned 1.7 → 0.6 from Roi production data (Aug 2026): 94% of callers
# stay silent through this beat, so the fallback fired on nearly every call and
# the old 1.7s created ~2.3s of dead air after "הלו?" before the identity line.
OPENAI_GREETING_STAGE2_FALLBACK_DEFAULT = 0.6
OPENAI_GREETING_STAGE2_FALLBACK_MIN = 0.4   # floor still avoids a hot-mic re-trigger
OPENAI_GREETING_STAGE2_FALLBACK_MAX = 3.0   # a longer silence is the WAITING job


def _parse_stage2_fallback_seconds(raw, default: float = OPENAI_GREETING_STAGE2_FALLBACK_DEFAULT) -> float:
    """Pure/testable. Post-"הלו?" fallback delay, within a conservative range.
    Unset, unparsable, NaN/inf, or out-of-range → `default` (0.6) with a
    non-secret warning. Never raises. (Mirrors _parse_realtime_speed.)"""
    s = (raw or "").strip()
    if not s:
        return default
    try:
        value = float(s)
    except (TypeError, ValueError):
        print(f"[OPENAI-CONFIG] ⚠️ invalid OPENAI_GREETING_STAGE2_FALLBACK_S={s!r} — using {default}")
        return default
    if not (OPENAI_GREETING_STAGE2_FALLBACK_MIN <= value <= OPENAI_GREETING_STAGE2_FALLBACK_MAX):
        print(
            f"[OPENAI-CONFIG] ⚠️ OPENAI_GREETING_STAGE2_FALLBACK_S={value} outside "
            f"[{OPENAI_GREETING_STAGE2_FALLBACK_MIN}, {OPENAI_GREETING_STAGE2_FALLBACK_MAX}] — using {default}"
        )
        return default
    return value


OPENAI_GREETING_STAGE2_FALLBACK_S = _parse_stage2_fallback_seconds(
    os.getenv("OPENAI_GREETING_STAGE2_FALLBACK_S")
)

# Exact spoken lines. Stage 1 ("הלו?") is neutral. The Stage-2 variants are
# NAME-FREE templates with a single {office} slot filled per call from the
# tenant's configured office identity (voice_shared.resolve_two_stage_office).
# "מאיה"/Maya is the assistant's product name (identical for every tenant), so it
# stays; only the tenant OFFICE phrase is dynamic — no tenant name is hardcoded
# here, and no tenant can ever hear another tenant's office.
_GREETING_STAGE1_LINE = "הלו?"
_GREETING_STAGE2_CALLER_TEMPLATE = "כן, מדברת מאיה {office}. איך אפשר לעזור?"
_GREETING_STAGE2_FALLBACK_TEMPLATE = "היי, מדברת מאיה {office}. איך אפשר לעזור?"

# A first turn after "הלו?" that is ONLY a greeting / acknowledgment / identity
# check → the FIXED Stage-2 question. Anything richer is substantive content and
# is answered naturally (with a brief self-intro), never re-asked.
_STAGE2_FIXED_TRIGGERS = {
    "הלו", "הלו הלו", "כן", "לא", "שלום", "היי", "הי", "אהלן",
    "רועי", "מי זה", "מי זאת", "מי מדבר", "מי מדברת",
    "אוקיי", "אוקי", "בסדר", "סבבה", "תודה", "תודה רבה",
}


def _normalize_greeting_turn(text: str) -> str:
    """Strip surrounding whitespace and trailing punctuation so "רועי?" and
    "מי זה?" match their trigger words."""
    return (text or "").strip().strip("?!.,־-…").strip()


def _is_greeting_only_turn(text: str) -> bool:
    """True → the caller only greeted / acknowledged / identity-checked, so the
    FIXED Stage-2 question fits. False → substantive content: answer it."""
    return _normalize_greeting_turn(text) in _STAGE2_FIXED_TRIGGERS


def _exact_line_instruction(line: str) -> str:
    """Per-response instruction forcing an exact, verbatim single line."""
    return f'אמרי עכשיו בדיוק, מילה במילה, ורק את המשפט הבא בלי שום תוספת: "{line}"'


# Stage-1 Hebrew pronunciation anchor (live-call finding, Aug 2026): "הלו?" is
# generated as the session's FIRST, isolated one-word response, and "הלו" is a
# cognate of "hello" — without an explicit anchor the realtime voice sometimes
# rendered it half-English/American; the longer Stage-2 sentence self-anchors.
# The anchor prefixes ONLY the Stage-1 instruction (Stage-2 untouched); the
# spoken output must remain exactly "הלו?".
_STAGE1_HEBREW_ANCHOR = "דברי בעברית ישראלית טבעית ובמבטא ישראלי."


def _stage1_instruction() -> str:
    """Stage-1 "הלו?" instruction: Israeli-Hebrew anchor + the exact line."""
    return f"{_STAGE1_HEBREW_ANCHOR} {_exact_line_instruction(_GREETING_STAGE1_LINE)}"


# Substantive Stage 2: identify (with the tenant {office}), then continue from
# what the caller already said. Name-free template — {office} is filled per call.
_STAGE2_SUBSTANTIVE_TEMPLATE = (
    "הציגי את עצמך במשפט קצר וטבעי כמאיה {office}, ומיד אחרי זה המשיכי "
    "ישירות ממה שהפונה כבר אמר. אל תבקשי מהפונה לחזור על סיבת הפנייה, ואל תשאלי "
    "\"איך אפשר לעזור?\" — הוא כבר הסביר."
)


# ── Onset-based interruption (barge-in) — TENANT-SCOPED, default OFF ──────────
# Phase: barge-in ONLY. Moves the yield-the-floor decision from transcription-
# gated (~2.9s measured) to speech-onset + a short energy-persistence guard
# (~150ms), scoped to RESPONDING_PLAYING. GREETING_PLAYING keeps the M4 path
# untouched; `interrupt_response` stays FALSE.
# The ON/OFF gate is a CLIENT ALLOWLIST resolved per-call via voice_shared's
# onset_barge_enabled(client_id) (OPENAI_ONSET_BARGE_CLIENT_IDS) — NOT a global
# boolean — so Roi can be enabled without affecting Eliran or any other tenant.
# The constants below are TUNING only (not the gate). For a non-enabled call the
# controller/wiring are a complete no-op (legacy transcription-gated path).
OPENAI_ONSET_GUARD_MS              = int(float(os.getenv("OPENAI_ONSET_GUARD_MS", "150")))
OPENAI_ONSET_ENERGY_RATIO          = float(os.getenv("OPENAI_ONSET_ENERGY_RATIO", "3.0"))
OPENAI_ONSET_ENERGY_MIN_FRAMES     = int(float(os.getenv("OPENAI_ONSET_ENERGY_MIN_FRAMES", "6")))  # >100ms burst
OPENAI_ONSET_ENERGY_ABS_MIN        = float(os.getenv("OPENAI_ONSET_ENERGY_ABS_MIN", "500"))
OPENAI_ONSET_REISSUE_MAX_PLAYED_MS = int(float(os.getenv("OPENAI_ONSET_REISSUE_MAX_PLAYED_MS", "1200")))
OPENAI_ONSET_FALSE_BARGE_CIRCUIT   = int(float(os.getenv("OPENAI_ONSET_FALSE_BARGE_CIRCUIT", "3")))
_ONSET_FRAME_MS = 20   # Twilio media frame = 20ms of 8kHz µ-law


def _build_ulaw_lut():
    """G.711 µ-law byte → linear PCM16 decode table (256 entries)."""
    lut = []
    for u in range(256):
        uu = (~u) & 0xFF
        sign = uu & 0x80
        exp = (uu >> 4) & 0x07
        man = uu & 0x0F
        s = (((man << 3) + 0x84) << exp) - 0x84
        lut.append(-s if sign else s)
    return lut


_ULAW_LUT = _build_ulaw_lut()


def _ulaw_frame_rms(payload_b64: str) -> float:
    """RMS (linear-PCM16 scale) of one base64 µ-law inbound frame. 0.0 on error."""
    try:
        raw = base64.b64decode(payload_b64)
    except Exception:
        return 0.0
    n = len(raw)
    if not n:
        return 0.0
    lut = _ULAW_LUT
    acc = 0
    for b in raw:
        v = lut[b]
        acc += v * v
    return (acc / n) ** 0.5


class InboundSpeechTracker:
    """Continuous, transcription-independent inbound speech-energy tracker.

    Provides (a) a slowly-adapting noise floor, (b) a 'sustained speech onset'
    timestamp used ONLY for latency instrumentation (caller-speech-onset → …),
    and (c) a per-window sustained-frame count used by the onset guard. Pure and
    unit-testable: push (ts, rms) frames; never does I/O.
    """
    def __init__(self, ratio=OPENAI_ONSET_ENERGY_RATIO, abs_min=OPENAI_ONSET_ENERGY_ABS_MIN,
                 min_frames=OPENAI_ONSET_ENERGY_MIN_FRAMES):
        self.ratio = ratio
        self.abs_min = abs_min
        self.min_frames = min_frames
        self._floor = abs_min
        self._run = 0
        self._below_run = 0
        self.onset_ts = None                 # first-frame ts of the current sustained run
        self._frames = deque(maxlen=64)      # (ts, above) — ~1.3s history

    def _threshold(self):
        return max(self.abs_min, self._floor * self.ratio)

    def push(self, ts: float, rms: float) -> bool:
        above = rms > self._threshold()
        self._frames.append((ts, above))
        if above:
            self._run += 1
            self._below_run = 0
            if self._run >= self.min_frames and self.onset_ts is None:
                self.onset_ts = ts - (self.min_frames - 1) * (_ONSET_FRAME_MS / 1000.0)
        else:
            self._below_run += 1
            if self._below_run >= 5:         # ~100ms of silence ends the burst
                self._run = 0
                self.onset_ts = None
            self._floor = 0.95 * self._floor + 0.05 * rms   # adapt on quiet frames only
        return above

    def sustained_frames(self, t0: float, t1: float) -> int:
        return sum(1 for (ts, a) in self._frames if t0 <= ts <= t1 and a)


# ── Echo guard (self-speech rejection) — transcript-level, tenant-scoped ──────
# Incident (Roi live, Aug 10): Maya's Stage-2 greeting echoed off the caller
# device → STT "היי מדברת מיה" → passed M4 (13 chars, 2.4s) → accepted turn →
# polluted extraction (name "מיה"). The guard flags caller transcripts that are
# fuzzy prefixes of what Maya JUST played, inside the physical echo window.
# Pure text + timing — NO audio processing, NO VAD/STT change. Shadow mode only
# emits echo_would_reject diagnostics; enforce is implemented but not enabled.
_ECHO_RECENT_MAX = 2            # compare against Maya's last 1–2 utterances
_ECHO_WINDOW_AFTER_END_S = 1.0  # echo can trail playback end by up to ~1s
_ECHO_WINDOW_BEFORE_START_S = 0.3
_ECHO_MIN_CALLER_TOKENS = 3     # shorter texts ("מאיה?", "ביטוח רכב") are NEVER
                                # flagged — protects genuine short repetitions
_ECHO_CONTAINMENT_MIN = 0.70    # ≥70% of caller tokens fuzzy-matched, in order
_ECHO_TOKEN_FUZZ = 0.75         # per-token similarity ("מיה" ~ "מאיה" ≈ 0.86)

_ECHO_STRIP_RE = re.compile(r"[֑-ׇ?!.,:;\"'`´׳״…\-–—־()\[\]]+")


def _echo_normalize(text: str) -> list[str]:
    """Conservative Hebrew normalization → token list: strip punctuation and
    niqqud, collapse whitespace. No stemming, no aggressive rewriting."""
    return [t for t in _ECHO_STRIP_RE.sub(" ", text or "").split() if t]


def _echo_token_sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def _echo_match_score(caller_text: str, assistant_text: str):
    """(containment, similarity) of the caller tokens against the assistant
    utterance, matched as an ORDERED subsequence with fuzzy token equality.
    Ordered matching kills coincidental bag-of-words overlap; fuzzy tokens
    catch STT garbling of echoes ("מאיה" → "מיה")."""
    ct = _echo_normalize(caller_text)
    at = _echo_normalize(assistant_text)
    if not ct or not at:
        return 0.0, 0.0
    matched, sims, j = 0, [], 0
    for tok in ct:
        while j < len(at):
            s = _echo_token_sim(tok, at[j])
            j += 1
            if s >= _ECHO_TOKEN_FUZZ:
                matched += 1
                sims.append(s)
                break
    containment = matched / len(ct)
    similarity = (sum(sims) / len(sims)) if sims else 0.0
    return containment, similarity


def _echo_check(caller_text: str, recent: list, onset_ts: float):
    """Return a match dict if the caller transcript looks like an echo of a
    recently played Maya utterance, else None.

    `recent` items: {"text", "play_start", "play_end"} (play_end None while the
    utterance is still playing). A candidate must BOTH overlap the physical
    playback window and fuzzy-prefix-match the utterance text.
    """
    ct = _echo_normalize(caller_text)
    if len(ct) < _ECHO_MIN_CALLER_TOKENS:
        return None
    if onset_ts is None:
        return None
    for u in reversed(recent or []):
        start = u.get("play_start")
        if start is None:
            continue
        end = u.get("play_end")
        in_window = (start - _ECHO_WINDOW_BEFORE_START_S) <= onset_ts and (
            end is None or onset_ts <= end + _ECHO_WINDOW_AFTER_END_S)
        if not in_window:
            continue
        containment, similarity = _echo_match_score(caller_text, u.get("text", ""))
        if containment >= _ECHO_CONTAINMENT_MIN:
            return {
                "assistant_text": (u.get("text") or "")[:80],
                "containment": round(containment, 3),
                "similarity": round(similarity, 3),
                "onset_offset_s": round(onset_ts - start, 3),
            }
    return None


class TurnController:
    """See module comment. All methods are pure and return list[(Action, value)]."""

    def __init__(self, monotonic=None, two_stage: bool = False, office: str = None,
                 onset_barge: bool = False):
        self.state = CallState.INITIALIZING
        self.greeting_done = False       # one-time greeting guard (create side)
        # ── M6 two-stage greeting (Roi-only; False ⇒ identical to M2–M5) ──────
        self.two_stage = two_stage
        # M6.1: the tenant's spoken office phrase, filled into the Stage-2
        # templates. Defaults to the name-free generic when unset/off.
        self.office = office or _GENERIC_OFFICE_LABEL
        self.greeting_stage = 0          # 0=none 1="הלו?" pending/playing 2=done
        self.stage2_done = False         # single race guard: Stage 2 fires once
        self.last_stage2_kind = None     # "fixed" | "substantive" | "fallback"
        # ── Onset barge-in (Phase: barge-in). onset_barge=False ⇒ complete no-op ─
        self.onset_barge = onset_barge
        self.onset_disabled_for_call = False   # per-call circuit breaker
        self._barge_recover_count = 0          # re-issues for the CURRENT response (cap 1)
        self._false_barge_count = 0            # per-call false-barge budget (circuit)
        self.resp_audio_ms = 0                 # audio ms sent for the CURRENT response
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
        # ── M4: segment/turn binding + audit state (all per-call) ────────────
        self._segment_seq = 0            # incremented on every speech_stopped
        self._turn_seq = 0               # incremented on every ACCEPTED turn
        self._unconsumed_segment = None  # segment awaiting its transcription
        self._pending_item_id = None     # OpenAI item_id of that segment
        self._generation_active = False  # a response is generating right now
        # Result of the most recent on_input_transcription (read by the wiring
        # for diagnostics and the caller-context decision).
        self.last_decision = None        # accepted|held_greeting|orphan|
                                         # obsolete_segment|rejected_gate|ignored_state
        self.last_segment_id = None
        self.last_turn_id = None
        self.last_turn_text = ""

    # — M6.1 Stage-2 lines, built from THIS controller's tenant office —
    def _stage2_caller_instruction(self) -> str:
        return _exact_line_instruction(_GREETING_STAGE2_CALLER_TEMPLATE.format(office=self.office))

    def _stage2_fallback_instruction(self) -> str:
        return _exact_line_instruction(_GREETING_STAGE2_FALLBACK_TEMPLATE.format(office=self.office))

    def _stage2_substantive_instruction(self) -> str:
        return _STAGE2_SUBSTANTIVE_TEMPLATE.format(office=self.office)

    # — greeting —
    def on_session_updated(self):
        if self.state == CallState.INITIALIZING and not self.greeting_done:
            self.greeting_done = True
            self.state = CallState.GREETING_REQUESTED
            self._got_first_delta = False
            # M6: Stage 1 is a scripted "הלו?"; otherwise the M2 model-worded
            # one-shot greeting is unchanged.
            if self.two_stage:
                self.greeting_stage = 1
                return [(Action.SPEAK_SCRIPTED, _stage1_instruction())]
            return [(Action.RESPONSE_CREATE, None)]
        return []

    # — M6 Stage 2 fallback (one-shot task, ~1.7s after "הלו?") —
    def on_greeting_fallback(self):
        """Fire Stage 2 automatically when no accepted caller turn arrived after
        "הלו?". No-op (returns []) if two-stage is off, we are not still in
        Stage 1, or Stage 2 already fired — so it can never double-speak."""
        if not self.two_stage or self.greeting_stage != 1 or self.stage2_done:
            return []
        self.stage2_done = True
        self.greeting_stage = 2
        self.last_stage2_kind = "fallback"
        self.state = CallState.ASSISTANT_RESPONDING
        self._got_first_delta = False
        return [(Action.SPEAK_SCRIPTED, self._stage2_fallback_instruction())]

    # — response lifecycle —
    def on_response_created(self):
        self._got_first_delta = False
        self._generation_active = True   # M4: cancel is meaningful only now
        self.resp_audio_ms = 0           # onset recovery: fresh response, nothing played yet
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
        # M4: generation is over — only playback may remain. A later barge-in
        # must NOT send response.cancel (that produced response_cancel_not_active).
        self._generation_active = False
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

    def _onset_active(self) -> bool:
        """Onset barge-in is live only when enabled AND the per-call circuit
        breaker has not opened. When False, the legacy transcription-gated path
        is the sole barge-in mechanism (identical to pre-Phase behavior)."""
        return self.onset_barge and not self.onset_disabled_for_call

    # — caller speech / turns —
    def on_speech_started(self, t: float):
        # Status marker (legacy). Under onset barge-in it ALSO arms the energy
        # guard while a REPLY is playing — the guard (wiring) confirms sustained
        # speech within ~150ms and cancels WITHOUT waiting for the transcript.
        # Greeting playback is never armed (M4 keeps its stronger protection).
        self._speech_started_at = t
        if self.state in (CallState.WAITING_FOR_CALLER, CallState.ACTIVE_CONVERSATION):
            self.state = CallState.CALLER_SPEAKING
        if self._onset_active() and self.state == CallState.RESPONDING_PLAYING:
            return [(Action.ARM_ONSET_GUARD, t)]
        return []

    # — Onset barge-in: energy-guard outcome (called by the wiring) —
    def on_onset_confirmed(self):
        """Sustained caller speech confirmed during a reply → yield the floor NOW
        (cancel + Twilio clear), then listen. No transcript is read to decide
        this. Stale confirm (state already moved) is ignored."""
        if not self._onset_active() or self.state != CallState.RESPONDING_PLAYING:
            return []
        self.pending_marks.clear()             # Twilio clear flushes queued audio
        self.state = CallState.BARGED_LISTENING
        return [(Action.CANCEL_AND_CLEAR, {"cancel": self._generation_active})]

    def on_onset_aborted(self):
        """Energy did not sustain (transient / click / short non-speech) → Maya
        never pauses; nothing to do."""
        return []

    def on_speech_stopped(self, t: float, item_id: str = None):
        if self._speech_started_at is not None:
            self._last_segment_dur = max(0.0, t - self._speech_started_at)
        # M4: a COMPLETED speech pair mints exactly one segment, which exactly
        # one transcription may consume. speech_started alone never does, so a
        # transcription can never bind to a half-open segment.
        self._segment_seq += 1
        self._unconsumed_segment = self._segment_seq
        self._pending_item_id = item_id
        return []

    def _reset_turn_audit(self):
        self.last_segment_id = None
        self.last_turn_id = None
        self.last_turn_text = ""

    def _release_segment(self):
        self._unconsumed_segment = None
        self._pending_item_id = None

    # — Onset barge-in: classify + recover AFTER we already yielded the floor —
    def _on_transcription_after_barge(self, text: str, d: float):
        """We already stopped Maya on speech onset. The transcript now only says
        WHAT the caller said and whether the stop was a false trigger."""
        if is_valid_caller_turn(text, d):
            # Real interruption content → answer it (normal turn).
            self._release_segment()
            self._turn_seq += 1
            self.last_turn_id = self._turn_seq
            self.last_turn_text = (text or "").strip()
            self.last_decision = "accepted"
            self.valid_turns += 1
            self._reprompted = False
            self._barge_recover_count = 0        # real content resets the re-issue budget
            self.state = CallState.PROCESSING_CALLER_TURN
            self._got_first_delta = False
            self.state = CallState.ASSISTANT_RESPONDING
            return [(Action.RESPONSE_CREATE, None)]
        # Empty / non-speech transcript → the onset was a FALSE trigger.
        self._release_segment()
        self.last_decision = "false_barge"
        return self._recover_after_false_barge()

    def _recover_after_false_barge(self):
        """Bounded, loop-safe recovery. Re-issue ONCE only if the reply had barely
        started; otherwise yield to WAITING rather than replay a near-complete
        answer. The per-call circuit breaker disables onset after N false barges."""
        self._false_barge_count += 1
        if self._false_barge_count >= OPENAI_ONSET_FALSE_BARGE_CIRCUIT:
            self.onset_disabled_for_call = True          # → legacy path for rest of call
        if (self._barge_recover_count < 1
                and self.resp_audio_ms <= OPENAI_ONSET_REISSUE_MAX_PLAYED_MS):
            self._barge_recover_count += 1
            self.state = CallState.PROCESSING_CALLER_TURN
            self._got_first_delta = False
            self.state = CallState.ASSISTANT_RESPONDING
            return [(Action.RESPONSE_CREATE, None)]       # re-issue (barely started)
        self._enter_waiting()                             # yield (mostly played / cap reached)
        return []

    # — Echo guard: ENFORCE path (implemented; enabled only via config mode) —
    def on_echo_rejected(self):
        """The wiring detected a self-speech echo in ENFORCE mode. Consume the
        segment; the phantom text never becomes a turn. In BARGED_LISTENING the
        onset-yield was caused by the echo → reuse the existing bounded
        false-barge recovery (re-issue once if barely started, else yield; the
        per-call circuit breaker applies unchanged). Elsewhere: no state change
        beyond reverting a bare CALLER_SPEAKING marker."""
        self._reset_turn_audit()
        self._release_segment()
        self.last_decision = "echo_rejected"
        if self.state == CallState.BARGED_LISTENING:
            return self._recover_after_false_barge()
        if self.state == CallState.CALLER_SPEAKING:
            self.state = (
                CallState.ACTIVE_CONVERSATION if self.valid_turns >= 1
                else CallState.WAITING_FOR_CALLER
            )
        return []

    def on_input_transcription(self, text: str, dur: float = None, item_id: str = None):
        d = self._last_segment_dur if dur is None else dur
        self._reset_turn_audit()
        # ── Onset barge-in: post-yield classification (Phase: barge-in) ──────
        # If we already stopped Maya on onset, the transcript decides content /
        # false-trigger — it does NOT decide whether to yield (already done).
        if self.state == CallState.BARGED_LISTENING:
            return self._on_transcription_after_barge(text, d)
        # Only a waiting state (fresh turn) or a PLAYING state (barge-in) may
        # accept a caller turn. While a response is generating
        # (ASSISTANT_RESPONDING/PROCESSING) or CLOSING, drop the transcription —
        # this prevents a duplicate response.create for overlapping segments.
        if not (self.state in _WAITING_STATES or self.state in _PLAYING_STATES):
            self.last_decision = "ignored_state"
            return []
        # ── M4 segment binding ───────────────────────────────────────────────
        # ORPHAN: no completed speech pair is awaiting a transcription. Covers a
        # transcription with no segment AND a duplicate for an already-consumed
        # segment (its segment was released on consumption).
        if self._unconsumed_segment is None:
            self.last_decision = "orphan"
            return []
        # LATE/OBSOLETE: this transcription belongs to an older speech item than
        # the segment currently awaiting one.
        if (item_id is not None and self._pending_item_id is not None
                and item_id != self._pending_item_id):
            self.last_decision = "obsolete_segment"
            return []
        segment_id = self._unconsumed_segment
        self.last_segment_id = segment_id

        if not is_valid_caller_turn(text, d):
            # Junk / noise / echo — consume the segment and revert a bare
            # CALLER_SPEAKING marker.
            self._release_segment()
            self.last_decision = "rejected_gate"
            if self.state == CallState.CALLER_SPEAKING:
                self.state = (
                    CallState.ACTIVE_CONVERSATION if self.valid_turns >= 1
                    else CallState.WAITING_FOR_CALLER
                )
            return []
        # ── M4 greeting protection ───────────────────────────────────────────
        # During the greeting, only a strong interruption may cut Maya off.
        # Anything weaker is HELD: no cancel, no clear, no response, no state
        # change, and (in the wiring) never added to caller conversation
        # context. The greeting finishes and the real mark drives the WAITING
        # transition — so a held fragment can never trigger a later response.
        if self.state == CallState.GREETING_PLAYING and not is_verified_greeting_interruption(text, d):
            self._release_segment()
            self.last_decision = "held_greeting"
            return []

        # ── Accepted caller turn ─────────────────────────────────────────────
        self._release_segment()
        self._turn_seq += 1
        self.last_turn_id = self._turn_seq
        self.last_turn_text = (text or "").strip()
        self.last_decision = "accepted"
        self.valid_turns += 1
        self._reprompted = False
        actions = []
        if self.state in _PLAYING_STATES:
            if d >= BARGE_IN_MIN_DURATION_S:
                self.pending_marks.clear()            # Twilio clear flushes all
                # M4: cancel only while the response is genuinely generating;
                # the Twilio clear is always sent (barge-in behavior unchanged).
                actions.append((Action.CANCEL_AND_CLEAR, {"cancel": self._generation_active}))
            # else: let playback finish; the turn is still created below.
        self.state = CallState.PROCESSING_CALLER_TURN
        # ── M6: the FIRST accepted turn after "הלו?" drives Stage 2 ───────────
        # A bare greeting / identity check → the fixed self-intro question; real
        # content → a normal model reply that self-introduces then continues from
        # what was said (the accepted turn is preserved for transcript/summary,
        # never overwritten). `stage2_done` makes this fire at most once.
        if self.two_stage and self.greeting_stage == 1 and not self.stage2_done:
            self.stage2_done = True
            self.greeting_stage = 2
            if _is_greeting_only_turn(text):
                self.last_stage2_kind = "fixed"
                actions.append((Action.SPEAK_SCRIPTED, self._stage2_caller_instruction()))
            else:
                self.last_stage2_kind = "substantive"
                actions.append((Action.SPEAK_SCRIPTED, self._stage2_substantive_instruction()))
        else:
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
    # Setup-head instrumentation: precise monotonic marks across the previously
    # un-timestamped opening (handler entry → media start → context → OpenAI
    # connect → session.created → first audio). All share one monotonic clock so
    # the whole head is reconstructable from the diag stream, keyed by call_sid.
    _t_entry = time.monotonic()
    _t_media_start = _t_entry   # set for real when the Twilio start event arrives
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
                _t_media_start = time.monotonic()
                stream_sid = evt["start"]["streamSid"]
                _custom = evt["start"].get("customParameters", {}) or {}
                if not call_sid:
                    call_sid = _custom.get("call_sid") or evt["start"].get("callSid", "")
                print(f"[OPENAI-WS] Start event — stream_sid={stream_sid} call_sid={call_sid!r} custom_keys={list(_custom.keys())}")
                _diag("setup_media_start", call_sid,
                      entry_to_start_ms=round((_t_media_start - _t_entry) * 1000))
                # Durable handoff — identical resolution to the Gemini path.
                _resolved    = await _resolve_gemini_context(_custom, call_sid)
                _t_ctx       = time.monotonic()
                agent_cfg    = _resolved["agent_cfg"]
                caller_phone = _resolved["caller_phone"]
                client_id    = _resolved["client_id"]
                client_name  = _resolved["client_name"]
                webhook_url  = agent_cfg.get("webhook_url", "")
                print(f"[OPENAI-WS] context source={_resolved['source']} caller={caller_phone} client='{client_name}' webhook={'yes' if webhook_url else 'no'}")
                _diag("setup_context_fetched", call_sid, source=_resolved["source"],
                      ctx_fetch_ms=round((_t_ctx - _t_media_start) * 1000))
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
    # M6: for two-stage clients the opening is delivered as scripted turns
    # (SPEAK_SCRIPTED), so the free-form one-shot opening directive is omitted to
    # avoid two competing greeting instructions. Everything else is unchanged.
    _two_stage = _two_stage_greeting_enabled(client_id or "")
    # Onset barge-in: tenant-scoped gate resolved ONCE here (client allowlist).
    # Everything downstream uses this per-call boolean — never a global env — so
    # Roi can be enabled without touching Eliran or any other Realtime tenant.
    _onset_barge = _onset_barge_enabled(client_id or "")
    # Echo guard: tenant-scoped mode resolved ONCE here ('off'|'shadow'|'enforce').
    # 'off' (default / non-allowlisted) ⇒ zero echo analysis work for this call.
    _echo_mode = _echo_guard_mode(client_id or "")
    if _echo_mode != "off":
        print(f"[OPENAI-WS] echo guard ACTIVE — mode={_echo_mode} (client allowlisted)")
    # M6.1: the spoken office identity for the Stage-2 self-intro is resolved
    # per-tenant from config (never hardcoded). Generic fallback when off/unset.
    _office = _resolve_two_stage_office(agent_cfg) if _two_stage else _GENERIC_OFFICE_LABEL
    if _two_stage:
        system_instruction = base_prompt
        print(f"[OPENAI-WS] M6 two-stage greeting ACTIVE — scripted opening, office={_office!r} (client allowlisted)")
    else:
        system_instruction = _openai_opening_instruction(base_prompt, first_message)
        if first_message:
            print("[OPENAI-WS] natural one-time opening instruction injected into system prompt")
    system_instruction += _NAME_PROTOCOL_INSTRUCTION
    # M7: turn-level dialogue discipline, tenant-scoped. Appended last so it is
    # the most recent instruction the model reads, and omitted entirely (not
    # merely disabled) for every non-allowlisted tenant.
    if _dialogue_style_enabled(client_id or ""):
        system_instruction += _DIALOGUE_STYLE_INSTRUCTION
        print("[OPENAI-WS] M7 dialogue discipline ACTIVE (client allowlisted)")

    # ── Connect to OpenAI Realtime (GA) ──────────────────────────────────────
    # NOTE: default ping_interval kept ON (WS keepalive) — unlike the Gemini
    # path, half-open sockets are detected at the protocol level.
    openai_url = _OPENAI_WS_URL.format(model=OPENAI_REALTIME_MODEL)
    try:
        openai_ws = await websockets.connect(
            openai_url,
            additional_headers={"Authorization": f"Bearer {_OPENAI_API_KEY}"},
        )
        _t_oai = time.monotonic()
        print(f"[OPENAI-WS] OpenAI Realtime connected — model={OPENAI_REALTIME_MODEL}")
        _diag("setup_openai_connected", call_sid,
              connect_ms=round((_t_oai - _t_ctx) * 1000),
              entry_to_connected_ms=round((_t_oai - _t_entry) * 1000))
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
    # M5: additive, chronological view of the same accepted turns (email only).
    # Fresh per call; never feeds extraction/summary/excerpt.
    _transcript_turns: list[dict] = []
    _response_first_audio_logged = False
    _ctrl = TurnController(two_stage=_two_stage, office=_office,
                           onset_barge=_onset_barge)
    # Onset barge-in: continuous inbound speech-energy tracker (None when this
    # call is NOT allowlisted ⇒ no per-frame work, no behavior change).
    _energy = InboundSpeechTracker() if _onset_barge else None

    # Echo guard: Maya's last utterances + playback timing (None when off ⇒ no
    # per-event work). recent items: {"text", "play_start", "play_end"}.
    _echo_state = {"recent": [], "cur_start": None} if _echo_mode != "off" else None

    def _echo_close_playback():
        # playback ended (mark returned) or was flushed (barge clear) — close
        # the echo window for all still-open utterances.
        if _echo_state is not None:
            _now = time.monotonic()
            for _u in _echo_state["recent"]:
                if _u["play_end"] is None:
                    _u["play_end"] = _now

    # ── Action executor — the ONLY place I/O side-effects happen ─────────────
    # Every response.create in this module is sent from here (RESPONSE_CREATE /
    # REPROMPT / SPEAK_SCRIPTED), so the "app owns response creation" invariant
    # is grep-checkable.
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
                # M4 audit: every caller-driven create is traceable to exactly
                # one accepted turn (call_sid, segment_id, turn_id, text, state).
                if _ctrl.last_decision == "accepted" and _ctrl.last_turn_id is not None:
                    _diag("response_create_sent", call_sid, reason="valid_turn",
                          segment_id=_ctrl.last_segment_id, turn_id=_ctrl.last_turn_id,
                          text=_ctrl.last_turn_text[:60], state=_ctrl.state.value)
                else:
                    _diag("response_create_sent", call_sid, reason="greeting",
                          state=_ctrl.state.value)
            elif act == Action.REPROMPT:
                await _send_response_create(_REPROMPT_INSTRUCTION)
                _diag("reprompt_sent", call_sid, reason="watchdog_checkin", gen=val)
            elif act == Action.SPEAK_SCRIPTED:
                # M6: greeting Stage 1 / Stage 2 — a response.create carrying a
                # narrow per-response instruction (verbatim line or self-intro).
                await _send_response_create(val)
                _diag("scripted_response_sent", call_sid,
                      greeting_stage=_ctrl.greeting_stage,
                      kind=_ctrl.last_stage2_kind, state=_ctrl.state.value)
            elif act == Action.ARM_ONSET_GUARD:
                # Onset barge-in: start the ~150ms energy-persistence guard for
                # this speech onset (val = speech_started monotonic ts).
                _cancel_onset_guard()
                _onset_guard["task"] = asyncio.create_task(_onset_guard_runner(val))
                _diag("onset_guard_armed", call_sid, state=_ctrl.state.value)
            elif act == Action.CANCEL_AND_CLEAR:
                # M4: response.cancel ONLY while a response is genuinely
                # generating (avoids response_cancel_not_active); the Twilio
                # clear is always sent so barge-in behavior is unchanged.
                _do_cancel = val.get("cancel", True) if isinstance(val, dict) else True
                if _do_cancel:
                    await openai_ws.send(json.dumps({"type": "response.cancel"}))
                if stream_sid:
                    await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                _echo_close_playback()   # flushed audio ends the echo window
                _diag("barge_in_cancel_and_clear", call_sid, cancel_sent=bool(_do_cancel))
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
        # Onset barge-in (flag ON only): tap inbound energy for the persistence
        # guard + the caller-speech-onset latency metric. Read-only; never gates.
        if _energy is not None:
            _energy.push(time.monotonic(), _ulaw_frame_rms(payload))
        # Twilio payload is already base64 µ-law — append verbatim.
        await openai_ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": payload,
        }))

    # ── Transport heartbeat state (M3) — diagnostics only ────────────────────
    _hb = {"seq": 0, "sent_id": "", "ack_id": "", "echo_ts": None}

    # ── Onset barge-in: energy-guard task (one per speech_started while playing) ─
    _onset_guard = {"task": None}

    def _cancel_onset_guard():
        t = _onset_guard["task"]
        if t is not None and not t.done():
            t.cancel()
        _onset_guard["task"] = None

    async def _onset_guard_runner(t_vad: float):
        # Wait GUARD_MS, then confirm sustained inbound speech in [t_vad, +GUARD].
        # Confirm → cancel + Twilio clear (yield the floor) with the full latency
        # breakdown. Abort → Maya keeps talking (transient rejected).
        try:
            await asyncio.sleep(OPENAI_ONSET_GUARD_MS / 1000.0)
            above = (_energy.sustained_frames(t_vad, t_vad + OPENAI_ONSET_GUARD_MS / 1000.0)
                     if _energy else 0)
            if above >= OPENAI_ONSET_ENERGY_MIN_FRAMES:
                acts = _ctrl.on_onset_confirmed()
                if acts:
                    _t_clear = time.monotonic()
                    _onset_ts = _energy.onset_ts if _energy else None
                    _diag("onset_barge_cancel", call_sid,
                          vad_to_clear_ms=round((_t_clear - t_vad) * 1000),
                          onset_to_clear_ms=(round((_t_clear - _onset_ts) * 1000) if _onset_ts else None),
                          onset_to_vad_ms=(round((t_vad - _onset_ts) * 1000) if _onset_ts else None),
                          guard_ms=OPENAI_ONSET_GUARD_MS, above=above,
                          floor=round(_energy._floor) if _energy else None)
                    await _execute(acts)
            else:
                _ctrl.on_onset_aborted()
                _diag("onset_guard_aborted", call_sid, above=above)
        except asyncio.CancelledError:
            return
        except Exception as e:
            _diag("onset_guard_error", call_sid, error=str(e)[:200])

    # ── M6 Stage-2 fallback: one-shot timer armed when "הלו?" finishes playing ─
    _greeting_fallback = {"task": None}

    def _cancel_greeting_fallback():
        t = _greeting_fallback["task"]
        if t is not None and not t.done():
            t.cancel()
        _greeting_fallback["task"] = None

    async def _greeting_fallback_runner():
        # After ~1.7s of post-"הלו?" silence with no accepted caller turn, speak
        # Stage 2 automatically. Cancelled the instant a caller turn triggers
        # Stage 2 first; on_greeting_fallback() is itself guarded (stage2_done),
        # so even a lost cancel race can never double-speak.
        try:
            await asyncio.sleep(OPENAI_GREETING_STAGE2_FALLBACK_S)
            acts = _ctrl.on_greeting_fallback()
            if acts:
                _diag("greeting_stage2_fallback_fired", call_sid,
                      after_s=OPENAI_GREETING_STAGE2_FALLBACK_S)
                await _execute(acts)
        except asyncio.CancelledError:
            return
        except Exception as e:
            _diag("greeting_fallback_error", call_sid, error=str(e)[:200])

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
        _echo_close_playback()   # playback finished at the caller device
        _diag("playback_mark_returned", call_sid, mark=name, state=_ctrl.state.value)
        # A returned playback mark may have re-armed a fresh waiting generation.
        if _ctrl.state in (CallState.WAITING_FOR_CALLER, CallState.ACTIVE_CONVERSATION):
            _diag("waiting_armed", call_sid, gen=_ctrl._timeout_gen,
                  state=_ctrl.state.value,
                  timeout=(OPENAI_WAITING_CLOSE_SECONDS if _ctrl._reprompted
                           else OPENAI_WAITING_REPROMPT_SECONDS))
        # M6: Stage 1 "הלו?" just finished playing → arm the one-shot Stage 2
        # fallback exactly once (a caller turn will cancel it if it speaks first).
        if (_ctrl.two_stage and _ctrl.greeting_stage == 1 and not _ctrl.stage2_done
                and _ctrl.state == CallState.WAITING_FOR_CALLER
                and _greeting_fallback["task"] is None):
            _greeting_fallback["task"] = asyncio.create_task(_greeting_fallback_runner())
            _diag("greeting_stage2_fallback_armed", call_sid,
                  after_s=OPENAI_GREETING_STAGE2_FALLBACK_S)

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
                    _diag("session_created", call_sid, model=OPENAI_REALTIME_MODEL,
                          since_entry_ms=round((time.monotonic() - _t_entry) * 1000))

                elif etype == "session.updated":
                    # One-time greeting: the controller emits RESPONSE_CREATE
                    # exactly once (greeting_done guard). No caller-text trigger.
                    acts = _ctrl.on_session_updated()
                    if acts:
                        _diag("greeting_response_created", call_sid)
                        await _execute(acts)

                elif etype == "input_audio_buffer.speech_started":
                    _t_ss = time.monotonic()
                    acts = _ctrl.on_speech_started(_t_ss)
                    _diag("speech_started", call_sid, state=_ctrl.state.value,
                          onset_to_vad_ms=(round((_t_ss - _energy.onset_ts) * 1000)
                                           if (_energy and _energy.onset_ts) else None))
                    # Legacy path: bare speech_started never cancels (RC1/RC2).
                    # Onset barge-in (flag ON): may arm the energy guard here.
                    if acts:
                        await _execute(acts)

                elif etype == "input_audio_buffer.speech_stopped":
                    _ctrl.on_speech_stopped(time.monotonic(), item_id=event.get("item_id"))
                    _diag("speech_stopped", call_sid, segment_id=_ctrl._unconsumed_segment)

                elif etype == "conversation.item.input_audio_transcription.completed":
                    _text = (event.get("transcript") or "").strip()
                    # ── Echo guard (tenant-scoped) ───────────────────────────
                    # SHADOW: diagnostic only — state, turns, transcript,
                    # extraction, summary, email and responses are untouched.
                    # ENFORCE: the phantom text never becomes a turn (segment
                    # consumed; BARGED_LISTENING reuses false-barge recovery).
                    _echo_hit = None
                    if _echo_state is not None and _text:
                        _echo_hit = _echo_check(_text, _echo_state["recent"],
                                                _ctrl._speech_started_at)
                    if _echo_hit is not None and _echo_mode == "shadow":
                        _diag("echo_would_reject", call_sid, caller_text=_text[:60],
                              matched_assistant=_echo_hit["assistant_text"],
                              similarity=_echo_hit["similarity"],
                              containment=_echo_hit["containment"],
                              onset_offset_s=_echo_hit["onset_offset_s"],
                              state=_ctrl.state.value, mode=_echo_mode)
                    if _echo_hit is not None and _echo_mode == "enforce":
                        _diag("echo_rejected", call_sid, caller_text=_text[:60],
                              matched_assistant=_echo_hit["assistant_text"],
                              similarity=_echo_hit["similarity"],
                              containment=_echo_hit["containment"],
                              onset_offset_s=_echo_hit["onset_offset_s"],
                              state=_ctrl.state.value, mode=_echo_mode)
                        acts = _ctrl.on_echo_rejected()
                        if acts:
                            if await _execute(acts):
                                break
                        continue   # phantom turn fully consumed — nothing else runs
                    acts = _ctrl.on_input_transcription(_text, item_id=event.get("item_id"))
                    _decision = _ctrl.last_decision
                    # M4: a HELD greeting fragment is noise — it must never enter
                    # accepted caller conversation context (extraction/summary/
                    # excerpt). A false-barge (onset yielded, transcript empty/
                    # junk) is likewise never real content. Others keep M3.
                    if _text and _decision not in ("held_greeting", "false_barge"):
                        _caller_lines.append(_text)
                        _transcript_turns.append({"role": "לקוח", "text": _text})
                    if _decision == "false_barge":
                        _diag("barge_recovery", call_sid,
                              action=("reissue" if _ctrl.state == CallState.ASSISTANT_RESPONDING else "yield"),
                              resp_audio_ms=round(_ctrl.resp_audio_ms),
                              false_count=_ctrl._false_barge_count,
                              circuit_open=_ctrl.onset_disabled_for_call, text=_text[:40])
                    if _decision == "held_greeting":
                        _diag("greeting_fragment_held", call_sid,
                              segment_id=_ctrl.last_segment_id, text=_text[:40],
                              state=_ctrl.state.value)
                    elif _decision == "orphan":
                        _diag("orphan_transcription", call_sid, text=_text[:40],
                              state=_ctrl.state.value)
                    elif _decision == "obsolete_segment":
                        _diag("obsolete_transcription", call_sid, text=_text[:40],
                              state=_ctrl.state.value)
                    _diag("input_transcription", call_sid, text=_text,
                          valid_turn=(_decision == "accepted"), decision=_decision,
                          segment_id=_ctrl.last_segment_id, turn_id=_ctrl.last_turn_id,
                          state=_ctrl.state.value)
                    # M6: a caller turn that drove Stage 2 cancels the pending
                    # fallback timer (the fixed/substantive reply already went out).
                    if _decision == "accepted" and _ctrl.last_stage2_kind in ("fixed", "substantive"):
                        _cancel_greeting_fallback()
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
                        if _onset_barge:
                            # audio ms of THIS response so far (recovery uses it to
                            # decide re-issue vs yield). base64 len × 3/4 = µ-law
                            # bytes; 8 bytes = 1ms at 8kHz. No decode on the hot path.
                            _ctrl.resp_audio_ms += (len(delta) * 3 // 4) / 8.0
                        if not _response_first_audio_logged:
                            _response_first_audio_logged = True
                            _now = time.monotonic()
                            if _echo_state is not None:
                                _echo_state["cur_start"] = _now   # echo window opens
                            _diag("first_outbound_audio", call_sid,
                                  since_entry_ms=round((_now - _t_entry) * 1000),
                                  since_media_start_ms=round((_now - _t_media_start) * 1000))
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
                        _transcript_turns.append({"role": "מאיה", "text": _text})
                        _ctrl.on_assistant_transcript(_text)
                        if _echo_state is not None:
                            # echo reference: what Maya just played + its window
                            _echo_state["recent"].append({
                                "text": _text,
                                "play_start": _echo_state["cur_start"],
                                "play_end": None,
                            })
                            del _echo_state["recent"][:-_ECHO_RECENT_MAX]

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
        _bg_tasks = [_watchdog_task, _heartbeat_task]
        if _greeting_fallback["task"] is not None:   # M6 one-shot Stage-2 timer
            _bg_tasks.append(_greeting_fallback["task"])
        if _onset_guard["task"] is not None:         # onset barge-in energy guard
            _bg_tasks.append(_onset_guard["task"])
        for _t in _bg_tasks:
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
        # M5: chronological RTL-safe rendering for the email. Additive — the raw
        # excerpt above is unchanged and remains the fallback + diagnostic value.
        _transcript_html_value = _transcript_html(_transcript_turns)
        # Fabrication guard (incident 2026-07-21): NEVER run the summary LLM when
        # the caller contributed no clear content — a transcript of only Maya's
        # greeting made the model invent a caller request + reply. Use a
        # deterministic, truthful summary instead. Normal two-sided calls (≥1
        # valid caller line) keep the existing summarization behavior unchanged.
        if _has_valid_caller_content(_caller_lines):
            _summary = await _summarize_transcript(_full_text, caller_names_allowed=_allowed_names)
        else:
            _summary = _EMPTY_CALLER_SUMMARY
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
            _history = await _get_customer_history(caller_phone, _call_started_at, agent_cfg.get("agent_id"))
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
                # M5: chronological RTL-safe HTML (Make prefers it, falls back
                # to transcript_excerpt when empty)
                "transcript_html":       _transcript_html_value,
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

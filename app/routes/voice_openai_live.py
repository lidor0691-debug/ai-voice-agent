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
from fastapi import APIRouter, WebSocket, Query
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

_OPENAI_WS_URL = "wss://api.openai.com/v1/realtime?model={model}"


# ── Pure helpers (unit-tested) ────────────────────────────────────────────────

def _build_session_update(system_instruction: str) -> dict:
    """
    GA session.update payload.

    - audio/pcmu both directions: Twilio Media Streams speak µ-law 8 kHz
      natively, so audio passes through base64-verbatim with NO transcoding.
    - server_vad with documented defaults — no tuning experiments in M1.
    - Input transcription ON (separate caller transcript buffer needs it).
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
                    # language pinned to Hebrew (M1.1): without it, short phone
                    # utterances hallucinate into other languages — which is
                    # exactly where caller names live.
                    "transcription": {
                        "model": OPENAI_REALTIME_TRANSCRIBE_MODEL,
                        "language": "he",
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
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
    OpenAI-path opening (M1.1): the greeting is an INTENT, not a script.

    Replaces the Gemini path's "open with exactly this sentence" (which produces
    announcer/IVR cadence) with a warm, natural, one-time opening in everyday
    Israeli Hebrew. Gemini path untouched — it keeps its own injection.
    """
    fm = (first_message or "").strip()
    if not fm:
        return base_prompt
    return (
        "פתיחת שיחה (פעם אחת בלבד): פתחי בברכה קצרה וטבעית ברוח המשפט: "
        f"\"{fm}\". "
        "דברי בעברית ישראלית יומיומית, בטון חם ואישי של פקידת קבלה אנושית — "
        "לא כמו הודעה מוקלטת, תפריט קולי או כרוזה. אין צורך לדקלם מילה במילה. "
        "אחרי הפתיחה המשיכי בשיחה רגילה ואל תחזרי על הברכה.\n\n"
        + base_prompt
    )


# Name protocol (M1.1): ask once, confirm once, never invent, never nag.
_NAME_PROTOCOL_INSTRUCTION = (
    "\n\nשם הפונה: בשלב מוקדם בשיחה, שאלי פעם אחת בלבד לשם הפונה, באופן שיחתי. "
    "כשנמסר שם — חזרי עליו בקצרה לאישור (למשל: \"נעים מאוד, דוד\"). "
    "אם הפונה מסרב, מתחמק או לא מוסר שם — המשיכי בשיחה כרגיל ואל תשאלי שוב. "
    "לעולם אל תמציאי שם ואל תסיקי אותו ממקור אחר."
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


# ── Twilio → OpenAI pump (M1.1: testable, exit-guaranteed) ────────────────────

async def _pump_twilio(
    receive_text,
    forward_audio,
    close_openai,
    diag,
    gap_seconds: float = None,
    send_timeout: float = None,
) -> str:
    """
    Pull Twilio frames and forward media payloads to OpenAI. Returns a terminal
    exit-reason string; `close_openai()` is invoked on EVERY exit path (the
    zombie-session fix), so the OpenAI receive loop is always unblocked and the
    handler's single `finally` finalization is guaranteed to run.

    Exit reasons:
      twilio_stop            — Twilio sent the normal stop event
      twilio_disconnect      — WS disconnect surfaced (code/reason diag'd)
      twilio_exhausted       — receive ended without stop/disconnect exception
      dead_socket_gap        — no Twilio frame for gap_seconds (frames normally
                               arrive every ~20ms — a gap means a DEAD socket,
                               never caller silence)
      openai_send_timeout    — openai_ws.send blocked (backpressure)
      openai_closed          — OpenAI WS closed mid-forward
      error:<...>            — anything else
    """
    gap = OPENAI_INBOUND_GAP_SECONDS if gap_seconds is None else gap_seconds
    tmo = OPENAI_SEND_TIMEOUT_SECONDS if send_timeout is None else send_timeout
    reason = "twilio_exhausted"
    last_frame_ts = time.monotonic()
    try:
        while True:
            try:
                raw = await asyncio.wait_for(receive_text(), timeout=gap)
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - last_frame_ts
                reason = "dead_socket_gap"
                diag("dead_socket_gap", elapsed_seconds=round(elapsed, 3), threshold=gap)
                break
            last_frame_ts = time.monotonic()
            evt = json.loads(raw)
            if evt["event"] == "media":
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
    _assistant_speaking = False
    _greeting_triggered = False
    _should_hangup = False
    _response_first_audio_logged = False

    # ── Twilio → OpenAI (µ-law passthrough via exit-guaranteed pump) ─────────
    async def _forward_audio(payload: str):
        # Twilio payload is already base64 µ-law — append verbatim.
        await openai_ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": payload,
        }))

    async def twilio_to_openai_loop():
        exit_reason = await _pump_twilio(
            receive_text=twilio_ws.receive_text,
            forward_audio=_forward_audio,
            close_openai=openai_ws.close,
            diag=lambda event, **kw: _diag(event, call_sid, **kw),
        )
        print(f"[OPENAI-WS] Twilio pump exited — reason={exit_reason}")

    # ── OpenAI → Twilio ───────────────────────────────────────────────────────
    async def openai_to_twilio_loop():
        nonlocal _assistant_speaking, _greeting_triggered, _should_hangup
        nonlocal _response_first_audio_logged
        try:
            async for raw in openai_ws:
                event = json.loads(raw)
                etype = event.get("type", "")

                if etype == "session.created":
                    _diag("session_created", call_sid, model=OPENAI_REALTIME_MODEL)

                elif etype == "session.updated":
                    # Trigger the one-time greeting exactly once: the opening
                    # instruction lives in the system prompt; one response.create
                    # makes the model speak it. No caller-text trigger needed.
                    if not _greeting_triggered:
                        _greeting_triggered = True
                        await openai_ws.send(json.dumps({"type": "response.create"}))
                        _diag("greeting_response_created", call_sid)

                elif etype == "input_audio_buffer.speech_started":
                    _diag("speech_started", call_sid, assistant_speaking=_assistant_speaking)
                    if _assistant_speaking and stream_sid:
                        # Barge-in: server VAD cancels the response server-side
                        # (interrupt_response default); we clear Twilio's queue.
                        await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                        _diag("interruption_twilio_clear_sent", call_sid)

                elif etype == "input_audio_buffer.speech_stopped":
                    _diag("speech_stopped", call_sid)

                elif etype == "conversation.item.input_audio_transcription.completed":
                    _text = (event.get("transcript") or "").strip()
                    if _text:
                        _caller_lines.append(_text)
                    _diag("input_transcription", call_sid, text=_text)

                elif etype == "response.created":
                    _response_first_audio_logged = False
                    _diag("response_created", call_sid)

                elif etype == "response.output_audio.delta":
                    delta = event.get("delta", "")
                    if delta and stream_sid:
                        if not _response_first_audio_logged:
                            _response_first_audio_logged = True
                            _diag("first_outbound_audio", call_sid)
                        _assistant_speaking = True
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
                        if _contains_closing_phrase(_text):
                            _should_hangup = True
                            print("[OPENAI-WS] Closing phrase detected in assistant output — will disconnect after response")

                elif etype == "response.done":
                    _assistant_speaking = False
                    _status = (event.get("response") or {}).get("status", "")
                    _diag("response_completed", call_sid, status=_status)
                    if _status == "cancelled":
                        _diag("response_cancelled", call_sid)
                    if _should_hangup:
                        print("[OPENAI-WS] Closing phrase — grace period, then terminating call")
                        await asyncio.sleep(CLOSING_GRACE_SECONDS)
                        await openai_ws.close()
                        break

                elif etype == "error":
                    _diag("openai_error", call_sid, error=str(event.get("error", ""))[:300])

        except websockets.exceptions.ConnectionClosed as e:
            _diag("ws_closed", call_sid, code=e.code, reason=str(e.reason or ""))
        except Exception as e:
            _diag("openai_receiver_error", call_sid, error=str(e)[:300])

    # ── Run both loops, then the shared post-call pipeline ────────────────────
    try:
        await asyncio.gather(twilio_to_openai_loop(), openai_to_twilio_loop())
    finally:
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

        # Name for the email — NEVER a guess (M1.1):
        #   real extracted name → as-is
        #   no name, clean transcript → "לא נמסר" (caller didn't provide one)
        #   no name, garbled/empty transcript → "לא זוהה בבירור" (STT quality)
        _email_name = extracted.get("name") or _name_fallback(_caller_lines)

        # Real 2–3 sentence Hebrew summary from BOTH speakers (roles tagged),
        # plus a raw excerpt as an always-available fallback for the email.
        _full_text = _full_transcript(_caller_lines, _assistant_lines)
        _excerpt   = _transcript_excerpt(_caller_lines, _assistant_lines)
        _summary   = await _summarize_transcript(_full_text) if _full_text.strip() else ""
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

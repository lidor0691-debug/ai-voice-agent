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

from app.services.lead_capture import save_lead
from app.services.voice_shared import extract_lead_from_transcript as _extract_lead_from_transcript
from app.services.voice_shared import send_voice_webhook as _send_voice_webhook
from app.services.voice_shared import get_customer_history as _get_customer_history
from app.integrations.twilio_client import _get_client as _get_twilio_client

# One-way reuse from the Gemini route (voice_gemini NEVER imports this module —
# it only reads the A/B gate from voice_shared, so there is no import cycle).
from app.routes.voice_gemini import (
    _GEMINI_CALL_CONTEXT,
    _resolve_gemini_context,
    _inject_opening_instruction,
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
                    "transcription": {"model": OPENAI_REALTIME_TRANSCRIBE_MODEL},
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

    # ── Prompt: same Roi system prompt + same one-time greeting injection ─────
    base_prompt = agent_cfg["prompt_override"].replace("{{caller_phone}}", caller_phone)
    first_message = (agent_cfg.get("first_message") or "").strip()
    system_instruction = _inject_opening_instruction(base_prompt, first_message)
    if first_message:
        print("[OPENAI-WS] one-time opening instruction injected into system prompt")

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

    # ── Twilio → OpenAI (µ-law passthrough) ──────────────────────────────────
    async def twilio_to_openai_loop():
        try:
            async for raw in twilio_ws.iter_text():
                evt = json.loads(raw)
                if evt["event"] == "media":
                    # Twilio payload is already base64 µ-law — append verbatim.
                    await openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": evt["media"]["payload"],
                    }))
                elif evt["event"] == "stop":
                    print("[OPENAI-WS] Twilio stream stopped — closing OpenAI WS")
                    try:
                        await openai_ws.close()
                    except Exception:
                        pass
                    break
        except Exception as e:
            print(f"[OPENAI-WS] Twilio receiver error: {e}")
            try:
                await openai_ws.close()
            except Exception:
                pass

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
            _last_call_summary = " | ".join(_summary_parts) or None

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
                "name":                  extracted.get("name", ""),
                "phone_number":          extracted.get("phone_number") or caller_phone,
                "topic":                 extracted.get("topic", ""),
                "notes":                 extracted.get("notes", ""),
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

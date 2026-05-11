"""
Gemini Live voice path — Twilio → Gemini Live bridge with business parity.

Routes registered under the /voice-ai prefix (see main.py):
  POST /voice-ai/voice-gemini   — TwiML entry point (point a Twilio number here)
  WS   /voice-ai/stream-gemini  — bidirectional Twilio Media Stream ↔ Gemini Live

Business parity vs OpenAI path:
  - Agent config fetched from Supabase by "To" number at call entry
  - System prompt sourced from agent config (fallback: hardcoded BPM instruction)
  - Lead saved to Supabase leads table on every call end
  - Webhook fired to Make.com on every call end
  NOTE: Structured lead fields (name, topic) are not yet extracted — Gemini Live
  has no function-call mechanism. The webhook payload contains caller phone + metadata.
  Full structured extraction is tracked as a follow-up task.
"""

import asyncio
import json
import os
from datetime import datetime
from urllib.parse import quote

import httpx
import websockets
from fastapi import APIRouter, WebSocket, Request, Query
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect

from app.utils.audio_gemini import twilio_to_gemini, gemini_to_twilio
from app.services.agent_config import fetch_supabase_agent_config
from app.services.lead_capture import save_lead
from app.services.voice_shared import extract_lead_from_transcript as _extract_lead_from_transcript
from app.services.voice_shared import send_voice_webhook as _send_gemini_webhook
from app.integrations.twilio_client import _get_client as _get_twilio_client

router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")       # Live WebSocket (AQ....)
GEMINI_API_KEY_REST = os.getenv("GEMINI_API_KEY_REST", "")  # kept for reference


# ── In-memory call context (keyed by Twilio CallSid) ─────────────────────────
# Populated at TwiML entry time so phone numbers and agent config survive
# proxy URL encoding (same pattern as CALL_CONTEXT in voice_realtime.py).
_GEMINI_CALL_CONTEXT: dict = {}


def _normalize_phone(phone: str) -> str:
    """Normalize to E.164 Israeli format (+972...). Mirrors voice_realtime.py."""
    if not phone:
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    national = digits[3:] if digits.startswith("972") else digits
    while national.startswith("0"):
        national = national[1:]
    if not national:
        return phone.strip()
    return f"+972{national}"


# Centralized model choice — swap here to try newer preview models.
# gemini-2.0-flash-live-001 is the current stable Live audio model.
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")

# Gemini Live WebSocket endpoint (BidiGenerateContent)
_GEMINI_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    "?key={api_key}"
)

# NOTE: Hardcoded Hebrew "BPM Studio" system instruction was removed here.
# Per multi-tenant isolation rules: no global fallback prompt may exist.
# Every voice call MUST resolve to an active agent_id with its own
# system_prompt. If resolution fails, the call is closed (fail closed).


# ── TwiML entry point ─────────────────────────────────────────────────────────

@router.post("/voice-gemini")
async def voice_gemini_entry(request: Request):
    """
    Twilio webhook — fetches agent config, stores call context, returns TwiML
    that opens a bidirectional Media Stream to the Gemini WebSocket endpoint.
    """
    form_data = await request.form()
    raw_to    = form_data.get("To", "")
    raw_from  = form_data.get("From", "")
    call_sid  = form_data.get("CallSid", "")

    norm_to   = _normalize_phone(raw_to)
    norm_from = _normalize_phone(raw_from)

    print(f"[GEMINI-VOICE] call_sid={call_sid} to={norm_to} from={norm_from}")

    # Fetch agent config for the destination number — always succeeds (returns safe default on miss)
    agent_cfg = await fetch_supabase_agent_config(norm_to)
    print(f"[GEMINI-VOICE] agent='{agent_cfg.get('client_name')}' fallback={agent_cfg.get('fallback_used')}")
    print(
        f"[ROUTE-AUDIT] route=voice_gemini_entry to={norm_to} "
        f"resolved_agent_id={agent_cfg.get('agent_id')} "
        f"resolved_client_id={agent_cfg.get('client_id')} "
        f"fallback_used={bool(agent_cfg.get('fallback_used'))} "
        f"knowledge_items_count={agent_cfg.get('knowledge_items_count', 0)}"
    )

    # Fail closed: unknown number / no active agent / empty prompt → reject call.
    if agent_cfg.get("fallback_used") or not agent_cfg.get("prompt_override"):
        print(f"[GEMINI-VOICE] ❌ No active agent for norm_to='{norm_to}' — returning error TwiML (fail closed)")
        err_response = VoiceResponse()
        err_response.say("מצטערים, אירעה שגיאה. נסו שוב מאוחר יותר.", language="he-IL")
        return Response(content=str(err_response), media_type="application/xml")

    # Store context keyed by CallSid so the WebSocket can find it without URL param issues
    _GEMINI_CALL_CONTEXT[call_sid] = {
        "to":         norm_to,
        "from":       norm_from,
        "agent_cfg":  agent_cfg,
        "created_at": datetime.now().timestamp(),
    }

    host       = request.url.hostname
    stream_url = f"wss://{host}/voice-ai/stream-gemini?call_sid={quote(call_sid, safe='')}"
    print(f"[GEMINI-VOICE] stream_url={stream_url}")

    response = VoiceResponse()
    connect  = Connect()
    connect.stream(url=stream_url)
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")


# ── WebSocket bridge ──────────────────────────────────────────────────────────

@router.websocket("/stream-gemini")
async def stream_gemini(twilio_ws: WebSocket, call_sid: str = Query(default="")):
    """
    Bridges a Twilio Media Stream to a Gemini Live session.

    Audio flow:
      Twilio (μ-law 8 kHz) → convert → Gemini Live (PCM16 16 kHz)
      Gemini Live (PCM16 24 kHz) → convert → Twilio (μ-law 8 kHz)
    """
    await twilio_ws.accept()
    print(f"[GEMINI-WS] Twilio connection accepted — call_sid={call_sid!r}")

    # ── Resolve call context — deferred until after Twilio start event ───────────
    # call_sid may be empty here because Twilio strips WebSocket query params.
    # We keep mutable refs and finalize them once the start event arrives.
    ctx          = _GEMINI_CALL_CONTEXT.get(call_sid, {})
    caller_phone = ctx.get("from", "")
    agent_cfg    = ctx.get("agent_cfg", {})
    webhook_url  = agent_cfg.get("webhook_url", "")
    client_id    = agent_cfg.get("client_id") or None
    client_name  = agent_cfg.get("client_name", "")

    if not GEMINI_API_KEY:
        print("[GEMINI-WS] ERROR: GEMINI_API_KEY is not set — closing Gemini stream")
        await twilio_ws.close()
        return

    # ── Capture Twilio stream_sid from the "start" event ─────────────────────
    stream_sid: str | None = None

    # Read messages until the Twilio "start" event so we have stream_sid
    # before we need to send outbound audio back into the call.
    _buffered_media: list[str] = []
    try:
        async for raw in twilio_ws.iter_text():
            evt = json.loads(raw)
            if evt["event"] == "start":
                stream_sid = evt["start"]["streamSid"]
                # Twilio strips query params from WebSocket URLs — read callSid from the start event
                if not call_sid:
                    call_sid = evt["start"].get("callSid", "")
                print(f"[GEMINI-WS] Start event received — stream_sid={stream_sid} call_sid={call_sid!r}")
                # Always re-resolve context after start event so call_sid is guaranteed correct
                ctx          = _GEMINI_CALL_CONTEXT.get(call_sid, {})
                caller_phone = ctx.get("from", "")
                agent_cfg    = ctx.get("agent_cfg", {})
                webhook_url  = agent_cfg.get("webhook_url", "")
                client_id    = agent_cfg.get("client_id") or None
                client_name  = agent_cfg.get("client_name", "")
                print(f"[GEMINI-WS] Agent context loaded — caller={caller_phone} client='{client_name}' webhook={'yes' if webhook_url else 'no'}")
                break
            elif evt["event"] == "media":
                # buffer any audio that arrives before start (rare but possible)
                _buffered_media.append(evt["media"]["payload"])
    except Exception as e:
        print(f"[GEMINI-WS] ERROR waiting for start event: {e}")
        await twilio_ws.close()
        return

    # ── Finalize prompt / voice / opening — always after start event ──────────
    # Fail closed: never use a hardcoded fallback prompt. The TwiML entry above
    # already rejects unknown numbers; this is a defense-in-depth check.
    if agent_cfg.get("fallback_used") or not agent_cfg.get("prompt_override"):
        print(
            f"[GEMINI-WS] ❌ No active agent prompt for client='{client_name}' "
            f"caller={caller_phone} — closing call (fail closed)"
        )
        try:
            await twilio_ws.close()
        except Exception:
            pass
        return

    base_prompt = agent_cfg["prompt_override"].replace("{{caller_phone}}", caller_phone)
    # If first_message is set, inject it as an opening instruction into the system prompt.
    # Do NOT use it as realtime_input — that would be interpreted as the caller speaking.
    first_message = (agent_cfg.get("first_message") or "").strip()
    if first_message:
        base_prompt = f"פתחי את השיחה תמיד עם המשפט הבא בדיוק:\n\"{first_message}\"\n\n{base_prompt}"
        print(f"[GEMINI-WS] first_message injected into system prompt")
    system_instruction = base_prompt
    print(f"[GEMINI-WS] Prompt source: Supabase config for '{client_name}'")
    print(
        f"[ROUTE-AUDIT] route=voice_gemini_ws to={agent_cfg.get('whatsapp_number') or 'voice'} "
        f"resolved_agent_id={agent_cfg.get('agent_id')} "
        f"resolved_client_id={agent_cfg.get('client_id') or client_id} "
        f"fallback_used=false "
        f"knowledge_items_count={agent_cfg.get('knowledge_items_count', 0)}"
    )

    # Valid Gemini Live prebuilt voice names — reject anything else (e.g. OpenAI leftovers)
    _GEMINI_VALID_VOICES = {"Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Schedar"}
    _raw_voice = (agent_cfg.get("voice") or "").strip()
    gemini_voice = _raw_voice if _raw_voice in _GEMINI_VALID_VOICES else "Zephyr"
    print(f"[GEMINI-WS] Voice: {gemini_voice} (requested={_raw_voice!r})")

    # Opening trigger: always a short neutral text so Gemini speaks first.
    # first_message content is already injected into the system prompt above.
    opening_trigger = "שלום"
    print(f"[GEMINI-WS] Opening trigger: {opening_trigger!r}")

    # ── Open Gemini Live WebSocket ────────────────────────────────────────────
    gemini_url = _GEMINI_WS_URL.format(api_key=GEMINI_API_KEY)
    try:
        gemini_ws = await websockets.connect(gemini_url, ping_interval=None)
        print(f"[GEMINI-WS] Gemini Live connected — model={GEMINI_LIVE_MODEL}")
    except Exception as e:
        print(f"[GEMINI-WS] ERROR: could not connect to Gemini Live: {e}")
        await twilio_ws.close()
        return

    # ── Send Gemini setup message ─────────────────────────────────────────────
    setup_msg = {
        "setup": {
            "model": f"models/{GEMINI_LIVE_MODEL}",
            "generation_config": {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {"voice_name": gemini_voice}
                    }
                },
            },
            "realtime_input_config": {
                "automatic_activity_detection": {
                    # Reduce silence threshold so Gemini responds faster after speech ends.
                    # Default is ~1000ms — 300ms is the practical minimum for phone audio.
                    "silence_duration_ms": 300,
                    # HIGH sensitivity: Gemini starts processing while user is still speaking,
                    # reducing perceived latency after speech ends.
                    "start_of_speech_sensitivity": "START_SENSITIVITY_HIGH",
                },
            },
            # Enable text transcripts alongside audio so we can extract lead data post-call
            "input_audio_transcription":  {},
            "output_audio_transcription": {},
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
        }
    }
    try:
        await gemini_ws.send(json.dumps(setup_msg))
        # Wait for Gemini's setup acknowledgement before streaming audio
        setup_ack = await asyncio.wait_for(gemini_ws.recv(), timeout=10.0)
        print(f"[GEMINI-WS] Gemini setup ack: {setup_ack[:200]}")
        # Trigger opening greeting via realtime_input (correct for gemini-3.1-flash-live-preview).
        # client_content is not supported for mid-session triggers on this model.
        await gemini_ws.send(json.dumps({
            "realtime_input": {"text": opening_trigger}
        }))
        print("[GEMINI-WS] Opening trigger sent via realtime_input")
    except asyncio.TimeoutError:
        print("[GEMINI-WS] ERROR: Gemini setup ack timed out — closing POC stream")
        await gemini_ws.close()
        await twilio_ws.close()
        return
    except Exception as e:
        print(f"[GEMINI-WS] ERROR during Gemini setup: {e}")
        await gemini_ws.close()
        await twilio_ws.close()
        return

    print("[GEMINI-WS] Gemini session initialised — bridging audio")

    # ── Shared state ──────────────────────────────────────────────────────────
    _first_inbound_logged  = False
    _first_outbound_logged = False
    _gemini_speaking       = False   # True while we are forwarding Gemini audio to Twilio
    _transcript_lines: list[str] = []  # accumulated conversation for post-call extraction
    _should_hangup         = False   # set when Maya signals end of call

    # Phrases in Maya's output that signal the call should end.
    # Keep these specific — common words like "שיהיה" trigger false positives mid-conversation.
    _HANGUP_PHRASES = ("להתראות", "המשך יום")

    # ── Forward Twilio audio → Gemini ─────────────────────────────────────────
    async def twilio_to_gemini_loop():
        nonlocal _first_inbound_logged

        # Discard audio buffered before the start event (line noise / ringback).
        # Replaying it races against the opening greeting and causes inconsistency.
        _buffered_media.clear()

        # Give Gemini time to start generating the opening greeting before
        # live caller audio flows in. Without this, early audio frames arrive
        # while Gemini is processing the text trigger and can disrupt the first turn.
        await asyncio.sleep(1.0)

        try:
            async for raw in twilio_ws.iter_text():
                evt = json.loads(raw)

                if evt["event"] == "media":
                    payload = evt["media"]["payload"]

                    if not _first_inbound_logged:
                        print("[GEMINI-WS] First inbound audio frame received from Twilio")
                        _first_inbound_logged = True

                    pcm_b64 = twilio_to_gemini(payload)
                    await gemini_ws.send(json.dumps({
                        "realtime_input": {
                            "audio": {"data": pcm_b64, "mimeType": "audio/pcm;rate=16000"}
                        }
                    }))

                elif evt["event"] == "stop":
                    print("[GEMINI-WS] Twilio stream stopped — closing Gemini WS to unblock gather")
                    try:
                        await gemini_ws.close()
                    except Exception:
                        pass
                    break

        except Exception as e:
            print(f"[GEMINI-WS] Twilio receiver error: {e}")
            try:
                await gemini_ws.close()
            except Exception:
                pass

    # ── Forward Gemini audio → Twilio ─────────────────────────────────────────
    async def gemini_to_twilio_loop():
        nonlocal _first_outbound_logged, _gemini_speaking, _should_hangup

        try:
            async for raw in gemini_ws:
                msg = json.loads(raw)

                # Gemini interrupted its own response (user barged in)
                if msg.get("serverContent", {}).get("interrupted"):
                    # Gemini's VAD detected user speech — clear Twilio's queued audio
                    print("[GEMINI-WS] Gemini interrupted — sent Twilio clear")
                    _gemini_speaking = False
                    if stream_sid:
                        await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                    continue

                server_content = msg.get("serverContent", {})

                # ── Capture transcripts for post-call extraction ──────────────
                input_t = server_content.get("inputTranscription", {})
                if input_t.get("text"):
                    _transcript_lines.append(f"לקוח: {input_t['text']}")

                output_t = server_content.get("outputTranscription", {})
                if output_t.get("text"):
                    _transcript_lines.append(f"מאיה: {output_t['text']}")
                    if any(p in output_t["text"] for p in _HANGUP_PHRASES):
                        _should_hangup = True
                        print(f"[GEMINI-WS] Hangup phrase detected in Maya output — will disconnect after turn")

                # Audio chunks from Gemini
                model_turn = server_content.get("modelTurn", {})
                parts      = model_turn.get("parts", [])

                for part in parts:
                    inline_data = part.get("inlineData", {})
                    mime        = inline_data.get("mimeType", "")
                    data        = inline_data.get("data", "")

                    # Gemini outputs PCM16 audio (24 kHz by default)
                    if data and "audio" in mime:
                        if not _first_outbound_logged:
                            print(f"[GEMINI-WS] First outbound audio frame received from Gemini — mimeType={mime!r}")
                            _first_outbound_logged = True

                        _gemini_speaking = True
                        ulaw_b64 = gemini_to_twilio(data)

                        if stream_sid:
                            await twilio_ws.send_json({
                                "event":     "media",
                                "streamSid": stream_sid,
                                "media":     {"payload": ulaw_b64},
                            })

                # Turn complete — Gemini done speaking this turn
                if server_content.get("turnComplete"):
                    _gemini_speaking = False
                    if _should_hangup:
                        print("[GEMINI-WS] Turn complete after hangup phrase — closing session")
                        await asyncio.sleep(2.5)  # let last audio frame reach Twilio
                        await gemini_ws.close()
                        break

        except Exception as e:
            print(f"[GEMINI-WS] Gemini receiver error: {e}")

    # ── Run both loops concurrently ───────────────────────────────────────────
    try:
        await asyncio.gather(twilio_to_gemini_loop(), gemini_to_twilio_loop())
    finally:
        print("[GEMINI-WS] Session ended — running end-of-call business logic")

        # ── Extract structured lead fields from transcript ────────────────────
        # IMPORTANT: only feed customer turns (lines prefixed "לקוח:") to the
        # extractor. Including assistant turns ("מאיה: ...") lets the LLM
        # latch onto names the assistant mentions (e.g., "קסניה") and save
        # them as the caller's name.
        extracted: dict = {}
        _customer_lines = [ln for ln in _transcript_lines if ln.startswith("לקוח:")]
        transcript_text = "\n".join(_customer_lines)
        if transcript_text.strip():
            print(f"[GEMINI-EXTRACT] Customer-only transcript ({len(_customer_lines)} lines) — running extraction")
            extracted = await _extract_lead_from_transcript(transcript_text, caller_phone)
            print(f"[GEMINI-EXTRACT] Result: {extracted}")
        else:
            print("[GEMINI-EXTRACT] No customer transcript captured — skipping extraction")

        # ── Lead persistence: always save a record to Supabase leads table ────
        if caller_phone:
            _topic = extracted.get("topic") or None
            _notes = extracted.get("notes") or None
            _summary_parts = []
            if _topic:
                _summary_parts.append(f"נושא: {_topic}")
            if _notes:
                _summary_parts.append(f"פרטים: {_notes}")
            _last_call_summary = " | ".join(_summary_parts) or None

            # ── Compute appointment_at from day + time extracted ──────────────
            _appointment_at = None
            _appt_day = extracted.get("appointment_day") or ""
            _appt_time = extracted.get("appointment_time") or ""
            if _appt_day and _appt_time:
                try:
                    from datetime import timedelta
                    _DAY_MAP = {
                        "ראשון": 6, "שני": 0, "שלישי": 1,
                        "רביעי": 2, "חמישי": 3, "שישי": 4, "שבת": 5,
                    }
                    _target_weekday = _DAY_MAP.get(_appt_day)
                    if _target_weekday is not None:
                        _now = datetime.utcnow()
                        _days_ahead = (_target_weekday - _now.weekday()) % 7
                        if _days_ahead == 0:
                            _days_ahead = 7  # always next occurrence
                        _appt_date = _now + timedelta(days=_days_ahead)
                        _h, _m = map(int, _appt_time.split(":"))
                        _appointment_at = _appt_date.replace(
                            hour=_h, minute=_m, second=0, microsecond=0
                        ).isoformat()
                        print(f"[GEMINI-LEAD] 📅 appointment_at={_appointment_at}")
                except Exception as _exc:
                    print(f"[GEMINI-LEAD] ⚠️ Failed to compute appointment_at: {_exc}")

            # Phone source of truth = normalized Twilio caller_phone.
            # NEVER use phone extracted from transcript (LLM can hallucinate or pick up
            # a number mentioned by the assistant or in casual conversation).
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
            print(f"[GEMINI-LEAD] ✅ Lead upserted — phone={caller_phone} name={extracted.get('name')} client_id={client_id}")
        else:
            print("[GEMINI-LEAD] ⚠️  No caller phone available — lead not saved")

        # ── Webhook delivery ──────────────────────────────────────────────────
        # Booking signal: Make.com uses booking_status to decide whether to fire
        # the post-call WhatsApp follow-up. Previously the payload only carried
        # name/topic/notes, so Make had no field to branch on and the follow-up
        # was never sent. appointment_at + booking_status make the trigger
        # explicit; followup_target_phone gives Make the WhatsApp destination.
        if caller_phone and webhook_url:
            _booking_status = "booked" if _appointment_at else "not_booked"
            webhook_payload = {
                "timestamp":             datetime.now().isoformat(),
                "source":                "voice_gemini",
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
            }
            print(
                f"[GEMINI-WEBHOOK] booking_status={_booking_status} "
                f"appointment_at={_appointment_at or '-'} "
                f"target={caller_phone}"
            )
            await _send_gemini_webhook(webhook_url, webhook_payload)
        elif not webhook_url:
            print("[GEMINI-WEBHOOK] ⚠️  No webhook URL in agent config — skipping")

        # ── Hang up Twilio call via REST API ─────────────────────────────────
        # Closing the WebSocket alone does not always terminate the Twilio call.
        # Explicitly end it via the REST API so the caller is disconnected.
        if call_sid:
            try:
                twilio_client = _get_twilio_client()
                await asyncio.to_thread(
                    lambda: twilio_client.calls(call_sid).update(status="completed")
                )
                print(f"[GEMINI-HANGUP] ✅ Twilio call {call_sid} terminated via REST API")
            except Exception as exc:
                print(f"[GEMINI-HANGUP] ⚠️  Could not terminate call via REST: {exc}")

        # ── Context cleanup ───────────────────────────────────────────────────
        _GEMINI_CALL_CONTEXT.pop(call_sid, None)

        # ── Close connections ─────────────────────────────────────────────────
        try:
            await gemini_ws.close()
        except Exception:
            pass
        try:
            await twilio_ws.close()
        except Exception:
            pass

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
from app.integrations.twilio_client import _get_client as _get_twilio_client

router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


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


async def _send_gemini_webhook(webhook_url: str, payload: dict) -> None:
    """POST payload to webhook URL. Never raises — errors are logged only."""
    if not webhook_url:
        print("[GEMINI-WEBHOOK] ⚠️  No webhook URL configured — skipping")
        return
    print(f"[GEMINI-WEBHOOK] ▶ POST {webhook_url}")
    print(f"[GEMINI-WEBHOOK] 📦 payload: {json.dumps(payload, ensure_ascii=False)}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            print(f"[GEMINI-WEBHOOK] ← HTTP {resp.status_code}")
            resp.raise_for_status()
            print("[GEMINI-WEBHOOK] ✅ delivered successfully")
    except Exception as exc:
        print(f"[GEMINI-WEBHOOK] ❌ delivery failed: {exc}")

# Centralized model choice — swap here to try newer preview models.
# gemini-2.0-flash-live-001 is the current stable Live audio model.
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")

# Gemini Live WebSocket endpoint (BidiGenerateContent)
_GEMINI_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    "?key={api_key}"
)

# ── Hebrew demo system instruction for Maya ───────────────────────────────────

_SYSTEM_INSTRUCTION = """\
את מאיה, נציגת שירות של סטודיו לריקוד. את ישראלית לחלוטין — תדברי עם מבטא ישראלי מההתחלה ועד סוף השיחה, ללא שום השפעה אנגלית.

המטרה שלך היא לנהל שיחה טבעית עם לקוחות, להבין אם הם מחפשים:
1. ריקוד לבת מצווה
2. שיעור ניסיון לסטודיו

תמיד תשאלי קודם על בת מצווה ורק אחר כך על שיעור ניסיון.

חוקים חשובים:
* דברי בעברית טבעית, לא רשמית מדי
* תדברי כמו בן אדם, עם זרימה
* אל תתני תשובות ארוכות מדי
* תמיד תשאלי שאלה אחת כל פעם
* אם הלקוח מתבלבל או קוטע — תזרמי ותמשיכי
* אם את צריכה שנייה לחשוב — תוסיפי מילת גישור טבעית כמו "אממ", "רגע", "אוקיי" לפני שאת ממשיכה. זה גורם לשיחה להישמע אנושית יותר

מידע על הסטודיו:
* מתקיימים שיעורים בימי ראשון ורביעי בלבד

חלוקה לפי גיל:
* גילאי 6–8: בשעה 17:00
* גילאי 9–12: בשעה 17:45
* גילאי 13–16: בשעה 18:30

מהלך שיחה:

שלב 1:
תשאלי: האם מדובר בריקוד לבת מצווה או בשיעור ניסיון?

שלב 2:
אם מדובר בבת מצווה:
* תשאלי תאריך
* תשאלי איפה האירוע
* תובילי להשארת פרטים

אם מדובר בשיעור ניסיון:
* תשאלי גיל
* תתאימי יום ושעה לפי הגיל בלבד
* תשאלי איזה יום נוח (ראשון או רביעי)

שלב 3:
להוביל לאיסוף פרטים:
* שם הילדה
* טלפון של ההורה

חוקים קריטיים:
* אל תציעי שעות שלא קיימות
* אל תדלגי על השאלה של בת מצווה
* אל תסיימי שיחה בלי לנסות לאסוף טלפון
* אל תישמעי מכירתית מדי

פתיחת השיחה (חובה — תמיד המשפט הראשון):
"היי, הגעתם לסטודיו BPM, מדברת מאיה. אני כאן לעזור! אתם מתעניינים בריקוד לבת מצווה או בשיעור ניסיון?"

אחרי הפתיחה:
* אם הלקוח אומר בת מצווה — המשיכי למסלול בת מצווה
* אם הלקוח אומר שיעור ניסיון — המשיכי למסלול שיעור ניסיון
* אם הלקוח לא ברור או מתלבט — עזרי לו להבין מה יותר רלוונטי עבורו

מטרה עסקית (קריטי):
המטרה שלך היא לא רק לענות יפה — אלא להוביל כל שיחה לסיום שבו יש לך לפחות:
* שם הילדה
* מספר טלפון של ההורה

אם אין לך את הפרטים האלה — השיחה לא הושלמה.

חוקי סגירה:
* תמיד תנסי להגיע לשלב איסוף פרטים
* אם הלקוח מתלבט — תמשיכי בעדינות להוביל לשם
* אם הלקוח אומר "אני אבדוק" — תעני: "ברור! רק כדי שאוכל לשלוח לך פרטים מסודרים, אפשר מספר טלפון?"
* אם השיחה מתקרבת לסיום ואין לך טלפון — תשאלי בצורה טבעית: "איך אפשר לחזור אליך עם הפרטים?"
* אם הלקוח כבר זרם — תובילי ישירות: "איך קוראים לילדה?" ואז "ומה המספר טלפון?"

סגנון הסגירה:
* לא אגרסיבי
* לא לוחץ
* אבל כן מוביל
* תמיד שאלה אחת בכל פעם
"""


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

    # ── Resolve call context set by voice_gemini_entry ────────────────────────
    ctx          = _GEMINI_CALL_CONTEXT.get(call_sid, {})
    caller_phone = ctx.get("from", "")
    agent_cfg    = ctx.get("agent_cfg", {})

    # webhook_url is pre-computed in agent_config: set only when lead_delivery_method=="webhook"
    # Do NOT fall back to lead_delivery_target — it may be a phone number (whatsapp method)
    webhook_url  = agent_cfg.get("webhook_url", "")
    client_id    = agent_cfg.get("client_id") or None
    client_name  = agent_cfg.get("client_name", "")

    # System prompt: use Supabase config when available, fall back to hardcoded
    if agent_cfg.get("prompt_override") and not agent_cfg.get("fallback_used"):
        system_instruction = agent_cfg["prompt_override"].replace("{{caller_phone}}", caller_phone)
        print(f"[GEMINI-WS] Using Supabase prompt for '{client_name}'")
    else:
        system_instruction = _SYSTEM_INSTRUCTION
        print(f"[GEMINI-WS] Using hardcoded fallback prompt (no Supabase config for '{client_name}')")

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
                # Twilio strips query params from WebSocket URLs — read callSid from the start event instead
                if not call_sid:
                    call_sid = evt["start"].get("callSid", "")
                    print(f"[GEMINI-WS] call_sid resolved from start event: {call_sid!r}")
                    # Re-resolve context now that we have the real call_sid
                    ctx          = _GEMINI_CALL_CONTEXT.get(call_sid, {})
                    caller_phone = ctx.get("from", "")
                    agent_cfg    = ctx.get("agent_cfg", {})
                    # webhook_url is pre-computed in agent_config: set only when lead_delivery_method=="webhook"
    # Do NOT fall back to lead_delivery_target — it may be a phone number (whatsapp method)
    webhook_url  = agent_cfg.get("webhook_url", "")
                    client_id    = agent_cfg.get("client_id") or None
                    client_name  = agent_cfg.get("client_name", "")
                    if agent_cfg.get("prompt_override") and not agent_cfg.get("fallback_used"):
                        system_instruction = agent_cfg["prompt_override"].replace("{{caller_phone}}", caller_phone)
                        print(f"[GEMINI-WS] Prompt updated from context: using Supabase prompt for '{client_name}'")
                    else:
                        system_instruction = _SYSTEM_INSTRUCTION
                    print(f"[GEMINI-WS] Context resolved — caller={caller_phone} client='{client_name}' webhook={'yes' if webhook_url else 'no'}")
                print(f"[GEMINI-WS] Twilio stream started — stream_sid={stream_sid}")
                break
            elif evt["event"] == "media":
                # buffer any audio that arrives before start (rare but possible)
                _buffered_media.append(evt["media"]["payload"])
    except Exception as e:
        print(f"[GEMINI-WS] ERROR waiting for start event: {e}")
        await twilio_ws.close()
        return

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
                        "prebuilt_voice_config": {"voice_name": "Zephyr"}
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
            "realtime_input": {"text": "שלום"}
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
        nonlocal _first_outbound_logged, _gemini_speaking

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

                # Audio chunks from Gemini
                server_content = msg.get("serverContent", {})
                model_turn     = server_content.get("modelTurn", {})
                parts          = model_turn.get("parts", [])

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

        except Exception as e:
            print(f"[GEMINI-WS] Gemini receiver error: {e}")

    # ── Run both loops concurrently ───────────────────────────────────────────
    try:
        await asyncio.gather(twilio_to_gemini_loop(), gemini_to_twilio_loop())
    finally:
        print("[GEMINI-WS] Session ended — running end-of-call business logic")

        # ── Lead persistence: always save a record to Supabase leads table ────
        # Minimum guaranteed fields: phone + source. Name/topic not yet available
        # (Gemini Live has no function-call mechanism for structured extraction).
        if caller_phone:
            await save_lead({
                "phone":     caller_phone,
                "source":    "voice",
                "status":    "new",
                "client_id": client_id,
            })
            print(f"[GEMINI-LEAD] ✅ Lead upserted for phone={caller_phone} client_id={client_id}")
        else:
            print("[GEMINI-LEAD] ⚠️  No caller phone available — lead not saved")

        # ── Webhook delivery: fire Make.com with basic call metadata ──────────
        # Structured fields (name, topic, notes) will be empty until function-call
        # extraction is implemented; downstream Make scenarios should handle that.
        if caller_phone and webhook_url:
            webhook_payload = {
                "timestamp":    datetime.now().isoformat(),
                "source":       "voice_gemini",
                "client":       client_name,
                "caller_phone": caller_phone,
                "call_sid":     call_sid,
                # Placeholder fields — empty until structured extraction is added
                "name":         "",
                "phone_number": caller_phone,
                "topic":        "",
                "notes":        "",
            }
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

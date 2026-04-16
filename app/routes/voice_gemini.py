"""
Gemini Live voice POC — isolated Twilio → Gemini Live bridge.

Routes registered under the /voice-ai prefix (see main.py):
  POST /voice-ai/voice-gemini   — TwiML entry point (point a Twilio number here)
  WS   /voice-ai/stream-gemini  — bidirectional Twilio Media Stream ↔ Gemini Live

This is a POC only. Do NOT modify or share state with the OpenAI realtime path.
"""

import asyncio
import json
import os

import websockets
from fastapi import APIRouter, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect

from app.utils.audio_gemini import twilio_to_gemini, gemini_to_twilio

router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

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
את מאיה, נציגת שירות של סטודיו לריקוד.

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
    Twilio webhook — returns TwiML that opens a bidirectional Media Stream
    to the Gemini POC WebSocket endpoint.
    """
    host       = request.url.hostname
    stream_url = f"wss://{host}/voice-ai/stream-gemini"
    print(f"[GEMINI-VOICE] incoming call → stream_url={stream_url}")

    response = VoiceResponse()
    connect  = Connect()
    # <Stream> with bidirectional mode so Twilio sends AND receives audio
    connect.stream(url=stream_url)
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")


# ── WebSocket bridge ──────────────────────────────────────────────────────────

@router.websocket("/stream-gemini")
async def stream_gemini(twilio_ws: WebSocket):
    """
    Bridges a Twilio Media Stream to a Gemini Live session.

    Audio flow:
      Twilio (μ-law 8 kHz) → convert → Gemini Live (PCM16 16 kHz)
      Gemini Live (PCM16 24 kHz) → convert → Twilio (μ-law 8 kHz)
    """
    await twilio_ws.accept()
    print("[GEMINI-WS] Twilio connection accepted")

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
                    # Default is ~1000ms — 400ms feels natural on a phone call.
                    "silence_duration_ms": 400,
                },
            },
            "system_instruction": {
                "parts": [{"text": _SYSTEM_INSTRUCTION}]
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

        # Replay any audio buffered before the start event
        for payload in _buffered_media:
            pcm_b64 = twilio_to_gemini(payload)
            await gemini_ws.send(json.dumps({
                "realtime_input": {
                    "audio": {"data": pcm_b64, "mimeType": "audio/pcm;rate=16000"}
                }
            }))
        _buffered_media.clear()

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
                    print("[GEMINI-WS] Twilio stream stopped")
                    break

        except Exception as e:
            print(f"[GEMINI-WS] Twilio receiver error: {e}")

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
        print("[GEMINI-WS] Session ended — closing connections")
        try:
            await gemini_ws.close()
        except Exception:
            pass
        try:
            await twilio_ws.close()
        except Exception:
            pass

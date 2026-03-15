import os
import json
import asyncio
import websockets
import httpx
from fastapi import APIRouter, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup
from datetime import datetime

router = APIRouter()

raw_api_key = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_KEY = raw_api_key.strip().replace("\u2028", "").replace("\u2029", "")
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
CALENDAR_ID = os.getenv("CALENDAR_ID", "")

current_date = datetime.now().strftime("%Y-%m-%d")


def normalize_israeli_phone(phone: str) -> str:
    """
    Normalize a phone number to E.164 format for Israel (+972).
    Removes spaces/dashes, strips leading zeros, and prefixes +972.
    """
    if not phone:
        return phone

    # Keep only digits
    digits = "".join(ch for ch in phone if ch.isdigit())

    # Strip country code if present
    if digits.startswith("972"):
        national = digits[3:]
    else:
        national = digits

    # Strip leading zeros from national part
    while national.startswith("0"):
        national = national[1:]

    if not national:
        return phone.strip()

    return f"+972{national}"


async def process_agency_lead(lead_data: dict) -> bool:
    """
    Send collected lead data to the configured Make.com webhook URL.
    Uses the MAKE_WEBHOOK_URL environment variable configured in Railway.
    """
    if not MAKE_WEBHOOK_URL:
        print("⚠️ MAKE_WEBHOOK_URL is not configured — skipping lead webhook.")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                MAKE_WEBHOOK_URL,
                json=lead_data,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            print(
                f"✅ Lead sent to Make.com webhook | status={response.status_code}"
            )
            return True
    except httpx.HTTPStatusError as exc:
        print(
            f"❌ Make.com webhook HTTP error {exc.response.status_code}: {exc.response.text}"
        )
    except Exception as exc:
        print(f"❌ Failed to send lead to Make.com webhook: {exc}")

    return False


# Insurance-agent demo: operational rules for voice AI — no dialogue simulation
SYSTEM_PROMPT = f"""OPERATIONAL RULES — STRICT COMPLIANCE REQUIRED.

IDENTITY:
You are Maya, the digital secretary of Roi, an independent insurance agent in Israel. Current date: {current_date}. You speak Hebrew in a short, friendly, natural tone. You are female.

VOICE INTERACTION RULES (MANDATORY):
1. NEVER simulate, predict, or generate the caller's responses. You do not speak for the caller. You do not answer your own questions. You do not invent what the caller said or will say.
2. NEVER INVENT OR ASSUME A CALLER'S NAME. If you do not yet know the caller's name, you MUST ask: "סליחה, עם מי יש לי את הכבוד?" Do NOT address the caller by any name unless they have explicitly told you their name in this call. Using a made-up name is strictly forbidden.
3. You are an interactive voice assistant. Output ONLY your own lines. Ask exactly ONE question at a time, then STOP. Wait in silence for the caller to respond. Do not continue speaking until the caller has responded.
4. Your style is warm, human and empathetic. You sound like a real assistant helping Roi, not like a robot reading a form. Use short, natural Hebrew fillers like "אהמ...", "אוקיי", "סבבה", "מעולה", "הבנתי", "אהלן" when appropriate — they make you sound natural and attentive. If the caller is describing a claim, difficulty or problem, you may say things like "מצטערת לשמוע" or "זה באמת לא נעים" before continuing. If the caller mentions the word "תביעה" or describes an insurance claim, respond with empathy first, for example: "אהמ... אוי, אני מצטערת לשמוע. בוא נראה איך אפשר לעזור", ואז המשיכי בעדינות לשאלות.
5. Speak at a natural, relaxed pace, with short sentences. Do not sound like you are reading a list. Keep things conversational and flowing, but still concise.
6. CONVERSATION START: As soon as the call connects, you MUST speak first without waiting for the caller. Your first utterance in the conversation MUST be exactly:
   "שלום, אני מאיה המזכירה הדיגיטלית של רועי. רועי לא פנוי כרגע. באיזה נושא אוכל לסייע?"
   Then STOP and wait for the caller.

CALL FLOW FOR INSURANCE DEMO:
7. After the greeting, you may ask at most THREE short questions:
   - Name: בקשי את השם הפרטי של המתקשר. אם אינך יודעת את שמו, שאלי: "סליחה, עם מי יש לי את הכבוד?"
   - Phone number: בקשי את מספר הטלפון לחזרה, אם חסר או לא ברור.
   - Short explanation: בקשי הסבר קצר על מה הוא צריך מרועי (למשל ביטוח רכב, דירה, חיים וכדומה).
8. Keep each question short, simple, and natural in Hebrew. Do not over‑explain. Do not ask follow‑up questions beyond these three topics.
9. Once you have the caller's name, phone number, and a short explanation (or as much as they are willing to give), you MUST say exactly:
   "תודה רבה. אני מעבירה לרועי את הפרטים עכשיו, והוא יחזור אליך בהקדם."
   Say this once in a warm, confident tone.
10. After saying the closing sentence, call the tool process_agency_lead with the collected details (name, phone number, topic, and any important notes).
11. After process_agency_lead completes, say: "מעולה, רשמתי הכל. יש עוד משהו שאוכל לעזור בו לפני שנסגור?" Then STOP and wait for the caller to respond.
12. If the caller indicates there is nothing more (e.g., says "לא", "זהו", "תודה", "הכל בסדר", "לא תודה", or any similar closing), say: "שיהיה יום מצוין, ביי!" and then IMMEDIATELY call the tool end_call to hang up. Do NOT say anything further after the goodbye.
"""
VOICE = "shimmer"

@router.post("/voice")
async def voice_entry(request: Request):
    # שליפת נתוני השיחה מטוויליו
    form_data = await request.form()
    caller_phone = form_data.get('From', 'לא ידוע')
    
    response = VoiceResponse()
    connect = Connect()
    host = request.url.hostname
    # אנחנו מעבירים את המספר כפרמטר בכתובת ה-WebSocket
    connect.stream(url=f'wss://{host}/voice-ai/stream?caller_phone={caller_phone}')
    response.append(connect)
    response.append(Hangup())
    return Response(content=str(response), media_type="application/xml")

@router.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    print("✅ Twilio connection accepted")
    
    caller_phone = twilio_ws.query_params.get('caller_phone', 'לא ידוע')
    
    if not OPENAI_API_KEY:
        print("❌ Missing OpenAI API Key")
        await twilio_ws.close()
        return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}

    # התיקון הקריטי של ההדרים נמצא כאן, מיושר מושלם
    async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:
        print("✅ Connected to OpenAI Realtime API")
        
        FINAL_PROMPT = SYSTEM_PROMPT + f"""
SESSION PARAMETERS:
- Caller phone (Twilio From): {caller_phone}.
- If the caller does not provide a different number, you may confirm or repeat this number with them.
- Remember: maximum 3 questions (name, phone number, short explanation) and then the exact closing sentence and end_call.
"""

        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.75,
                    "prefix_padding_ms": 500,
                    "silence_duration_ms": 1000,
                },
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": VOICE,
                "instructions": FINAL_PROMPT,
                "modalities": ["audio", "text"],
                "temperature": 0.7,
                "tools": [
                    {
                        "type": "function",
                        "name": "process_agency_lead",
                        "description": "שולחת את פרטי הפונה למערכת של רועי כדי שרועי יוכל לחזור אליו.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "השם הפרטי של הפונה",
                                },
                                "phone_number": {
                                    "type": "string",
                                    "description": "מספר הטלפון לחזרה (אם לא ידוע, אפשר להשתמש במספר של השיחה)",
                                },
                                "topic": {
                                    "type": "string",
                                    "description": "הנושא שבגללו הפונה צריך את רועי (למשל ביטוח רכב, דירה וכו׳)",
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "מידע נוסף שיכול לעזור לרועי להבין את הבקשה",
                                },
                            },
                            "required": ["name", "phone_number", "topic"],
                            "additionalProperties": False,
                        },
                    },
                    {
                        "type": "function",
                        "name": "end_call",
                        "description": "מנתקת את השיחה",
                        "parameters": {"type": "object", "properties": {}},
                    },
                ],
            },
        }

        await openai_ws.send(json.dumps(session_update))
        # Trigger the model to speak first immediately according to SYSTEM_PROMPT
        await openai_ws.send(json.dumps({"type": "response.create"}))

        stream_sid = None
        is_ai_speaking = False
        speech_started_at = None
        _SILENCE_MS = 1000   # must match silence_duration_ms in session config above
        _MIN_SPEECH_MS = 300  # caller must sustain speech this long before interrupting AI

        async def receive_from_twilio():
            nonlocal stream_sid
            try:
                async for message in twilio_ws.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        print(f"📡 Stream started with SID: {stream_sid}")
                    elif data['event'] == 'media':
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }))
            except Exception as e:
                print(f"⚠️ Twilio Receiver Error: {e}")

        async def receive_from_openai():
            nonlocal is_ai_speaking, speech_started_at
            try:
                async for message in openai_ws:
                    response = json.loads(message)
                    event_type = response.get('type')

                    # Stream AI audio to Twilio and mark AI as speaking
                    if event_type == 'response.audio.delta':
                        is_ai_speaking = True
                        if stream_sid:
                            await twilio_ws.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": response['delta']}
                            })
                        continue

                    # AI finished speaking — reset state
                    if event_type in ('response.audio.done', 'response.cancelled'):
                        is_ai_speaking = False
                        speech_started_at = None
                        continue

                    # VAD: caller started speaking — record timestamp, do NOT interrupt yet.
                    # Waiting for speech_stopped lets us measure actual duration before acting,
                    # which filters out noise bursts, echo, and brief sounds.
                    if event_type == 'input_audio_buffer.speech_started':
                        speech_started_at = asyncio.get_event_loop().time()
                        continue

                    # VAD: caller finished speaking — now decide whether to interrupt.
                    # speech_stopped fires after silence_duration_ms of quiet, so elapsed time
                    # from speech_started = actual_speech_duration + silence_duration_ms.
                    # Only interrupt if: AI is currently speaking AND speech was >= _MIN_SPEECH_MS.
                    if event_type == 'input_audio_buffer.speech_stopped':
                        if speech_started_at is not None and is_ai_speaking:
                            elapsed_ms = (asyncio.get_event_loop().time() - speech_started_at) * 1000
                            speech_ms = elapsed_ms - _SILENCE_MS
                            if speech_ms >= _MIN_SPEECH_MS:
                                if stream_sid:
                                    await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                                await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        speech_started_at = None
                        continue

                    if event_type == "response.function_call_arguments.done":
                        func_name = response["name"]
                        args = json.loads(response["arguments"])
                        print(f"🛠️ Calling function: {func_name} with args: {args}")

                        if func_name == "process_agency_lead":
                            lead_payload = {
                                "source": "voice_realtime",
                                "caller_phone_twilio": caller_phone,
                                "name": args.get("name"),
                                "phone_number": args.get("phone_number") or caller_phone,
                                "topic": args.get("topic"),
                                "notes": args.get("notes", ""),
                            }
                            await process_agency_lead(lead_payload)

                        if func_name == "end_call":
                            print("👋 Maya requested end_call — disconnecting")
                            await asyncio.sleep(2)
                            await twilio_ws.close()
                            break
            except Exception as e:
                print(f"⚠️ OpenAI Receiver Error: {e}")

        await asyncio.gather(receive_from_twilio(), receive_from_openai())
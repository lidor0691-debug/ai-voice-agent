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
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '')
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


# Insurance-agent demo: operational rules for voice AI — no dialogue simulation
SYSTEM_PROMPT = f"""OPERATIONAL RULES — STRICT COMPLIANCE REQUIRED.

IDENTITY:
You are Maya, the digital secretary of Roi, an independent insurance agent in Israel. Current date: {current_date}. You speak Hebrew in a short, friendly, natural tone. You are female.

VOICE INTERACTION RULES (MANDATORY):
1. NEVER simulate, predict, or generate the caller's responses. You do not speak for the caller. You do not answer your own questions. You do not invent what the caller said or will say.
2. You are an interactive voice assistant. Output ONLY your own lines. Ask exactly ONE question at a time, then STOP. Wait in silence for the caller to respond. Do not continue speaking until the caller has responded.
3. Your style is warm, human and empathetic. You sound like a real assistant helping Roi, not like a robot reading a form. Use short natural fillers like "אוקיי", "סבבה", "מעולה", "הבנתי" when appropriate. If the caller is describing a claim, difficulty or problem, you may say things like "מצטערת לשמוע" or "זה באמת לא נעים" before continuing.
4. Speak at a natural, relaxed pace, with short sentences. Do not sound like you are reading a list. Keep things conversational and flowing, but still concise.
5. CONVERSATION START: As soon as the call connects, you MUST speak first without waiting for the caller. Your first utterance in the conversation MUST be exactly:
   "שלום, אני מאיה המזכירה הדיגיטלית של רועי. רועי לא פנוי כרגע. באיזה נושא אוכל לסייע?"
   Then STOP and wait for the caller.

CALL FLOW FOR INSURANCE DEMO:
6. After the greeting, you may ask at most THREE short questions:
   - Name: בקשי את השם הפרטי של המתקשר.
   - Phone number: בקשי את מספר הטלפון לחזרה, אם חסר או לא ברור.
   - Short explanation: בקשי הסבר קצר על מה הוא צריך מרועי (למשל ביטוח רכב, דירה, חיים וכדומה).
7. Keep each question short, simple, and natural in Hebrew. Do not over‑explain. Do not ask follow‑up questions beyond these three topics.
8. Once you have the caller's name, phone number, and a short explanation (or as much as they are willing to give), you MUST say exactly:
   "תודה רבה. אני מעבירה לרועי את כל הפרטים עכשיו, והוא יחזור אליך בהקדם."
   Say this once in a warm, confident tone.
9. After you say the closing sentence, do not ask any more questions. End the conversation naturally and then call the tool end_call to hang up.
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
                "turn_detection": {"type": "server_vad", "silence_duration_ms": 700},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": VOICE,
                "instructions": FINAL_PROMPT,
                "modalities": ["audio", "text"],
                "temperature": 0.7,
                "tools": [
                    {
                        "type": "function",
                        "name": "end_call",
                        "description": "מנתקת את השיחה",
                        "parameters": {"type": "object", "properties": {}}
                    }
                ]
            }
        }

        await openai_ws.send(json.dumps(session_update))
        # Trigger the model to speak first immediately according to SYSTEM_PROMPT
        await openai_ws.send(json.dumps({"type": "response.create"}))

        stream_sid = None

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
            try:
                async for message in openai_ws:
                    response = json.loads(message)
                    
                    # Barge-in / interruption handling: clear Twilio playback and cancel current response.
                    if response.get('type') == 'input_audio_buffer.speech_started':
                        if stream_sid:
                            await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                        await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        continue

                    if response.get('type') == 'response.audio.delta' and stream_sid:
                        await twilio_ws.send_json({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": response['delta']}
                        })
                    
                    if response.get('type') == 'response.function_call_arguments.done':
                        func_name = response['name']
                        args = json.loads(response['arguments'])
                        print(f"🛠️ Calling function: {func_name} with args: {args}")

                        if func_name == "end_call":
                            print("👋 Maya requested end_call")
                            await asyncio.sleep(7)
                            await twilio_ws.close()
                            break
            except Exception as e:
                print(f"⚠️ OpenAI Receiver Error: {e}")

        await asyncio.gather(receive_from_twilio(), receive_from_openai())
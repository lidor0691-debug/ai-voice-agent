import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# טעינת משתני סביבה - עם ניקוי תווים נסתרים
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "").strip()
CALENDAR_ID = "e1f69352b339ba76f5776a42037f94705d3340aac25a78b1c7f85bd05f5bf931@group.calendar.google.com"

SYSTEM_PROMPT = """את מאיה מהונדה Big Boys Toys. את חדה ומקצועית. 
עלייך לאסוף תמיד: שם, טלפון, דגם וזמן לפני אישור תור. 
דברי בנקבה על עצמך ובזכר ללקוח."""

VOICE = "shimmer"

@app.post("/voice")
async def voice_entry(request: Request):
    response = VoiceResponse()
    connect = Connect()
    host = request.url.hostname
    connect.stream(url=f'wss://{host}/stream')
    response.append(connect)
    response.append(Hangup())
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    print("DEBUG: Twilio Connected") # יופיע בלוגים כשתתחיל שיחה

    if not OPENAI_API_KEY:
        print("ERROR: OpenAI API Key is missing!")
        await twilio_ws.close(); return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    
    try:
        async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:
            print("DEBUG: Connected to OpenAI Realtime")
            
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 1000},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_PROMPT,
                    "modalities": ["audio", "text"],
                    "temperature": 0.8,
                    "tools": [
                        {
                            "type": "function",
                            "name": "check_availability",
                            "description": "בודק זמינות",
                            "parameters": { "type": "object", "properties": { "date": {"type": "string"} } }
                        },
                        {
                            "type": "function",
                            "name": "book_garage_service",
                            "description": "רישום למוסך",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "bike_model": {"type": "string"},
                                    "service_type": {"type": "string"},
                                    "mileage": {"type": "string"},
                                    "appointment_time": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "service_type", "appointment_time"]
                            }
                        }
                    ],
                    "tool_choice": "auto"
                }
            }
            await openai_ws.send(json.dumps(session_update))

            async def receive_from_twilio():
                try:
                    async for message in twilio_ws.iter_text():
                        data = json.loads(message)
                        if data['event'] == 'media':
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))
                except Exception as e: print(f"Twilio Receive Error: {e}")

            async def receive_from_openai():
                try:
                    async for openai_message in openai_ws:
                        response_data = json.loads(openai_message)
                        if response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                            await twilio_ws.send_text(json.dumps({"event": "media", "media": {"payload": response_data['delta']}}))
                        elif response_data['type'] == 'response.function_call_arguments.done':
                            func_name = response_data['name']
                            args = json.loads(response_data['arguments'])
                            if MAKE_WEBHOOK_URL:
                                async with httpx.AsyncClient() as client:
                                    args['action'] = func_name
                                    await client.post(MAKE_WEBHOOK_URL, json=args, timeout=10)
                                    print(f"DEBUG: Webhook sent for {func_name}")
                except Exception as e: print(f"OpenAI Receive Error: {e}")

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
    finally:
        print("DEBUG: Connection Closed")

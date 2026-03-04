import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# טעינת משתני סביבה וניקוי תווים נסתרים
raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
CALENDAR_ID = "e1f69352b339ba76f5776a42037f94705d3340aac25a78b1c7f85bd05f5bf931@group.calendar.google.com"

# המוח של מאיה - שילוב של הדינמיקה המקורית עם חוקי ברזל
SYSTEM_PROMPT = """את מאיה, מנהלת השירות והמכירות של הונדה Big Boys Toys. 
את בחורה חדה, חולה על אופנועים, ומדברת בגובה העיניים.

חוקים בל יעברו (למניעת טעויות):
1. מגדר: את אישה (אני יכולה, רשמתי). את פונה ללקוח אך ורק בלשון זכר (אתה, תרצה).
2. דגמים: את מומחית לדגמים כמו CB500X, Africa Twin, Forza.
3. איסוף נתונים: אל תנחשי! את חייבת לשאול ולקבל: שם, טלפון, דגם אופנוע וקילומטראז' (KM).
4. סגנון: דברי כמו חברה שמבינה עניין ("בטח", "וואלה"). אל תהיי רשמית מדי.
5. מטרה: תני הרגשה של שירות VIP. בסוף תגידי: 'מעולה, הכל רשום ומחכה לך במוסך'."""

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
    if not OPENAI_API_KEY:
        await twilio_ws.close(); return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    
    try:
        async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:
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
                            "name": "book_garage_service",
                            "description": "קביעת תור למוסך",
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
                                "required": ["name", "phone", "bike_model", "service_type", "mileage", "appointment_time"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "get_bike_quote",
                            "description": "שולח הצעת מחיר בווטסאפ",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "bike_model": {"type": "string"},
                                    "price": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "price"]
                            }
                        }
                    ],
                    "tool_choice": "auto"
                }
            }
            await openai_ws.send(json.dumps(session_update))

            stream_sid = None

            async def receive_from_twilio():
                nonlocal stream_sid
                try:
                    async for message in twilio_ws.iter_text():
                        data = json.loads(message)
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {"instructions": "תפתחי הכי טבעי וזכר: 'היי, הגעת ל-Big Boys Toys, אני מאיה. מה קורה? איך אני יכולה לעזור?'"}
                            }))
                        elif data['event'] == 'media':
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))
                except Exception: pass

            async def receive_from_openai():
                try:
                    async for openai_message in openai_ws:
                        response_data = json.loads(openai_message)
                        
                        if response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                            await twilio_ws.send_text(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": response_data['delta']}}))
                        elif response_data['type'] == 'input_audio_buffer.speech_started':
                            await twilio_ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
                        
                        elif response_data['type'] == 'response.function_call_arguments.done':
                            func_name = response_data['name']
                            call_id = response_data['call_id']
                            args = json.loads(response_data['arguments'])
                            
                            if MAKE_WEBHOOK_URL:
                                async with httpx.AsyncClient() as client:
                                    args['action'] = func_name
                                    args['calendar_id'] = CALENDAR_ID
                                    await client.post(MAKE_WEBHOOK_URL, json=args, timeout=15)
                                
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {"type": "function_call_output", "call_id": call_id, "output": "{\"status\":\"success\"}"}
                            }))
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                except Exception: pass

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
    except Exception: pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

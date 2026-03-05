import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# ניקוי מפתחות ומשתנים - סטרילי לגמרי
raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
CALENDAR_ID = "e1f69352b339ba76f5776a42037f94705d3340aac25a78b1c7f85bd05f5bf931@group.calendar.google.com"

# ה-Prompt המדויק: 12,000 ק"מ, מגדר קשוח, ושעה מדויקת
SYSTEM_PROMPT = """את מאיה מהונדה Big Boys Toys. בחורה חדה ומקצועית.
חוקי ברזל:
1. מגדר: את אישה. פני ללקוח אך ורק בזכר (אתה, תרצה). אל תפתחי בנקבה לעולם!
2. לוגיקה: 1,000 ק"מ = הרצה. 12,000 ק"מ = טיפול תקופתי. תגידי את זה ללקוח.
3. דיוק: אל תאשרי תור בלי שעה מדויקת (למשל 09:00). אל תסכימי ל"בוקר".
4. אימות: חזרי על מספר הקילומטראז' ששמעת כדי לוודא דיוק.
5. סיום: הבטיחי הודעת סיכום בווטסאפ בסוף השיחה."""

VOICE = "shimmer"

@app.post("/voice")
async def voice_entry(request: Request):
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f'wss://{request.url.hostname}/stream')
    response.append(connect)
    response.append(Hangup())
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    
    try:
        async with websockets.connect(url, additional_headers=headers) as openai_ws:
            # עדכון סשן - הגדרות מהירות ודיוק
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 800},
                    "instructions": SYSTEM_PROMPT,
                    "voice": VOICE,
                    "temperature": 0.6,
                    "tools": [
                        {
                            "type": "function",
                            "name": "book_garage_service",
                            "description": "קביעת תור למוסך",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, "service_type": {"type": "string"},
                                    "mileage": {"type": "string"}, "appointment_time": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "service_type", "mileage", "appointment_time"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "save_test_ride",
                            "description": "שומר רכיבת מבחן",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, "appointment_time": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "appointment_time"]
                            }
                        }
                    ]
                }
            }))

            stream_sid = None

            async def to_openai():
                nonlocal stream_sid
                try:
                    async for msg in twilio_ws.iter_text():
                        data = json.loads(msg)
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {"instructions": "תפתחי בברכה חמה וקצרה בזכר: 'היי, הגעת להונדה, אני מאיה. איך אני יכולה לעזור?'"}
                            }))
                        elif data['event'] == 'media':
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))
                except: pass

            async def from_openai():
                try:
                    async for msg in openai_ws:
                        data = json.loads(msg)
                        if data.get('type') == 'response.audio.delta':
                            await twilio_ws.send_text(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": data['delta']}}))
                        
                        if data.get('type') == 'input_audio_buffer.speech_started':
                            await twilio_ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))

                        if data.get('type') == 'response.function_call_arguments.done':
                            args = json.loads(data['arguments'])
                            if MAKE_WEBHOOK_URL:
                                async with httpx.AsyncClient() as client:
                                    args['action'] = data['name']
                                    await client.post(MAKE_WEBHOOK_URL, json=args, timeout=10)
                            
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {"type": "function_call_output", "call_id": data['call_id'], "output": "{\"status\":\"success\"}"}
                            }))
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                except: pass

            await asyncio.gather(to_openai(), from_openai())
    except: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5050)))

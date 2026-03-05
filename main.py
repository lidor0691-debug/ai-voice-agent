import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup
from datetime import datetime

app = FastAPI()

raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# חישוב תאריך נוכחי כדי שמאיה תדע לחשב מתי זה "מחר" או "יום חמישי"
current_date = datetime.now().strftime("%Y-%m-%d")

SYSTEM_PROMPT = f"""את מאיה מנהלת השירות והמכירות של הונדה Big Boys Toys. 
היום התאריך הוא: {current_date}.

חוקי ברזל:
1. מגדר: את אישה. פני ללקוח תמיד בזכר (אתה, תרצה). הברכה הראשונה חייבת להיות בזכר.
2. לוגיקת טיפולים: 1,000 ק"מ = הרצה. 12,000 ק"מ = תקופתי. תאמתי את המספר ששמעת.
3. תתעקשי על שעה מדויקת (למשל 09:00), אל תאשרי סתם "בוקר".
4. *חוק זמן קריטי*: כשאת מפעילה פונקציה, פורמט השדה appointment_time חייב להיות תמיד YYYY-MM-DD HH:MM (למשל 2026-03-05 10:30). לעולם אל תעבירי מילים כמו "מחר" או "יום חמישי".
5. דגמים ומכירות: את מכירה את הדגמים CB500X, Africa Twin, Forza, X-ADV. אם הלקוח שואל על מחירים או רוצה נסיעת מבחן, תזרמי איתו, תני הערכת מחיר כללית ותציעי לקבוע נסיעת מבחן או לשלוח הצעה לווטסאפ."""

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
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 800},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "instructions": SYSTEM_PROMPT,
                    "voice": VOICE,
                    "temperature": 0.6,
                    "tools": [
                        {
                            "type": "function",
                            "name": "book_garage_service",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, "service_type": {"type": "string"},
                                    "mileage": {"type": "string"}, 
                                    "appointment_time": {"type": "string", "description": "Must be strictly in YYYY-MM-DD HH:MM format"}
                                },
                                "required": ["name", "phone", "bike_model", "service_type", "mileage", "appointment_time"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "save_test_ride",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, 
                                    "appointment_time": {"type": "string", "description": "Must be strictly in YYYY-MM-DD HH:MM format"}
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
                                "response": {"instructions": "תגידי משפט קצר: 'היי, הגעת להונדה, אני מאיה. איך אפשר לעזור?'"}
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

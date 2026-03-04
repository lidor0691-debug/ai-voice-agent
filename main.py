import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# משתני סביבה
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "").strip()

SYSTEM_PROMPT = """את מאיה, מנהלת השירות של הונדה Big Boys Toys. 
את חייבת לאסוף: שם, טלפון, דגם אופנוע וזמן לפני שאת מאשרת תור. 
דברי בנקבה על עצמך ובזכר ללקוח. תהיי חדה, מקצועית וחמה."""

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
            # הגדרת סשן
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "instructions": SYSTEM_PROMPT,
                    "voice": "shimmer",
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 1000},
                    "tools": [
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
                                    "appointment_time": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "service_type", "appointment_time"]
                            }
                        }
                    ]
                }
            }))

            # משפט פתיחה
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {"instructions": "תגידי: 'היי, הגעת להונדה Big Boys Toys, אני מאיה. איך אפשר לעזור?'"}
            }))

            stream_sid = None

            async def to_openai():
                nonlocal stream_sid
                async for msg in twilio_ws.iter_text():
                    data = json.loads(msg)
                    if data['event'] == 'start': stream_sid = data['start']['streamSid']
                    if data['event'] == 'media':
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))

            async def from_openai():
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
                                await client.post(MAKE_WEBHOOK_URL, json=args, timeout=5)
                        
                        await openai_ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {"type": "function_call_output", "call_id": data['call_id'], "output": "{\"status\":\"success\"}"}
                        }))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

            await asyncio.gather(to_openai(), from_openai())

    except Exception: pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

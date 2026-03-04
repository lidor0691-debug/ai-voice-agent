import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "").strip()

SYSTEM_PROMPT = "את מאיה מהונדה Big Boys Toys. תעני בקצרה ובחום. תמיד תשאלי לשם הלקוח."

@app.post("/voice")
async def voice_entry(request: Request):
    resp = VoiceResponse()
    connect = Connect()
    connect.stream(url=f'wss://{request.url.hostname}/stream')
    resp.append(connect)
    resp.append(Hangup())
    return Response(content=str(resp), media_type="application/xml")

@app.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    print("LOG: Twilio connected")
    
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    
    try:
        async with websockets.connect(url, additional_headers=headers) as openai_ws:
            print("LOG: OpenAI connected successfully")
            
            # עדכון סשן בסיסי
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "instructions": SYSTEM_PROMPT,
                    "voice": "shimmer",
                    "turn_detection": {"type": "server_vad"}
                }
            }))

            # הודעת פתיחה כפויה
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {"instructions": "תגידי מיד: 'שלום, הגעת להונדה, אני מאיה. איך עוזרים?'"}
            }))

            stream_sid = None

            async def from_twilio():
                nonlocal stream_sid
                async for msg in twilio_ws.iter_text():
                    data = json.loads(msg)
                    if data['event'] == 'start': 
                        stream_sid = data['start']['streamSid']
                        print(f"LOG: Stream SID: {stream_sid}")
                    if data['event'] == 'media':
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))

            async def from_openai():
                async for msg in openai_ws:
                    data = json.loads(msg)
                    if data['type'] == 'response.audio.delta':
                        await twilio_ws.send_text(json.dumps({
                            "event": "media", "streamSid": stream_sid, "media": {"payload": data['delta']}
                        }))
                    if data['type'] == 'error':
                        print(f"OPENAI ERROR: {data['error']['message']}")

            await asyncio.gather(from_twilio(), from_openai())

    except Exception as e:
        print(f"LOG CRITICAL ERROR: {e}")

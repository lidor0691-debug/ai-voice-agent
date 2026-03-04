import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# שליפת משתנים
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

SYSTEM_PROMPT = "את מאיה מהונדה. דברי עברית. תהיי קצרה וחממה. תשאלי לשם הלקוח."

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
    print("LOG: Twilio Connected")
    
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    
    try:
        async with websockets.connect(url, additional_headers=headers) as openai_ws:
            print("LOG: OpenAI Connected")
            
            # הגדרת סשן ראשונית
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "instructions": SYSTEM_PROMPT,
                    "voice": "shimmer",
                    "turn_detection": {"type": "server_vad"}
                }
            }))

            stream_sid = None

            async def from_twilio():
                nonlocal stream_sid
                try:
                    async for msg in twilio_ws.iter_text():
                        data = json.loads(msg)
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"LOG: Stream Started: {stream_sid}")
                        if data['event'] == 'media' and openai_ws.open:
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }))
                except Exception as e: print(f"Twilio Error: {e}")

            async def from_openai():
                try:
                    async for msg in openai_ws:
                        data = json.loads(msg)
                        if data.get('type') == 'response.audio.delta' and stream_sid:
                            await twilio_ws.send_text(json.dumps({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": data['delta']}
                            }))
                        if data.get('type') == 'error':
                            print(f"!!! OPENAI ERROR: {data['error']['message']}")
                except Exception as e: print(f"OpenAI Error: {e}")

            await asyncio.gather(from_twilio(), from_openai())

    except Exception as e:
        print(f"LOG CRITICAL: {e}")
    finally:
        print("LOG: Connection Closed")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

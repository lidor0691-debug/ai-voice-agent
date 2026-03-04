import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response, HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# בדיקת דופק - כדי שנדע שהשרת עובד
@app.get("/")
async def health_check():
    return HTMLResponse(content="<h1>Maya Server is LIVE</h1>", status_code=200)

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
            
            # עדכון סשן
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "instructions": "את מאיה מהונדה. דברי עברית קצרה וחמה.",
                    "voice": "shimmer",
                    "turn_detection": {"type": "server_vad"}
                }
            }))

            stream_sid = None

            async def to_openai():
                nonlocal stream_sid
                async for msg in twilio_ws.iter_text():
                    data = json.loads(msg)
                    if data['event'] == 'start': stream_sid = data['start']['streamSid']
                    if data['event'] == 'media' and openai_ws.open:
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))

            async def from_openai():
                async for msg in openai_ws:
                    data = json.loads(msg)
                    if data.get('type') == 'response.audio.delta' and stream_sid:
                        await twilio_ws.send_text(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": data['delta']}}))

            await asyncio.gather(to_openai(), from_openai())
    except Exception as e:
        print(f"LOG ERROR: {e}")

if __name__ == "__main__":
    import uvicorn
    # Railway חייב את ה-Port הזה
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

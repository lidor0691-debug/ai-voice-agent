import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# משתני סביבה - נקיים
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

SYSTEM_PROMPT = "את מאיה מהונדה Big Boys Toys. דברי עברית, תהיי חדה וחמה. תמיד תשאלי לשם הלקוח."

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
    
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    
    async with websockets.connect(url, additional_headers=headers) as openai_ws:
        # 1. עדכון סשן מיידי
        await openai_ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "instructions": SYSTEM_PROMPT,
                "voice": "shimmer",
                "turn_detection": {"type": "server_vad"}
            }
        }))

        # 2. פקודת פתיחה
        await openai_ws.send(json.dumps({
            "type": "response.create",
            "response": {"instructions": "תפתחי בברכה: 'היי, הגעת להונדה, אני מאיה. איך אפשר לעזור?'"}
        }))

        stream_sid = None

        async def to_openai():
            nonlocal stream_sid
            async for msg in twilio_ws.iter_text():
                data = json.loads(msg)
                if data['event'] == 'start':
                    stream_sid = data['start']['streamSid']
                if data['event'] == 'media' and openai_ws.open:
                    await openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": data['media']['payload']
                    }))

        async def from_openai():
            async for msg in openai_ws:
                data = json.loads(msg)
                if data.get('type') == 'response.audio.delta' and stream_sid:
                    await twilio_ws.send_text(json.dumps({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": data['delta']}
                    }))
                if data.get('type') == 'input_audio_buffer.speech_started':
                    await twilio_ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))

        await asyncio.gather(to_openai(), from_openai())

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

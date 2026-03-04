import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# שליפת מפתח OpenAI מהסביבה
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# נתיב לבדיקת דופק - כדי שלא תקבל 404
@app.get("/")
async def root():
    return JSONResponse(content={"status": "Maya is LIVE and waiting for calls"}, status_code=200)

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
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(url, additional_headers=headers) as openai_ws:
            print("LOG: OpenAI Connected")
            
            # 1. הגדרת סשן בסיסית ונקייה
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "instructions": "את מאיה מהונדה Big Boys Toys. דברי עברית חדה וקצרה. תמיד תשאלי לשם הלקוח בסוף.",
                    "voice": "shimmer",
                    "turn_detection": {"type": "server_vad"}
                }
            }))

            # 2. משפט פתיחה מחייב
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "instructions": "תפתחי בברכה: 'שלום, הגעת להונדה Big Boys Toys, אני מאיה. איך אפשר לעזור?'"
                }
            }))

            stream_sid = None

            async def to_openai():
                nonlocal stream_sid
                async for msg in twilio_ws.iter_text():
                    data = json.loads(msg)
                    if data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        print(f"LOG: Stream SID: {stream_sid}")
                    elif data['event'] == 'media' and openai_ws.open:
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

            await asyncio.gather(to_openai(), from_openai())

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        print("LOG: Connection Closed")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

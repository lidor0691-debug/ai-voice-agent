import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# שליפת מפתח - מוודא שאין רווחים מיותרים
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "").strip()

SYSTEM_PROMPT = "את מאיה, מנהלת השירות של הונדה. דברי בנקבה על עצמך ובזכר ללקוח. את חייבת לאסוף שם וטלפון."

@app.post("/voice")
async def voice_entry(request: Request):
    response = VoiceResponse()
    connect = Connect()
    # שימוש בכתובת הציבורית של השרת
    connect.stream(url=f'wss://{request.url.hostname}/stream')
    response.append(connect)
    response.append(Hangup())
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    print("LOG: Twilio connected")
    
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(url, additional_headers=headers) as openai_ws:
            print("LOG: OpenAI connected")
            
            # 1. הגדרת סשן
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "instructions": SYSTEM_PROMPT,
                    "voice": "shimmer",
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "turn_detection": {"type": "server_vad"}
                }
            }))

            # 2. פקודת פתיחה מיידית
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {"instructions": "תגידי מיד: 'שלום, הגעת להונדה, אני מאיה. איך אפשר לעזור?'"}
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
                    if data.get('type') == 'response.audio.delta':
                        await twilio_ws.send_text(json.dumps({
                            "event": "media", 
                            "streamSid": stream_sid, 
                            "media": {"payload": data['delta']}
                        }))
                    if data.get('type') == 'error':
                        print(f"OPENAI ERROR: {data['error']['message']}")

            await asyncio.gather(to_openai(), from_openai())

    except Exception as e:
        print(f"LOG ERROR: {e}")
    finally:
        print("LOG: Connection closed")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

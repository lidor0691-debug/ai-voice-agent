import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect

app = FastAPI()

# ניקוי המפתח כדי למנוע קריסות
raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""

SYSTEM_PROMPT = "אתה עוזרת אדמיניסטרטיבית חכמה לקליניקה. תעני בעברית, קצר, שירותי ולעניין. אל תחפרי."
VOICE = "shimmer"  # קול נשי המותאם למודל ה-Realtime של OpenAI

@app.post("/voice")
async def voice_entry(request: Request):
    """כאן אנחנו רק עונים לשיחה ומעבירים אותה לערוץ שידור חי (WebSocket)"""
    response = VoiceResponse()
    connect = Connect()
    
    # מושכים את הכתובת של Railway וממירים מ-https ל-wss (WebSocket Secure)
    host = request.url.hostname
    connect.stream(url=f'wss://{host}/stream')
    
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    """הצינור החי: מחבר בין הסמארטפון של הלקוח ישירות למוח של OpenAI"""
    await twilio_ws.accept()
    print("Twilio connected to server.")
    
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY is missing!")
        await twilio_ws.close()
        return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        # פותחים חיבור בזמן אמת ל-OpenAI
        async with websockets.connect(openai_url, extra_headers=headers) as openai_ws:
            print("Connected to OpenAI Realtime API.")
            
            # 1. הגדרת סשן (זיהוי קול, פורמט אודיו, והנחיות)
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad"},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_PROMPT,
                    "modalities": ["audio", "text"],
                    "temperature": 0.7,
                }
            }
            await openai_ws.send(json.dumps(session_update))

            stream_sid = None

            # משימה 1: לקבל אודיו מהלקוח (Twilio) ולהעביר ל-AI
            async def receive_from_twilio():
                nonlocal stream_sid
                try:
                    async for message in twilio_ws.iter_text():
                        data = json.loads(message)
                        
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            # מכריחים את הסוכנת להתחיל לדבר מיד כשהשיחה נפתחת
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "instructions": "תגידי מיד ובטבעיות: 'שלום, הגעתם לקליניקה. איך אפשר לעזור?'"
                                }
                            }))
                            
                        elif data['event'] == 'media':
                            # הלקוח מדבר - מעבירים את חתיכות הקול ל-AI
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                            
                        elif data['event'] == 'stop':
                            print("Call disconnected by user.")
                            break
                except Exception as e:
                    print(f"Twilio receive error: {e}")

            # משימה 2: לקבל אודיו מה-AI ולהעביר ללקוח
            async def receive_from_openai():
                try:
                    async for openai_message in openai_ws:
                        response_data = json.loads(openai_message)
                        
                        if response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                            # ה-AI מדבר - דוחפים את הקול לטלפון של הלקוח
                            audio_payload = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": response_data['delta']
                                }
                            }
                            await twilio_ws.send_text(json.dumps(audio_payload))
                            
                        elif response_data['type'] == 'input_audio_buffer.speech_started':
                            # הלקוח התפרץ! עוצרים את הדיבור של ה-AI מיד
                            clear_msg = {
                                "event": "clear",
                                "streamSid": stream_sid
                            }
                            await twilio_ws.send_text(json.dumps(clear_msg))
                            
                except Exception as e:
                    print(f"OpenAI receive error: {e}")

            # מריצים את שתי הפעולות במקביל (דופלקס מלא)
            await asyncio.gather(receive_from_twilio(), receive_from_openai())
            
    except Exception as e:
        print(f"Connection error: {e}")
        await twilio_ws.close()

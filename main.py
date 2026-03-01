import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect

app = FastAPI()

raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""

# פרומפט חדש: מגדיר לה מטרות עסקיות ברורות
SYSTEM_PROMPT = """אתה עוזרת אדמיניסטרטיבית חכמה לקליניקה.
המטרה שלך היא לאסוף פרטים מהלקוח: שם, מספר טלפון, וסיבת הפנייה.
תשאלי שאלות קצרות וטבעיות, אחת בכל פעם, כדי לאסוף את המידע. 
ברגע שיש לך את כל 3 הפרטים, תפעילי מיד את הפונקציה save_lead. 
לאחר מכן תאשרי ללקוח שהפרטים נרשמו ושנחזור אליו בהקדם כדי לקבוע תור.
דברי בעברית, קצר ולעניין. אל תחפרי."""

VOICE = "shimmer"

@app.post("/voice")
async def voice_entry(request: Request):
    response = VoiceResponse()
    connect = Connect()
    host = request.url.hostname
    connect.stream(url=f'wss://{host}/stream')
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    
    if not OPENAI_API_KEY:
        await twilio_ws.close()
        return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:
            
            # 1. הגדרת הסשן עם "כלי" (Tool) לאיסוף הלידים
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
                    "tools": [{
                        "type": "function",
                        "name": "save_lead",
                        "description": "שומר את פרטי הלקוח לאחר איסוף מלא של שם, טלפון וסיבת הפנייה",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "שם הלקוח"},
                                "phone": {"type": "string", "description": "מספר הטלפון של הלקוח"},
                                "reason": {"type": "string", "description": "סיבת הפנייה או סוג הטיפול המבוקש"}
                            },
                            "required": ["name", "phone", "reason"]
                        }
                    }],
                    "tool_choice": "auto"
                }
            }
            await openai_ws.send(json.dumps(session_update))

            stream_sid = None

            async def receive_from_twilio():
                nonlocal stream_sid
                try:
                    async for message in twilio_ws.iter_text():
                        data = json.loads(message)
                        
                        if data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "instructions": "תגידי מיד ובטבעיות: 'שלום, הגעתם לקליניקה. איך אפשר לעזור?'"
                                }
                            }))
                            
                        elif data['event'] == 'media':
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                            
                        elif data['event'] == 'stop':
                            break
                except Exception as e:
                    print(f"Twilio receive error: {e}")

            async def receive_from_openai():
                try:
                    async for openai_message in openai_ws:
                        response_data = json.loads(openai_message)
                        
                        if response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                            audio_payload = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": response_data['delta']}
                            }
                            await twilio_ws.send_text(json.dumps(audio_payload))
                            
                        elif response_data['type'] == 'input_audio_buffer.speech_started':
                            clear_msg = {
                                "event": "clear",
                                "streamSid": stream_sid
                            }
                            await twilio_ws.send_text(json.dumps(clear_msg))
                        
                        # ----- לוגיקת הלידים: ברגע שה-AI חילץ נתונים -----
                        elif response_data['type'] == 'response.function_call_arguments.done':
                            call_id = response_data['call_id']
                            args = json.loads(response_data['arguments'])
                            
                            # מדפיסים את הליד ללוגים של השרת שלנו
                            print("\n" + "="*40)
                            print("🎯 ליד חדש נכנס!")
                            print(f"שם: {args.get('name')}")
                            print(f"טלפון: {args.get('phone')}")
                            print(f"סיבה: {args.get('reason')}")
                            print("="*40 + "\n")

                            # סוגרים מעגל מול ה-AI (מאשרים לה שהמידע נשמר בהצלחה)
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": json.dumps({"status": "success"})
                                }
                            }))
                            
                            # נותנים פקודה ל-AI להמשיך לדבר עם הלקוח
                            await openai_ws.send(json.dumps({"type": "response.create"}))

                except Exception as e:
                    print(f"OpenAI receive error: {e}")

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
            
    except Exception as e:
        print(f"Connection error: {e}")
        await twilio_ws.close()

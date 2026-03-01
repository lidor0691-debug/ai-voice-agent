import os
import json
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""

# פרומפט מעודכן - כולל התייחסות למגדר ולניתוק השיחה בסוף
SYSTEM_PROMPT = """את עוזרת אדמיניסטרטיבית חכמה ונשית לקליניקה.
חוק ברזל: פני למתקשר תמיד בלשון זכר (לדוגמה: "איך אני יכולה לעזור לך?", "מה השם שלך?", "רשמתי את הפרטים שלך").
המטרה שלך היא לאסוף פרטים מהלקוח: שם, מספר טלפון, וסיבת הפנייה.
תשאלי שאלות קצרות וטבעיות, אחת בכל פעם, כדי לאסוף את המידע. 
ברגע שיש לך את כל 3 הפרטים, תפעילי מיד את הפונקציה save_lead. 
לאחר קבלת אישור שהליד נשמר, תגידי ללקוח: "מעולה, הפרטים נשמרו. נחזור אליך בהקדם לקביעת תור. המשך יום נעים!", ומיד לאחר מכן הפעילי את הפונקציה end_call כדי לנתק את השיחה.
דברי בעברית, קצר ולעניין. אל תחפרי."""

VOICE = "alloy"  # הוחלף לקול שנוטה להישמע קצת יותר טוב בעברית

@app.post("/voice")
async def voice_entry(request: Request):
    response = VoiceResponse()
    connect = Connect()
    host = request.url.hostname
    connect.stream(url=f'wss://{host}/stream')
    response.append(connect)
    
    # פקודת ניתוק קשיחה ל-Twilio ברגע שה-WebSocket נסגר
    response.append(Hangup())
    
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
            
            # הגדרת הכלים (Tools) - הוספנו פונקציית ניתוק
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
                    "tools": [
                        {
                            "type": "function",
                            "name": "save_lead",
                            "description": "שומר את פרטי הלקוח לאחר איסוף מלא של שם, טלפון וסיבת הפנייה",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "שם הלקוח"},
                                    "phone": {"type": "string", "description": "מספר הטלפון של הלקוח"},
                                    "reason": {"type": "string", "description": "סיבת הפנייה"}
                                },
                                "required": ["name", "phone", "reason"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "end_call",
                            "description": "מנתק את השיחה. יש להפעיל רק אחרי פרידה מהלקוח.",
                            "parameters": {"type": "object", "properties": {}}
                        }
                    ],
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
                                    "instructions": "תגידי מיד: 'שלום, הגעתם לקליניקה. מדברת נציגה וירטואלית, איך אני יכולה לעזור לך?'"
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
                except Exception:
                    pass

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
                        
                        # --- טיפול בפונקציות (ליד + ניתוק) ---
                        elif response_data['type'] == 'response.function_call_arguments.done':
                            call_id = response_data['call_id']
                            function_name = response_data['name']
                            args = json.loads(response_data['arguments']) if response_data.get('arguments') else {}
                            
                            if function_name == "save_lead":
                                print("\n" + "="*40)
                                print("🎯 ליד חדש נכנס!")
                                print(f"שם: {args.get('name')}")
                                print(f"טלפון: {args.get('phone')}")
                                print(f"סיבה: {args.get('reason')}")
                                print("="*40 + "\n")

                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps({"status": "success"})
                                    }
                                }))
                                await openai_ws.send(json.dumps({"type": "response.create"}))
                                
                            elif function_name == "end_call":
                                print("📞 מנתק את השיחה לפי בקשת ה-AI...")
                                await twilio_ws.close()
                                break

                except Exception as e:
                    print(f"OpenAI error: {e}")

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
            
    except Exception as e:
        print(f"Connection error: {e}")
        try:
            await twilio_ws.close()
        except:
            pass

import os
import json
import asyncio
import websockets
import httpx
from fastapi import APIRouter, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup
from datetime import datetime

router = APIRouter()

raw_api_key = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '')
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
CALENDAR_ID = os.getenv("CALENDAR_ID", "")

current_date = datetime.now().strftime("%Y-%m-%d")

# משלבים את האופי האנושי שאהבת עם חוקי הברזל למערכות
SYSTEM_PROMPT = f"""את מאיה מנהלת השירות והמכירות של הונדה Big Boys Toys.
היום התאריך הוא: {current_date}.

חוקי ברזל לניהול השיחה:
1. מגדר: את אישה. פני ללקוח אך ורק בזכר (אתה, תרצה). הברכה הראשונה תמיד בזכר.
2. לוגיקת טיפולים: 1,000 ק"מ = הרצה. 12,000 ק"מ = תקופתי. תאמתי את המספר ששמעת.
3. *חוק זמן קריטי לקלנדר*: כשאת מפעילה פונקציה, appointment_time חייב להיות אך ורק YYYY-MM-DD HH:MM (למשל 2026-03-05 09:00). אל תאשרי שעה מעורפלת.
4. מכירות: CB500X, Africa Twin, Forza, X-ADV. תזרמי בטבעיות אם שואלים שאלות, אל תהיי רובוטית.
"""
VOICE = "shimmer"

@router.post("/voice")
async def voice_entry(request: Request):
    # שליפת נתוני השיחה מטוויליו
    form_data = await request.form()
    caller_phone = form_data.get('From', 'לא ידוע')
    
    response = VoiceResponse()
    connect = Connect()
    host = request.url.hostname
    # אנחנו מעבירים את המספר כפרמטר בכתובת ה-WebSocket
    connect.stream(url=f'wss://{host}/voice-ai/stream?caller_phone={caller_phone}')
    response.append(connect)
    response.append(Hangup())
    return Response(content=str(response), media_type="application/xml")

@router.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    print("✅ Twilio connection accepted")
    
    caller_phone = twilio_ws.query_params.get('caller_phone', 'לא ידוע')
    
    if not OPENAI_API_KEY:
        print("❌ Missing OpenAI API Key")
        await twilio_ws.close()
        return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}

    # התיקון הקריטי של ההדרים נמצא כאן, מיושר מושלם
    async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:
        print("✅ Connected to OpenAI Realtime API")
        
        FINAL_PROMPT = SYSTEM_PROMPT + f"""
חוקי ברזל:
1. מספר הטלפון של הלקוח הוא {caller_phone}. השתמשי בו תמיד בשדה ה-phone.
2. חובה לשאול לשם הלקוח לפני קביעת התור.
3. איסוף נתונים: דגם, קילומטראז' וסוג טיפול (תקופתי/הרצה/תיקון).
4. ניתוק: בסיום האישור ואחרי שאמרת להתראות, הפעילי מיד את end_call.
"""

        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad", "silence_duration_ms": 700},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": VOICE,
                "instructions": FINAL_PROMPT,
                "modalities": ["audio", "text"],
                "temperature": 0.7,
                "tools": [
                    {
                        "type": "function",
                        "name": "book_garage_service",
                        "description": "קובע תור לטיפול במוסך",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "שם הלקוח"},
                                "phone": {"type": "string", "description": "מספר טלפון"},
                                "bike_model": {"type": "string", "description": "דגם האופנוע"},
                                "service_type": {"type": "string", "description": "סוג הטיפול"},
                                "mileage": {"type": "string", "description": "קילומטראז'"},
                                "appointment_time": {"type": "string", "description": "YYYY-MM-DD HH:MM"}
                            },
                            "required": ["name", "phone", "bike_model", "service_type", "mileage", "appointment_time"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "end_call",
                        "description": "מנתקת את השיחה",
                        "parameters": {"type": "object", "properties": {}}
                    }
                ]
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
                        print(f"📡 Stream started with SID: {stream_sid}")
                    elif data['event'] == 'media':
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }))
            except Exception as e:
                print(f"⚠️ Twilio Receiver Error: {e}")

        async def receive_from_openai():
            try:
                async for message in openai_ws:
                    response = json.loads(message)
                    
                    if response.get('type') == 'response.audio.delta' and stream_sid:
                        await twilio_ws.send_json({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": response['delta']}
                        })
                    
                    if response.get('type') == 'response.function_call_arguments.done':
                        func_name = response['name']
                        args = json.loads(response['arguments'])
                        print(f"🛠️ Calling function: {func_name} with args: {args}")
                        
                        if func_name == "book_garage_service":
                            async with httpx.AsyncClient() as client:
                                args['action'] = func_name
                                await client.post(MAKE_WEBHOOK_URL, json=args, timeout=10)
                            
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {"type": "function_call_output", "call_id": response['call_id'], "output": "{\"status\":\"success\"}"}
                            }))
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                        
                        elif func_name == "end_call":
                            print("👋 Maya requested end_call")
                            await asyncio.sleep(2)
                            await twilio_ws.close()
                            break
                except Exception as e:
                    print(f"⚠️ OpenAI Receiver Error: {e}")

        await asyncio.gather(receive_from_twilio(), receive_from_openai())
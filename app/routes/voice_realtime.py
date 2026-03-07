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
    
    # שליפת מספר הטלפון מהכתובת
    caller_phone = twilio_ws.query_params.get('caller_phone', 'לא ידוע')
    
    if not OPENAI_API_KEY:
        await twilio_ws.close()
        return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    
    # הזרקת המספר לתוך הפרומפט
    CURRENT_SYSTEM_PROMPT = SYSTEM_PROMPT + f"\nמספר הטלפון שממנו הלקוח מחייג כרגע הוא: {caller_phone}. אם הוא אומר 'המספר שממנו אני מחייג' או משהו דומה, תשתמשי במספר הזה בלי לשאול אותו שוב."
    
    try:
        async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:
            session_update = {
                "type": "session.update",
                "session": {
                    "instructions": CURRENT_SYSTEM_PROMPT, # שים לב לשינוי כאן
                    # ... שאר ההגדרות (turn_detection, tools וכו') נשארות אותו דבר
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 700}, # התזמון המקורי שאהבת
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_PROMPT,
                    "modalities": ["audio", "text"],
                    "temperature": 0.8, # החזרנו את היצירתיות והאנושיות
                    "tools": [
                        {
                            "type": "function",
                            "name": "book_garage_service",
                            "description": "קביעת תור למוסך",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, 
                                    "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, 
                                    "service_type": {"type": "string"},
                                    "mileage": {"type": "string"}, 
                                    "appointment_time": {"type": "string", "description": "Strictly YYYY-MM-DD HH:MM format"}
                                },
                                "required": ["name", "phone", "bike_model", "service_type", "mileage", "appointment_time"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "save_test_ride",
                            "description": "קביעת נסיעת מבחן",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, 
                                    "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, 
                                    "appointment_time": {"type": "string", "description": "Strictly YYYY-MM-DD HH:MM format"}
                                },
                                "required": ["name", "phone", "bike_model", "appointment_time"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "end_call",
                            "description": "מנתק את השיחה",
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
                                "response": {"instructions": "תפתחי בחום: 'היי, הגעת להונדה Big Boys Toys, אני מאיה. על איזה כלי אתה רוצה לרכוב היום או שצריך טיפול?'"}
                            }))
                        elif data['event'] == 'media':
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))
                except Exception: pass

            async def receive_from_openai():
                try:
                    async for openai_message in openai_ws:
                        response_data = json.loads(openai_message)
                        
                        if response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                            await twilio_ws.send_text(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": response_data['delta']}}))
                        elif response_data['type'] == 'input_audio_buffer.speech_started':
                            await twilio_ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
                        
                        elif response_data['type'] == 'response.function_call_arguments.done':
                            func_name = response_data['name']
                            call_id = response_data['call_id']
                            args = json.loads(response_data['arguments'])
                            
                            if func_name in ["save_test_ride", "book_garage_service"]:
                                if MAKE_WEBHOOK_URL:
                                    async with httpx.AsyncClient() as client:
                                        args['action'] = func_name
                                        args['calendar_id'] = CALENDAR_ID
                                        await client.post(MAKE_WEBHOOK_URL, json=args, timeout=10)
                                
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {"type": "function_call_output", "call_id": call_id, "output": "{\"status\":\"success\", \"message\":\"הפעולה בוצעה, היומן מעודכן\"}"}
                                }))
                                await openai_ws.send(json.dumps({"type": "response.create"}))
                                
                            elif func_name == "end_call":
                                await asyncio.sleep(5)
                                await twilio_ws.close()
                                break
                except Exception: pass

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
    except Exception: pass
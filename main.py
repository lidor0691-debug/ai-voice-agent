import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# טעינת משתני סביבה
raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
CALENDAR_ID = "e1f69352b339ba76f5776a42037f94705d3340aac25a78b1c7f85bd05f5bf931@group.calendar.google.com"

# מוח מאיה 8.2 - גמישות מכירתית ודינמיות
SYSTEM_PROMPT = f"""את מאיה מנהלת השירות והמכירות של הונדה Big Boys Toys. 
את בחורה חריפה, חולה על אופנועים, ויודעת למכור ולתת שירות במקביל.

חוקי דמו למקצוענים:
1. גמישות: הלקוח יכול לקפוץ בין נושאים. אם הוא קבע תור למוסך ואז שואל על אופנוע חדש - תזרמי איתו בכיף.
2. ידע במחירים: אם שואלים על מחיר, תני הערכה כללית (למשל: "ה-CB500X מתחיל באזור ה-50 אלף, תלוי באבזור") ותציעי לשלוח הצעה מדויקת בווטסאפ.
3. איסוף נתונים רציף: אם כבר קיבלת שם וטלפון במוסך, אל תשאלי אותם שוב לנסיעת המבחן! תשתמשי במידע שכבר יש לך.
4. שעה מדויקת: תמיד תתעקשי על שעה (HH:MM) גם למוסך וגם לנסיעת המבחן.
5. מגדר: את אישה (נקבה). הלקוח גבר (זכר). פנייה בברכה ראשונה תמיד בזכר!

לוגיקת טיפולים: 1,000 ק"מ = הרצה. 12,000 ק"מ = תקופתי."""

VOICE = "shimmer"

@app.post("/voice")
async def voice_entry(request: Request):
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f'wss://{request.url.hostname}/stream')
    response.append(connect)
    response.append(Hangup())
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    if not OPENAI_API_KEY:
        await twilio_ws.close(); return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
    
    try:
        async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 800},
                    "voice": VOICE,
                    "instructions": SYSTEM_PROMPT,
                    "modalities": ["audio", "text"],
                    "temperature": 0.6,
                    "tools": [
                        {
                            "type": "function",
                            "name": "book_garage_service",
                            "description": "קביעת תור למוסך",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, "service_type": {"type": "string"},
                                    "mileage": {"type": "string"}, "appointment_time": {"type": "string"}
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
                                    "name": {"type": "string"}, "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, "appointment_time": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "appointment_time"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "get_bike_quote",
                            "description": "שליחת הצעת מחיר בוואטסאפ",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, "phone": {"type": "string"},
                                    "bike_model": {"type": "string"}, "price_estimate": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "price_estimate"]
                            }
                        }
                    ],
                    "tool_choice": "auto"
                }
            }
            await openai_ws.send(json.dumps(session_update))

            stream_sid = None

            async def to_openai():
                nonlocal stream_sid
                async for message in twilio_ws.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        await openai_ws.send(json.dumps({
                            "type": "response.create",
                            "response": {"instructions": "תפתחי בברכה חדה וקצרה בזכר."}
                        }))
                    elif data['event'] == 'media':
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))

            async def from_openai():
                async for msg in openai_ws:
                    data = json.loads(msg)
                    if data.get('type') == 'response.audio.delta' and stream_sid:
                        await twilio_ws.send_text(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": data['delta']}}))
                    elif data.get('type') == 'input_audio_buffer.speech_started':
                        await twilio_ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
                    
                    elif data.get('type') == 'response.function_call_arguments.done':
                        args = json.loads(data['arguments'])
                        if MAKE_WEBHOOK_URL:
                            async with httpx.AsyncClient() as client:
                                args['action'] = data['name']
                                await client.post(MAKE_WEBHOOK_URL, json=args, timeout=15)
                        await openai_ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {"type": "function_call_output", "call_id": data['call_id'], "output": "{\"status\":\"success\"}"}
                        }))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

            await asyncio.gather(to_openai(), from_openai())
    except Exception: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5050)))

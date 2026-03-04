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

# המוח של מאיה 7.4 - הפרדה מוחלטת בין מוסך למכירות
SYSTEM_PROMPT = f"""את מאיה, מנהלת השירות של הונדה Big Boys Toys. 
את פועלת לפי חוקי ברזל. אסור לך לנחש פרטים!

חוק 1: הפרדה מוחלטת. 
- אם הלקוח אמר "טיפול" או "מוסך" -> את בנתיב מוסך בלבד. אסור להפעיל את save_test_ride.
- אם הלקוח אמר "קנייה" או "נסיעה" -> את בנתיב מכירות בלבד. אסור להפעיל את book_garage_service.

חוק 2: איסוף נתונים למוסך (חובה!):
לפני שאת מפעילה את 'book_garage_service', את חייבת לשאול ולקבל תשובה על:
1. איזה דגם אופנוע?
2. מה הקילומטראז' (ק"מ)?
3. איזה סוג טיפול (תקופתי או תקלה)?

חוק 3: סדר פעולות:
- תמיד בודקת זמינות (check_availability) קודם.
- רק אחרי שהלקוח אישר שעה, את מפעילה את השמירה (שלב ב').
- את מודיעה: "רגע, אני מעדכנת את האקסל שלנו... זהו, רשום!".

סגנון: חדה, מקצועית, פונה למתקשר בזכר, מדברת על עצמך בנקבה."""

VOICE = "shimmer"

@app.post("/voice")
async def voice_entry(request: Request):
    response = VoiceResponse()
    connect = Connect()
    host = request.url.hostname
    connect.stream(url=f'wss://{host}/stream')
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
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 1000},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_PROMPT,
                    "modalities": ["audio", "text"],
                    "temperature": 0.6, # הורדתי טמפרטורה כדי שתהיה יותר מדויקת ופחות יצירתית
                    "tools": [
                        {
                            "type": "function",
                            "name": "check_availability",
                            "description": "בודק זמינות ביומן.",
                            "parameters": { "type": "object", "properties": { "date": {"type": "string"} } }
                        },
                        {
                            "type": "function",
                            "name": "save_test_ride",
                            "description": "שמירת רכיבת מבחן באקסל.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "bike_model": {"type": "string"},
                                    "appointment_time": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "appointment_time"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "book_garage_service",
                            "description": "רישום תור למוסך באקסל.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "bike_model": {"type": "string"},
                                    "service_type": {"type": "string"},
                                    "mileage": {"type": "string"},
                                    "appointment_time": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "service_type", "appointment_time"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "get_bike_quote",
                            "description": "שליחת הצעת מחיר בווטסאפ.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "bike_model": {"type": "string"},
                                    "price": {"type": "string"}
                                },
                                "required": ["name", "phone", "bike_model", "price"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "end_call",
                            "description": "ניתוק השיחה.",
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
                                "response": {"instructions": "תפתחי בחום: 'היי, הגעת להונדה Big Boys Toys, אני מאיה. מה אפשר לעשות בשבילך?'"}
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
                            
                            output_content = "{\"status\":\"success\"}"
                            
                            if func_name in ["save_test_ride", "check_availability", "book_garage_service", "get_bike_quote"]:
                                if MAKE_WEBHOOK_URL:
                                    async with httpx.AsyncClient() as client:
                                        args['action'] = func_name
                                        args['calendar_id'] = CALENDAR_ID
                                        webhook_res = await client.post(MAKE_WEBHOOK_URL, json=args, timeout=15)
                                        if webhook_res.status_code == 200:
                                            output_content = webhook_res.text
                                
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {"type": "function_call_output", "call_id": call_id, "output": output_content}
                                }))
                                await openai_ws.send(json.dumps({"type": "response.create"}))
                                
                            elif func_name == "end_call":
                                await asyncio.sleep(2)
                                await twilio_ws.close()
                                break
                except Exception: pass

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
    except Exception: pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

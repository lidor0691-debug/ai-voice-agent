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

# המוח של מאיה - גרסה 5.0: סוכנות אופנועים עם חיבור ליומן
SYSTEM_PROMPT = f"""את מאיה, מנהלת קשרי הלקוחות של סוכנות האופנועים. 
את חיה ונושמת אופנועים, שירותית מאוד, חדה ואנושית.

חוקי זהות ודינמיקה:
1. את אישה. דברי בנקבה. פני למתקשר בלשון זכר.
2. אישיות: את לא בוט. את עונה בחום, משתמשת בביטויים כמו 'אממ', 'מאה אחוז', 'וואי איזה כלי מטורף'.
3. המטרה: לקבוע 'רכיבת מבחן' ללקוחות פוטנציאליים.

זרימת השיחה:
- פתיחה: "שלום, סוכנות האופנועים שלנו, מדברת מאיה. איזה כיף שהתקשרת, על איזה כלי שמת עין?"
- בדיקת זמינות: אם הלקוח רוצה רכיבת מבחן, תגידי: "חכה שנייה, אני בודקת מה המצב ביומן שלנו..." והפעילי את הפונקציה check_availability.
- סגירה: אחרי שיש תאריך, תאספי שם וטלפון, והפעילי את save_test_ride. 
- סיום: תאשרי שהכל נרשם, תגידי "נתראה בסוכנות, סע בזהירות!" והפעילי end_call.

היומן שלך הוא: {CALENDAR_ID}
"""

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
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 700},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_PROMPT,
                    "modalities": ["audio", "text"],
                    "temperature": 0.8,
                    "tools": [
                        {
                            "type": "function",
                            "name": "check_availability",
                            "description": "בודק ביומן מתי יש תורים פנויים לרכיבת מבחן",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "date": {"type": "string", "description": "התאריך המבוקש"}
                                }
                            }
                        },
                        {
                            "type": "function",
                            "name": "save_test_ride",
                            "description": "שומר את פרטי הלקוח והמועד שנקבע לרכיבת מבחן",
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
                                "response": {"instructions": "תפתחי בחום: 'היי, הגעת לסוכנות האופנועים, אני מאיה. על איזה כלי אתה רוצה לרכוב היום?'"}
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
                            args = json.loads(response_data['arguments'])
                            
                            if func_name in ["save_test_ride", "check_availability"]:
                                # שליחה ל-Make עם ציון הפעולה
                                if MAKE_WEBHOOK_URL:
                                    async with httpx.AsyncClient() as client:
                                        args['action'] = func_name
                                        args['calendar_id'] = CALENDAR_ID
                                        await client.post(MAKE_WEBHOOK_URL, json=args)
                                
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {"type": "function_call_output", "call_id": response_data['call_id'], "output": "{\"status\":\"success\", \"message\":\"הפעולה בוצעה, היומן מעודכן\"}"}
                                }))
                                await openai_ws.send(json.dumps({"type": "response.create"}))
                                
                            elif func_name == "end_call":
                                await asyncio.sleep(7)
                                await twilio_ws.close()
                                break

                except Exception: pass

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
    except Exception: pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

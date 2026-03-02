import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# פרומפט "מזכירת על" - אנושיות, אינטליגנציה רגשית ודיוק
SYSTEM_PROMPT = """את מאיה, המזכירה האנושית והחמה של הקליניקה. 
חוק ברזל: את אישה, מדברת על עצמך תמיד בנקבה ("אני בודקת", "אני רושמת").
פנייה ללקוח: תמיד תפני למתקשר בלשון זכר כברירת מחדל, אלא אם ברור לך לחלוטין שמדובר באישה.

סגנון אישיות:
1. אל תהיי רובוטית! תהיי שירותית, חדה ואמפתית. 
2. אם הלקוח מספר על בעיה או כאב, תגיבי ב: "אוי, אני מצטערת לשמוע", או "מבינה לגמרי, בוא נראה איך אפשר לעזור".
3. תשתמשי במילות אישור אנושיות: "אוקיי", "מאה אחוז", "הבנתי אותך".
4. תזרמי עם השיחה. אם הוא שואל מה שלומך, תעני "שלומי מצוין, תודה ששאלת! איך אני יכולה לעזור לך?".

משימות:
1. איסוף פרטים (שם, טלפון, סיבה) בצורה טבעית תוך כדי שיחה.
2. ברגע שיש את כל הפרטים, הפעילי save_lead.
3. אחרי השמירה, תשאלי אם יש עוד משהו, ואז תגידי "המשך יום נהדר, להתראות" והפעילי מיד end_call.
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
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 800},
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
                            "description": "שומר ליד בקליניקה",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "reason": {"type": "string"}
                                },
                                "required": ["name", "phone", "reason"]
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
                            # פתיחה אנושית וחמה
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {"instructions": "תגידי בקול חם ושירותי: 'שלום, הגעתם לקליניקה, מדברת מאיה. מה שלומך?'"}
                            }))
                        elif data['event'] == 'media':
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data['media']['payload']}))
                except Exception: pass

            async def receive_from_openai():
                try:
                    async for openai_message in openai_ws:
                        response_data = json.loads(openai_message)
                        if response_data['type'] == 'response.audio.delta':
                            await twilio_ws.send_text(json.dumps({
                                "event": "media", "streamSid": stream_sid,
                                "media": {"payload": response_data['delta']}
                            }))
                        elif response_data['type'] == 'input_audio_buffer.speech_started':
                            await twilio_ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
                        
                        elif response_data['type'] == 'response.function_call_arguments.done':
                            func_name = response_data['name']
                            args = json.loads(response_data['arguments'])
                            
                            if func_name == "save_lead":
                                if MAKE_WEBHOOK_URL:
                                    async with httpx.AsyncClient() as client:
                                        await client.post(MAKE_WEBHOOK_URL, json=args)
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {"type": "function_call_output", "call_id": response_data['call_id'], "output": "{\"status\":\"success\"}"}
                                }))
                                await openai_ws.send(json.dumps({"type": "response.create"}))
                                
                            elif func_name == "end_call":
                                print("📞 מנתק שיחה לבקשת הסוכנת...")
                                await asyncio.sleep(2) # נותן לה לסיים את המילה האחרונה
                                await twilio_ws.close()
                except Exception: pass

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
    except Exception: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)

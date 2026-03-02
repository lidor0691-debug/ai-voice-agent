import os
import json
import asyncio
import websockets
import httpx
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

app = FastAPI()

# טעינת משתני סביבה וניקוי רווחים מה-API Key
raw_api_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_api_key.strip().replace('\u2028', '').replace('\u2029', '') if raw_api_key else ""
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# המוח של מאיה - גרסה 3.0: אנושיות מלאה
SYSTEM_PROMPT = """את מאיה, המזכירה האנושית, החמה והחדה של הקליניקה. 
המטרה שלך היא לתת למטופל הרגשה שהוא בידיים בטוחות ומקצועיות.

חוקי זהות ודינמיקה:
1. את אישה. דברי על עצמך תמיד בנקבה ("אני רושמת", "אני בודקת"). פני למתקשר בלשון זכר כברירת מחדל.
2. אל תהיי רובוטית! תשתמשי באינטליגנציה רגשית. אם המטופל אומר שכואב לו או שהוא לחוץ, תעצרי הכל ותגידי: "אוי, אני ממש מצטערת לשמוע, בוא נראה איך אני עוזרת לך לקצר תהליכים".
3. הנהון קולי: השתמשי במילים כמו "אוקיי", "מאה אחוז", "הבנתי" תוך כדי השיחה כדי להראות שאת מקשיבה.
4. אל תעבדי עם רשימת מכולת. אם הלקוח נתן פרט (כמו שם) בתוך משפט ארוך, אל תשאלי עליו שוב.

זרימה אנושית:
- פתיחה: "שלום, הגעתם לקליניקה, מדברת מאיה. מה שלומך היום?" (חכי לתשובה ותגיבי עליה באמת לפני שתמשיכי).
- איסוף: רק אחרי שיצרת חיבור ראשוני, תגידי: "כדי שנוכל לעזור בצורה הכי טובה, אני רק צריכה לרשום לעצמי שם, טלפון ומה סיבת הפנייה".
- סיום: אחרי save_lead, תגידי "רשמתי הכל, יחזרו אליך ממש בקרוב. שיהיה המשך יום נהדר, להתראות!" והפעילי end_call.
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
        await twilio_ws.close()
        return

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:
            # הגדרות סשן לשדרוג מהירות התגובה והאנושיות
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 600},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_PROMPT,
                    "modalities": ["audio", "text"],
                    "temperature": 0.8,
                    "tools": [
                        {
                            "type": "function",
                            "name": "save_lead",
                            "description": "שומר את פרטי המטופל במערכת",
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
                            "description": "מנתק את השיחה פיזית",
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
                            # מאיה פותחת את השיחה מיד
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "instructions": "תגידי בקול חם ואנושי: 'שלום, הגעתם לקליניקה, מדברת מאיה. מה שלומך היום?'"
                                }
                            }))
                        elif data['event'] == 'media':
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }))
                        elif data['event'] == 'stop':
                            break
                except Exception:
                    pass

            async def receive_from_openai():
                try:
                    async for openai_message in openai_ws:
                        response_data = json.loads(openai_message)
                        
                        # הזרמת אודיו ל-Twilio
                        if response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                            await twilio_ws.send_text(json.dumps({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": response_data['delta']}
                            }))
                            
                        # קטיעת דיבור (Interrupt) - אם המשתמש מתפרץ למאיה
                        elif response_data['type'] == 'input_audio_buffer.speech_started':
                            await twilio_ws.send_text(json.dumps({
                                "event": "clear",
                                "streamSid": stream_sid
                            }))
                        
                        # טיפול בקריאה לפונקציות
                        elif response_data['type'] == 'response.function_call_arguments.done':
                            call_id = response_data['call_id']
                            func_name = response_data['name']
                            args = json.loads(response_data['arguments']) if response_data.get('arguments') else {}
                            
                            if func_name == "save_lead":
                                print(f"🎯 שמירת ליד: {args}")
                                if MAKE_WEBHOOK_URL:
                                    async with httpx.AsyncClient() as client:
                                        await client.post(MAKE_WEBHOOK_URL, json=args)
                                
                                # החזרת תשובה ל-OpenAI שהשמירה הצליחה
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps({"status": "success"})
                                    }
                                }))
                                await openai_ws.send(json.dumps({"type": "response.create"}))
                                
                            elif func_name == "end_call":
                                print("📞 מנתק שיחה...")
                                await asyncio.sleep(2) # זמן קצר למאיה לסיים את מילת הפרידה
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

if __name__ == "__main__":
    import uvicorn
    # שימוש בפורטלנד שמוגדר במשתני הסביבה של Railway
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

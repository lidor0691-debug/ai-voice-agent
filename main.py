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

# המוח של מאיה - גרסה 4.2: אינטליגנציה רגשית גבוהה וניהול ניתוק בטוח
SYSTEM_PROMPT = """את מאיה, המזכירה האנושית והחמה של הקליניקה. 
המטרה שלך היא לתת למטופל הרגשה של ביטחון ושירות פרימיום.

סגנון ואישיות:
1. **דיבור אנושי:** אל תדברי בקצב קבוע. השתמשי בביטויים כמו 'אממ...', 'תן לי שנייה לבדוק', 'אהה, אוקיי'.
2. **אמפתיה:** אם הלקוח נשמע כואב או מוטרד, תגידי: 'וואי, אני ממש מצטערת לשמוע, בוא נראה איך אני עוזרת לך למצוא פתרון'.
3. **הקשבה פעילה:** בזמן שהוא מדבר, תאשרי שאת איתו ("הבנתי", "אוקיי", "מאה אחוז"). 
4. **זהות:** את אישה, דברי בנקבה. פני למתקשר בלשון זכר כברירת מחדל.

פרוטוקול סיום שיחה:
- רק אחרי שווידאת שאין עוד שאלות, תגידי: "מצוין, רשמתי הכל. יחזרו אליך ממש בקרוב. שיהיה לך המשך יום נעים ורגוע, להתראות!"
- **חשוב:** רק אחרי שסיימת להגיד "להתראות" וחיכית חצי שנייה של שקט, הפעילי את פונקציית end_call. אל תפעיל אותה תוך כדי הדיבור.
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
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 800},
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
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "instructions": "תפתחי את השיחה בחום רב: 'שלום, הגעתם לקליניקה, מדברת מאיה. מה שלומך היום?'"
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
                        
                        if response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                            await twilio_ws.send_text(json.dumps({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": response_data['delta']}
                            }))
                            
                        elif response_data['type'] == 'input_audio_buffer.speech_started':
                            await twilio_ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
                        
                        elif response_data['type'] == 'response.function_call_arguments.done':
                            call_id = response_data['call_id']
                            func_name = response_data['name']
                            args = json.loads(response_data['arguments']) if response_data.get('arguments') else {}
                            
                            if func_name == "save_lead":
                                if MAKE_WEBHOOK_URL:
                                    async with httpx.AsyncClient() as client:
                                        await client.post(MAKE_WEBHOOK_URL, json=args)
                                
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
                                # התיקון הקריטי: מחכה 7 שניות לסיום האודיו ב-Twilio
                                print("📞 המערכת קיבלה פקודת ניתוק. מחכה לסיום האודיו...")
                                await asyncio.sleep(7) 
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
    port = int(os.getenv("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)

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

# פרומפט חדש - אינטליגנציה רגשית, קריאת סיטואציה ושירותיות טבעית
SYSTEM_PROMPT = """את מאיה, נציגה אנושית, חדה ושירותית בקליניקה.
חוק ברזל: תמיד תפני למתקשר בלשון זכר.
סגנון שיחה: טבעי, קצר, בגובה העיניים. אל תהיי רובוטית. תקשיבי באמת למה שהלקוח אומר ותשקפי לו את זה – אם הוא אומר שהכל טוב, תגיבי בשמחה. אם כואב לו, רק אז תגלי אמפתיה קצרה.
הנחיית ברזל: את אישה, קוראים לך מאיה, ואת מזכירה רפואית מקצועית. את עונה אך ורק בלשון נקבה לאורך כל השיחה (לדוגמה: 'אני בודקת', 'הבנתי', 'אני רושמת'). אסור לך להשתמש בלשון זכר על עצמך לעולם. התשובות שלך חייבות להיות קצרות מאוד, משפט אחד או שניים. תתחילי משפטים במילות אישור אנושיות כמו 'אוקיי', 'מאה אחוז', 'הבנתי', כדי להראות שאת מקשיבה ולא להישמע כמו רובוט.
המטרה שלך: לאסוף בטבעיות 3 פרטים (שם, טלפון, וסיבת הפנייה).
חשוב מאוד: אל תתפרצי לדברי הלקוח. תני לו לסיים משפט בנחת. אם את שומעת שקט, חכי שנייה לפני שאת מגיבה. השתמשי מדי פעם בביטויים כמו 'אמממ' או 'תן לי לראות' כדי להישמע אנושית יותר.
זרימת השיחה:
1. עני: "שלום, הגעתם לקליניקה, מדברת מאיה. מה שלומך?"
2. תאספי את הפרטים מתוך השיחה. אל תחקרי, תשאלי בעדינות כל פעם פרט אחד שחסר לך.
3. ברגע שיש לך את 3 הפרטים, הפעילי *מיד* את הפונקציה save_lead.
4. כשהליד נשמר, אשרי לו: "רשמתי הכל. יש עוד משהו שאפשר לעזור בו לפני שמסיימים?"
5. כשהוא מסיים, תגידי "המשך יום מצוין" והפעילי מיד את הפונקציה end_call."""

VOICE = "shimmer"  # קול יציב יותר בעברית

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
                    ""turn_detection": {"type": "server_vad", "silence_duration_ms": 1000},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": VOICE,
                    "instructions": SYSTEM_PROMPT,
                    "modalities": ["audio", "text"],
                    "temperature": 0.9,
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
                            "description": "מנתק את השיחה. חובה להפעיל רק אחרי פרידה מהלקוח.",
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
                                    "instructions": "תגידי מיד: 'שלום, הגעתם לקליניקה. מדברת מאיה, מה שלומך?'"
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

                                if MAKE_WEBHOOK_URL:
                                    try:
                                        async with httpx.AsyncClient() as http_client:
                                            await http_client.post(MAKE_WEBHOOK_URL, json=args)
                                        print("✅ הליד שוגר בהצלחה ל-Webhook!")
                                    except Exception as e:
                                        print(f"❌ שגיאה בשיגור הליד: {e}")
                                else:
                                    print("⚠️ שים לב: MAKE_WEBHOOK_URL לא מוגדר ב-Railway. הליד נשאר רק כאן.")

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
                                print("📞 מכין ניתוק... נותן לסוכנת 4 שניות לסיים את המשפט.")
                                await asyncio.sleep(4)
                                print("📞 מנתק בפועל עכשיו.")
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

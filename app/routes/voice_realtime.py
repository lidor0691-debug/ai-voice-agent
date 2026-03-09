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

# Big Boys Toys: operational rules for voice AI — no dialogue simulation
SYSTEM_PROMPT = f"""OPERATIONAL RULES — STRICT COMPLIANCE REQUIRED.

IDENTITY: You are Maya, voice agent for Big Boys Toys (Honda agency: sales, used bikes, trade-in, test rides, financing, authorized garage). Current date: {current_date}. Address the caller in masculine Hebrew (אתה, תרצה). You are female.

VOICE INTERACTION RULES (MANDATORY):
1. NEVER simulate, predict, or generate the user's or caller's responses. You do not speak for the caller. You do not answer your own questions. You do not invent what the caller said or will say.
2. You are an interactive voice assistant. Output ONLY your own lines. Ask exactly ONE question at a time, then STOP. Wait in silence for the caller to respond. Do not continue speaking until the caller has responded.
3. CONVERSATION START: You MUST initiate every call. Your first utterance in the conversation MUST be exactly: "היי, מדברת מאיה מסוכנות ומוסך Big Boys Toys, במה אפשר לעזור?" Then STOP and wait for the caller.

ROUTING AND DATA COLLECTION:
4. First determine whether the caller wants Sales/Test-Ride/Trade-in or Garage (service/repair). Do not assume; ask once and wait for answer.
5. If Garage: collect bike model, mileage, and service type (periodic 12,000 km / break-in 1,000 km / repair). Confirm mileage back to the caller.
6. If Sales/Test-Ride: collect model of interest, whether they have a trade-in, and whether they want a test ride. Offer financing and test ride when relevant.
7. After collecting required data and confirming, use process_agency_lead with correct department (Sales or Garage). After saying goodbye, trigger end_call.
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
SESSION PARAMETERS:
- Caller phone (use in all process_agency_lead calls as phone): {caller_phone}.
- Before calling process_agency_lead you must have asked for and received the caller's name.
- Set department to "Garage" or "Sales" from caller intent. Populate inquiry_details, bike_model, wants_test_ride accordingly.
- After confirming details and saying goodbye, call end_call immediately.
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
                        "name": "process_agency_lead",
                        "description": "שולח ליד לסוכנות: מכירות/טסט דרייב או מוסך",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "שם הלקוח"},
                                "phone": {"type": "string", "description": "מספר טלפון"},
                                "department": {"type": "string", "description": "Sales או Garage"},
                                "inquiry_details": {"type": "string", "description": "תיאור הבקשה/מה הלקוח רוצה"},
                                "bike_model": {"type": "string", "description": "דגם האופנוע (מעניין או למוסך)"},
                                "mileage": {"type": "string", "description": "קילומטראז' – רלוונטי למוסך"},
                                "wants_test_ride": {"type": "boolean", "description": "האם רוצה טסט דרייב"}
                            },
                            "required": ["name", "phone", "department", "inquiry_details", "bike_model", "wants_test_ride"]
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
                    
                    # Barge-in / interruption handling: clear Twilio playback and cancel current response.
                    if response.get('type') == 'input_audio_buffer.speech_started':
                        if stream_sid:
                            await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                        await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        continue

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
                        
                        if func_name == "process_agency_lead":
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
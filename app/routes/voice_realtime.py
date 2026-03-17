import os
import json
import asyncio
import websockets
import httpx
from urllib.parse import quote
from datetime import datetime
from fastapi import APIRouter, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Hangup

router = APIRouter()

# ── Environment variables ────────────────────────────────────────────────────
OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)

ROI_PHONE_NUMBER    = os.getenv("TWILIO_PHONE_NUMBER", "")   # Roi's Twilio number
ROI_WEBHOOK_URL     = os.getenv("ROI_WEBHOOK_URL") or os.getenv("MAKE_WEBHOOK_URL", "")

STUDIO_PHONE_NUMBER = os.getenv("STUDIO_PHONE_NUMBER", "")
STUDIO_WEBHOOK_URL  = os.getenv("STUDIO_WEBHOOK_URL", "")

current_date = datetime.now().strftime("%Y-%m-%d")

# ── In-memory call context store (keyed by Twilio CallSid) ───────────────────
# Populated by the /voice HTTP webhook before the WebSocket connects.
# The WebSocket reads from here using CallSid so it never depends on
# URL query params that may drop or mangle phone number characters (+).
CALL_CONTEXT: dict[str, dict] = {}

_CONTEXT_TTL_SECONDS = 30 * 60  # 30 minutes


def _cleanup_stale_contexts() -> None:
    """Remove CALL_CONTEXT entries older than _CONTEXT_TTL_SECONDS."""
    now = datetime.now().timestamp()
    stale = [sid for sid, ctx in CALL_CONTEXT.items()
             if now - ctx.get("created_at", 0) > _CONTEXT_TTL_SECONDS]
    for sid in stale:
        CALL_CONTEXT.pop(sid, None)
        print(f"🧹 Cleaned up stale context for CallSid: {sid}")


# ── Utility ───────────────────────────────────────────────────────────────────

def normalize_israeli_phone(phone: str) -> str:
    """Normalize a phone number to E.164 format for Israel (+972)."""
    if not phone:
        return phone
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("972"):
        national = digits[3:]
    else:
        national = digits
    while national.startswith("0"):
        national = national[1:]
    if not national:
        return phone.strip()
    return f"+972{national}"


def normalize_phone_key(phone: str) -> str:
    """Normalize any phone string to E.164 for consistent CLIENTS_CONFIG lookup."""
    if not phone:
        return ""
    return normalize_israeli_phone(phone)


async def send_lead_to_webhook(webhook_url: str, lead_data: dict) -> bool:
    """Send collected lead data to the given webhook URL."""
    if not webhook_url:
        print("⚠️ No webhook URL configured — skipping lead.")
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                json=lead_data,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            print(f"✅ Lead sent to webhook | status={resp.status_code}")
            return True
    except httpx.HTTPStatusError as exc:
        print(f"❌ Webhook HTTP error {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        print(f"❌ Webhook request failed: {exc}")
    return False


# ── Client configuration ──────────────────────────────────────────────────────
# Key   = normalized E.164 Twilio "To" phone number
# Value = client config dict
#
# To add a new client: add one entry here. No other code changes required.

_roi_phone_raw    = ROI_PHONE_NUMBER
_studio_phone_raw = STUDIO_PHONE_NUMBER
_roi_phone        = normalize_phone_key(_roi_phone_raw)
_studio_phone     = normalize_phone_key(_studio_phone_raw)

_ROI_CONFIG = {
    "client_name":    "Roi Insurance",
    "assistant_name": "מאיה",
    "business_type":  "insurance agency",
    "tone":           "professional, calm, trustworthy",
    "greeting": (
        "שלום, אני מאיה המזכירה הדיגיטלית של רועי. "
        "רועי לא פנוי כרגע. באיזה נושא אוכל לסייע?"
    ),
    "goal": "collect insurance lead details for Roi to follow up on",
    "required_fields": ["name", "phone_number", "insurance_type"],
    "booking_rules": "",
    "webhook_url": ROI_WEBHOOK_URL,
    "voice": "shimmer",
    "extra_notes": (
        "Focus on trust and clarity. "
        "If the caller mentions 'תביעה' (insurance claim), respond with empathy: "
        "'אהמ... אוי, אני מצטערת לשמוע. בוא נראה איך אפשר לעזור', "
        "then continue gently with the questions. "
        "Once you have name, phone, and topic, say exactly: "
        "'תודה רבה. אני מעבירה לרועי את הפרטים עכשיו, והוא יחזור אליך בהקדם.'"
    ),
}

_STUDIO_CONFIG = {
    "client_name":    "Maya BPM Dance Studio",
    "assistant_name": "מאיה",
    "business_type":  "dance studio",
    "tone":           "friendly, warm, personal, light",
    "greeting": (
        "שלום הגעת למאיה BPM! "
        "את מתעניינת לגבי ריקוד בת מצווה או סטודיו לריקוד?"
    ),
    "goal": "collect lead details and book a free trial dance class",
    "required_fields": [
        "interest_type (bat mitzvah choreography or studio classes)",
        "girl_name",
        "school_grade",
        "dance_experience",
        "parent_name",
        "parent_phone",
    ],
    "booking_rules": (
        "Trial classes are available on Sundays and Wednesdays only.\n"
        "Group schedule by grade:\n"
        "  - Kindergarten + Grade 1: Sunday at 17:00\n"
        "  - Grades 2–4: 17:45–18:40\n"
        "  - Grades 5–6: 18:40–19:40\n"
        "  - Older girls: 19:40–20:40\n"
        "Always offer 2 free trial classes to every new student."
    ),
    "webhook_url": STUDIO_WEBHOOK_URL,
    "voice": "shimmer",
    "extra_notes": (
        "Make every girl feel welcome and excited about dancing. "
        "Keep the conversation short and naturally guide toward booking a trial. "
        "After collecting the grade, suggest the matching time slot. "
        "Always mention the 2 free trial classes."
    ),
}

CLIENTS_CONFIG: dict[str, dict] = {}

if _roi_phone:
    CLIENTS_CONFIG[_roi_phone] = _ROI_CONFIG
else:
    print("❌ CLIENTS_CONFIG: Roi phone missing — TWILIO_PHONE_NUMBER is not set!")

if _studio_phone:
    if _studio_phone == _roi_phone:
        print("❌ CLIENTS_CONFIG: Studio phone equals Roi phone — STUDIO_PHONE_NUMBER may be wrong!")
    else:
        CLIENTS_CONFIG[_studio_phone] = _STUDIO_CONFIG
else:
    print("❌ CLIENTS_CONFIG: Studio phone missing — STUDIO_PHONE_NUMBER is not set!")

_DEFAULT_CLIENT: dict = CLIENTS_CONFIG.get(_roi_phone, next(iter(CLIENTS_CONFIG.values()), {}))

print("=" * 60)
print("🔧 STARTUP — ROUTING CONFIG")
print(f"   TWILIO_PHONE_NUMBER  raw='{_roi_phone_raw}'  normalized='{_roi_phone}'  {'✅' if _roi_phone else '❌ MISSING'}")
print(f"   STUDIO_PHONE_NUMBER  raw='{_studio_phone_raw}'  normalized='{_studio_phone}'  {'✅' if _studio_phone else '❌ MISSING'}")
print(f"   Numbers equal? {_roi_phone == _studio_phone and bool(_roi_phone)}")
print(f"   CLIENTS_CONFIG keys ({len(CLIENTS_CONFIG)}): {list(CLIENTS_CONFIG.keys())}")
print(f"   Default fallback: '{_DEFAULT_CLIENT.get('client_name', 'none')}'")
print("=" * 60)


# ── Dynamic prompt builder ────────────────────────────────────────────────────

def build_system_prompt(client_config: dict, caller_phone: str) -> str:
    """Build a full system prompt from a client config dict."""
    name          = client_config.get("assistant_name", "מאיה")
    client_name   = client_config.get("client_name", "")
    business      = client_config.get("business_type", "")
    tone          = client_config.get("tone", "professional")
    greeting      = client_config.get("greeting", "שלום, במה אוכל לעזור?")
    goal          = client_config.get("goal", "")
    required      = client_config.get("required_fields", [])
    booking_rules = client_config.get("booking_rules", "")
    extra_notes   = client_config.get("extra_notes", "")

    fields_str      = "\n".join(f"  - {f}" for f in required)
    booking_section = f"\nBOOKING RULES:\n{booking_rules}\n" if booking_rules else ""
    extra_section   = f"\nEXTRA NOTES:\n{extra_notes}\n" if extra_notes else ""

    return f"""OPERATIONAL RULES — STRICT COMPLIANCE REQUIRED.

IDENTITY:
You are {name}, the AI voice assistant for {client_name} ({business}).
Current date: {current_date}. You speak Hebrew. You are female.
Your tone: {tone}.

VOICE INTERACTION RULES (MANDATORY):
1. NEVER simulate, predict, or generate the caller's responses. You do not speak for the caller.
2. NEVER invent or assume a caller's name. If unknown, ask: "סליחה, עם מי יש לי את הכבוד?"
   Do NOT address the caller by name unless they have explicitly told you their name in this call.
3. Ask exactly ONE question at a time, then STOP and wait for the caller to respond.
4. Use short, natural Hebrew fillers — "אהמ...", "אוקיי", "הבנתי", "מעולה", "סבבה" — to sound human and attentive.
5. Speak at a relaxed, conversational pace with short sentences.
6. CONVERSATION START: Speak first the moment the call connects. Your first utterance MUST be:
   "{greeting}"
   Then STOP and wait for the caller.

GOAL:
{goal}

REQUIRED INFORMATION TO COLLECT:
{fields_str}
{booking_section}{extra_section}
CALL FLOW:
7. Collect all required fields one question at a time through natural conversation.
8. Once you have all required information (or as much as the caller is willing to give),
   say the appropriate warm closing for this business and call the tool process_agency_lead
   with all collected details.
9. After process_agency_lead completes, say:
   "מעולה, רשמתי הכל. יש עוד משהו שאוכל לעזור בו לפני שנסגור?"
   Then STOP and wait for the caller.
10. If the caller indicates there is nothing more (e.g., "לא", "זהו", "תודה", "הכל בסדר", "לא תודה"),
    say: "שיהיה יום מצוין, ביי!" and IMMEDIATELY call the tool end_call.
    Do NOT say anything further after the goodbye.

SESSION INFO:
- Caller phone (Twilio From): {caller_phone}
- If the caller provides no alternative phone, you may use this number.
"""


# ── Twilio entry point ────────────────────────────────────────────────────────

@router.post("/voice")
async def voice_entry(request: Request):
    form_data = await request.form()
    raw_to    = form_data.get("To", "")
    raw_from  = form_data.get("From", "")
    call_sid  = form_data.get("CallSid", "")

    norm_to   = normalize_phone_key(raw_to)
    norm_from = normalize_phone_key(raw_from)

    # Store call metadata before WebSocket connects — keyed by CallSid.
    # The WebSocket endpoint reads from here; it never depends on URL params
    # carrying phone numbers (which are mangled by + encoding in some proxies).
    _cleanup_stale_contexts()
    CALL_CONTEXT[call_sid] = {
        "to":         norm_to,
        "from":       norm_from,
        "raw_to":     raw_to,
        "raw_from":   raw_from,
        "created_at": datetime.now().timestamp(),
    }

    print("=" * 60)
    print(f"[VOICE] call_sid         = '{call_sid}'")
    print(f"[VOICE] raw_to           = '{raw_to}'")
    print(f"[VOICE] normalized_to    = '{norm_to}'")
    print(f"[VOICE] raw_from         = '{raw_from}'")
    print(f"[VOICE] normalized_from  = '{norm_from}'")
    print(f"[VOICE] CALL_CONTEXT keys after store: {list(CALL_CONTEXT.keys())}")
    print(f"[VOICE] stored context   = {CALL_CONTEXT[call_sid]}")

    host       = request.url.hostname
    stream_url = f"wss://{host}/voice-ai/stream?call_sid={quote(call_sid, safe='')}"
    print(f"[VOICE] stream_url       = '{stream_url}'")

    response = VoiceResponse()
    connect  = Connect()
    connect.stream(url=stream_url)
    response.append(connect)
    response.append(Hangup())
    twiml_str = str(response)
    print(f"[VOICE] TwiML returned:\n{twiml_str}")
    print("=" * 60)
    return Response(content=twiml_str, media_type="application/xml")


# ── WebSocket / realtime engine ───────────────────────────────────────────────

@router.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()

    # ── Phase 1: resolve call_sid ─────────────────────────────────────────
    # Try query param first; if missing, read Twilio messages until the
    # "start" event arrives (which always contains callSid).
    # We MUST have call_sid before opening OpenAI — routing depends on it.
    print("=" * 60)
    print(f"[WS] raw query params    = {dict(twilio_ws.query_params)}")
    call_sid   = twilio_ws.query_params.get("call_sid", "")
    stream_sid = None
    _pending_audio: list[str] = []   # buffer media that arrives before start

    print(f"[WS] call_sid from query = '{call_sid}'")

    if not CALL_CONTEXT.get(call_sid):
        # call_sid is missing or not yet in CALL_CONTEXT — wait for start event
        print(f"[WS] call_sid not in CALL_CONTEXT — reading messages until start event")
        try:
            async for raw_msg in twilio_ws.iter_text():
                evt = json.loads(raw_msg)
                if evt["event"] == "start":
                    start_sid  = evt["start"].get("callSid", "")
                    stream_sid = evt["start"].get("streamSid", "")
                    print(f"[WS] call_sid from start event  = '{start_sid}'")
                    print(f"[WS] stream_sid from start event = '{stream_sid}'")
                    if start_sid:
                        call_sid = start_sid
                    break
                elif evt["event"] == "media":
                    _pending_audio.append(evt["media"]["payload"])
        except Exception as e:
            print(f"[WS ERROR] Failed while waiting for start event: {e}")

    print(f"[WS] CALL_CONTEXT keys   = {list(CALL_CONTEXT.keys())}")

    # ── Phase 2: resolve routing from CALL_CONTEXT ───────────────────────
    call_ctx = CALL_CONTEXT.get(call_sid)
    if call_ctx:
        caller_phone = call_ctx["from"]
        to_number    = call_ctx["to"]
        print(f"[WS] resolved call_ctx   = {call_ctx}")
    else:
        caller_phone = ""
        to_number    = ""
        print(f"[WS ERROR] Missing CALL_CONTEXT for call_sid='{call_sid}' — routing will fall back")

    # ── Phase 3: client lookup ────────────────────────────────────────────
    print(f"[ROUTING] to_number used for lookup = '{to_number}'")
    print(f"[ROUTING] CLIENTS_CONFIG keys       = {list(CLIENTS_CONFIG.keys())}")
    _exact = CLIENTS_CONFIG.get(to_number) if to_number else None
    print(f"[ROUTING] exact lookup result       = {'<' + _exact.get('client_name', '?') + '>' if _exact else 'None'}")

    if _exact:
        client_config = _exact
        print(f"[ROUTING] selected client_name     = '{client_config.get('client_name')}' (EXACT MATCH)")
    else:
        client_config = _DEFAULT_CLIENT
        print(f"[ROUTING] selected client_name     = '{client_config.get('client_name', 'none')}' (FALLBACK)")

    # ── Fail-fast assertions ──────────────────────────────────────────────
    if to_number and to_number == _studio_phone:
        if client_config.get("client_name") != "Maya BPM Dance Studio":
            raise RuntimeError(
                f"ROUTING BUG: Studio call (to='{to_number}') resolved to "
                f"'{client_config.get('client_name')}' — CLIENTS_CONFIG: {list(CLIENTS_CONFIG.keys())}"
            )
    if to_number and to_number == _roi_phone:
        if client_config.get("client_name") != "Roi Insurance":
            raise RuntimeError(
                f"ROUTING BUG: Roi call (to='{to_number}') resolved to "
                f"'{client_config.get('client_name')}' — CLIENTS_CONFIG: {list(CLIENTS_CONFIG.keys())}"
            )

    if not client_config:
        print("[WS ERROR] No client config and no default — closing.")
        await twilio_ws.close()
        return

    if not OPENAI_API_KEY:
        print("[WS ERROR] Missing OpenAI API Key")
        await twilio_ws.close()
        return

    system_prompt = build_system_prompt(client_config, caller_phone)
    webhook_url   = client_config.get("webhook_url", "")
    voice         = client_config.get("voice", "shimmer")

    print(f"[OPENAI] selected client_name = '{client_config.get('client_name')}'")
    print(f"[OPENAI] prompt first 120     = '{system_prompt[:120].strip()}'")
    print("=" * 60)

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers    = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}

    async with websockets.connect(openai_url, additional_headers=headers) as openai_ws:

        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.75,
                    "prefix_padding_ms": 500,
                    "silence_duration_ms": 1000,
                },
                "input_audio_format":  "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice":        voice,
                "instructions": system_prompt,
                "modalities":   ["audio", "text"],
                "temperature":  0.7,
                "tools": [
                    {
                        "type": "function",
                        "name": "process_agency_lead",
                        "description": (
                            f"Send all collected caller details to {client_config.get('client_name')}. "
                            "Call this once you have gathered the required information."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Caller's name",
                                },
                                "phone_number": {
                                    "type": "string",
                                    "description": "Phone number to call back",
                                },
                                "topic": {
                                    "type": "string",
                                    "description": "Main topic or interest (e.g. insurance type, dance interest)",
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "All other collected details as a summary",
                                },
                            },
                            "required": ["name", "phone_number", "topic"],
                            "additionalProperties": False,
                        },
                    },
                    {
                        "type": "function",
                        "name": "end_call",
                        "description": "Hang up the call immediately.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                ],
            },
        }

        await openai_ws.send(json.dumps(session_update))

        # Flush audio that arrived while we were waiting for the start event
        for payload in _pending_audio:
            await openai_ws.send(json.dumps({
                "type":  "input_audio_buffer.append",
                "audio": payload,
            }))
        _pending_audio.clear()

        await openai_ws.send(json.dumps({"type": "response.create"}))

        is_ai_speaking    = False
        speech_started_at = None
        _SILENCE_MS       = 1000  # must match silence_duration_ms above
        _MIN_SPEECH_MS    = 300   # minimum real speech before allowing interruption

        async def receive_from_twilio():
            nonlocal stream_sid
            try:
                async for message in twilio_ws.iter_text():
                    data = json.loads(message)
                    if data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        print(f"📡 Stream started: {stream_sid}")
                    elif data["event"] == "media":
                        await openai_ws.send(json.dumps({
                            "type":  "input_audio_buffer.append",
                            "audio": data["media"]["payload"],
                        }))
            except Exception as e:
                print(f"⚠️ Twilio Receiver Error: {e}")

        async def receive_from_openai():
            nonlocal is_ai_speaking, speech_started_at
            try:
                async for message in openai_ws:
                    event      = json.loads(message)
                    event_type = event.get("type")

                    # ── Stream AI audio to Twilio ──────────────────────────
                    if event_type == "response.audio.delta":
                        is_ai_speaking = True
                        if stream_sid:
                            await twilio_ws.send_json({
                                "event":     "media",
                                "streamSid": stream_sid,
                                "media":     {"payload": event["delta"]},
                            })
                        continue

                    # ── AI finished speaking ───────────────────────────────
                    if event_type in ("response.audio.done", "response.cancelled"):
                        is_ai_speaking    = False
                        speech_started_at = None
                        continue

                    # ── VAD: caller started speaking ───────────────────────
                    # Record timestamp; don't interrupt yet — wait for speech_stopped
                    # to measure actual duration (filters noise, echo, brief sounds).
                    if event_type == "input_audio_buffer.speech_started":
                        speech_started_at = asyncio.get_event_loop().time()
                        continue

                    # ── VAD: caller finished speaking ──────────────────────
                    # speech_stopped fires after silence_duration_ms of quiet.
                    # elapsed = actual_speech + silence_duration_ms.
                    # Only interrupt if AI is speaking AND speech >= _MIN_SPEECH_MS.
                    if event_type == "input_audio_buffer.speech_stopped":
                        if speech_started_at is not None and is_ai_speaking:
                            elapsed_ms = (asyncio.get_event_loop().time() - speech_started_at) * 1000
                            speech_ms  = elapsed_ms - _SILENCE_MS
                            if speech_ms >= _MIN_SPEECH_MS:
                                if stream_sid:
                                    await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                                await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        speech_started_at = None
                        continue

                    # ── Tool calls ─────────────────────────────────────────
                    if event_type == "response.function_call_arguments.done":
                        func_name = event["name"]
                        args      = json.loads(event["arguments"])
                        print(f"🛠️ Function call: {func_name} | args: {args}")

                        if func_name == "process_agency_lead":
                            lead_payload = {
                                "source":              "voice_realtime",
                                "client":              client_config.get("client_name", ""),
                                "caller_phone_twilio": caller_phone,
                                "name":                args.get("name"),
                                "phone_number":        args.get("phone_number") or caller_phone,
                                "topic":               args.get("topic"),
                                "notes":               args.get("notes", ""),
                            }
                            await send_lead_to_webhook(webhook_url, lead_payload)

                        if func_name == "end_call":
                            print(f"👋 end_call triggered for '{client_config.get('client_name')}' — disconnecting")
                            CALL_CONTEXT.pop(call_sid, None)
                            await asyncio.sleep(2)
                            await twilio_ws.close()
                            break

            except Exception as e:
                print(f"⚠️ OpenAI Receiver Error: {e}")

        await asyncio.gather(receive_from_twilio(), receive_from_openai())

        # Cleanup on normal call end
        CALL_CONTEXT.pop(call_sid, None)

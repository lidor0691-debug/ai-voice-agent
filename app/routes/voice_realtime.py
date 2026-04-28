import os
import json
import asyncio
import websockets
import httpx
from urllib.parse import quote
from datetime import datetime, timedelta
from fastapi import APIRouter, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect
from app.services.agent_config import fetch_supabase_agent_config, get_agent_phone_number_by_id
from app.services.lead_capture import save_lead

router = APIRouter()

# ── Environment variables ────────────────────────────────────────────────────
OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)

ROI_PHONE_NUMBER    = os.getenv("TWILIO_PHONE_NUMBER", "")   # kept for logging only

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
    """Normalize any phone string to E.164 for Supabase lookup."""
    if not phone:
        return ""
    return normalize_israeli_phone(phone)


async def send_lead_to_webhook(webhook_url: str, lead_data: dict) -> bool:
    """Send collected lead data to the given webhook URL."""
    print("[WEBHOOK] ▶ send_lead_to_webhook called")
    print(f"[WEBHOOK] 🌐 URL: {webhook_url or '(empty — not configured)'}")
    print(f"[WEBHOOK] 📦 payload: {json.dumps(lead_data, ensure_ascii=False)}")

    if not webhook_url:
        print("[WEBHOOK] ⚠️ No webhook URL configured — lead NOT sent.")
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                json=lead_data,
                headers={"Content-Type": "application/json"},
            )
            print(f"[WEBHOOK] ← HTTP {resp.status_code}")
            print(f"[WEBHOOK] ← body: {resp.text[:500]}")
            resp.raise_for_status()
            print("[WEBHOOK] ✅ Lead delivered successfully")
            return True
    except httpx.HTTPStatusError as exc:
        print(f"[WEBHOOK] ❌ HTTP error {exc.response.status_code}: {exc.response.text[:500]}")
    except Exception as exc:
        print(f"[WEBHOOK] ❌ Request failed: {exc}")
    return False


print("=" * 60)
print("🔧 STARTUP — ROUTING CONFIG")
print(f"   TWILIO_PHONE_NUMBER: '{ROI_PHONE_NUMBER}'")
print("   Agent routing: Supabase only (no hardcoded clients)")
print("=" * 60)


# ── Client-specific payload builders ─────────────────────────────────────────

def _build_roi_payload(args: dict, caller_phone: str, client_config: dict) -> dict:
    return {
        "source":              "voice_realtime",
        "client":              client_config.get("client_name", ""),
        "caller_phone_twilio": caller_phone,
        "name":                args.get("name", ""),
        "phone_number":        args.get("phone_number") or caller_phone,
        "topic":               args.get("topic", ""),
        "notes":               args.get("notes", ""),
    }


_HEBREW_WEEKDAY = {"ראשון": 6, "שני": 0, "שלישי": 1, "רביעי": 2, "חמישי": 3, "שישי": 4, "שבת": 5}


def _build_studio_payload(args: dict, caller_phone: str, client_config: dict) -> dict:
    raw_parent_phone = args.get("parent_phone") or caller_phone
    parent_phone     = normalize_israeli_phone(raw_parent_phone) if raw_parent_phone else ""
    trial_booked     = bool(args.get("preferred_day"))
    followup_msg     = (
        "היי, כאן מאיה מהסטודיו 💃\n"
        f"איזה כיף שדיברנו.\nמחכות לכן לשיעור הניסיון שקבענו ❤️"
        if trial_booked else
        "היי, כאן מאיה מהסטודיו 💃\n"
        "תודה שפנית אלינו. נחזור אלייך ממש בקרוב עם המשך תיאום ❤️"
    )
    # Compute next occurrence of the selected weekday as YYYY-MM-DD HH:MM
    _preferred  = args.get("preferred_day", "")
    _time       = args.get("assigned_trial_time", "")
    _target_wd  = _HEBREW_WEEKDAY.get(_preferred)
    _date_str   = ""
    if _target_wd is not None and _time:
        _today      = datetime.now()
        _days_ahead = (_target_wd - _today.weekday()) % 7
        _date_str   = (_today + timedelta(days=_days_ahead)).strftime("%Y-%m-%d")
    payload = {
        "timestamp":             datetime.now().isoformat(),
        "source":                "voice_realtime",
        "client":                "Maya BPM",
        "service_type":          "studio",
        "girl_name":             args.get("girl_name", ""),
        "school_grade":          args.get("school_grade", ""),
        "dance_experience":      args.get("dance_experience", ""),
        "experience_details":    args.get("experience_details", ""),
        "parent_name":           args.get("parent_name", ""),
        "parent_phone":          parent_phone,
        "girl_phone":            "",
        "preferred_day":         _preferred,
        "assigned_trial_day":    _date_str,
        "assigned_trial_time":   _time,
        "trial1_status":         "נקבע" if trial_booked else "",
        "trial2_status":         "",
        "registration_status":   "חדש",
        "notes":                 args.get("notes", ""),
        "followup_target_phone": parent_phone,
        "followup_message":      followup_msg,
    }
    print(f"[STUDIO] 📦 final payload: {json.dumps(payload, ensure_ascii=False)}")
    return payload


# Maps client_name → payload builder function
_PAYLOAD_BUILDERS = {
    "Roi Insurance":        _build_roi_payload,
    "Maya BPM": _build_studio_payload,
}


# ── Dynamic prompt builder ────────────────────────────────────────────────────

def build_system_prompt(client_config: dict, caller_phone: str) -> str:
    """Build a full system prompt from a client config dict."""
    # Studio (and future clients) can supply a full prompt override
    override = client_config.get("prompt_override")
    if override:
        return override.replace("{caller_phone}", caller_phone)
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

    # Guard: reject unknown numbers via Supabase lookup.
    # This prevents the WebSocket from opening for truly unknown numbers.
    try:
        _sb = await fetch_supabase_agent_config(norm_to)
        _known_in_supabase = bool(_sb and not _sb.get("fallback_used"))
        print(f"[VOICE] Supabase pre-check: known={_known_in_supabase}, client='{_sb.get('client_name')}'")
    except Exception as _e:
        print(f"[VOICE] Supabase pre-check error: {_e}")
        _known_in_supabase = False
    if not _known_in_supabase:
        print(f"[VOICE] ❌ No active agent in Supabase for norm_to='{norm_to}' — returning error TwiML")
        err_response = VoiceResponse()
        err_response.say("מצטערים, אירעה שגיאה. נסו שוב מאוחר יותר.", language="he-IL")
        return Response(content=str(err_response), media_type="application/xml")

    host       = request.url.hostname
    stream_url = f"wss://{host}/voice-ai/stream?call_sid={quote(call_sid, safe='')}"
    print(f"[VOICE] stream_url       = '{stream_url}'")

    response = VoiceResponse()
    connect  = Connect()
    connect.stream(url=stream_url)
    response.append(connect)
    twiml_str = str(response)
    print(f"[VOICE] TwiML returned:\n{twiml_str}")
    print("=" * 60)
    return Response(content=twiml_str, media_type="application/xml")


# ── Test call Twilio webhook ─────────────────────────────────────────────────

@router.post("/test-voice")
async def test_voice_entry(request: Request):
    """
    Twilio webhook for outbound test calls initiated from the dashboard.
    Looks up agent config by agent_id query param instead of To number,
    and marks the call as test so leads/webhooks are skipped.
    """
    form_data = await request.form()
    agent_id  = request.query_params.get("agent_id", "")
    call_sid  = form_data.get("CallSid", "")
    raw_from  = form_data.get("From", "")
    norm_from = normalize_phone_key(raw_from)

    print(f"[TEST-VOICE] agent_id={agent_id} | call_sid={call_sid} | from={raw_from}")

    agent_phone = await get_agent_phone_number_by_id(agent_id)
    if not agent_phone:
        err = VoiceResponse()
        err.say("Test call setup failed — agent not found.", language="en-US")
        return Response(content=str(err), media_type="application/xml")

    agent_cfg = await fetch_supabase_agent_config(agent_phone)
    if agent_cfg.get("fallback_used"):
        err = VoiceResponse()
        err.say("Test call setup failed — agent config not found.", language="en-US")
        return Response(content=str(err), media_type="application/xml")

    _cleanup_stale_contexts()
    CALL_CONTEXT[call_sid] = {
        "to":                    agent_phone,
        "from":                  norm_from,
        "raw_to":                agent_phone,
        "raw_from":              raw_from,
        "created_at":            datetime.now().timestamp(),
        "is_test":               True,
        "agent_config_override": agent_cfg,
    }
    print(f"[TEST-VOICE] context stored for call_sid={call_sid}, agent='{agent_cfg.get('client_name')}'")

    host       = request.url.hostname
    stream_url = f"wss://{host}/voice-ai/stream?call_sid={quote(call_sid, safe='')}"
    response   = VoiceResponse()
    connect    = Connect()
    connect.stream(url=stream_url)
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")


# ── WebSocket / realtime engine ───────────────────────────────────────────────

@router.websocket("/stream")
async def websocket_endpoint(twilio_ws: WebSocket):
    await twilio_ws.accept()
    _ws_open = True   # guarded flag — prevents send/close after disconnect

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

    # ── Phase 1.5: ensure stream_sid is captured before opening OpenAI ──
    # If call_sid was resolved from the query param (Phase 1 block skipped),
    # the Twilio "start" event is still buffered — read it now so that
    # stream_sid is set before response.create fires and audio starts flowing.
    if stream_sid is None:
        try:
            async for raw_msg in twilio_ws.iter_text():
                evt = json.loads(raw_msg)
                if evt["event"] == "start":
                    if not call_sid:
                        call_sid = evt["start"].get("callSid", "")
                    stream_sid = evt["start"].get("streamSid", "")
                    print(f"[WS] stream_sid from phase 1.5 = '{stream_sid}'")
                    break
                elif evt["event"] == "media":
                    _pending_audio.append(evt["media"]["payload"])
        except Exception as e:
            print(f"[WS ERROR] Phase 1.5 start wait failed: {e}")

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

    # ── Phase 3: client lookup — Supabase only ────────────────────────────
    is_test = bool(call_ctx and call_ctx.get("is_test"))
    print(f"[ROUTING] to_number used for lookup = '{to_number}' | is_test={is_test}")

    if call_ctx and call_ctx.get("agent_config_override"):
        client_config = call_ctx["agent_config_override"]
        print(f"[ROUTING] ✅ Test call — using pre-fetched config for '{client_config.get('client_name')}'")
    elif not to_number:
        print(f"[ROUTING] ❌ No to_number — closing call")
        try:
            await twilio_ws.close()
        except Exception as e:
            print(f"[ROUTING] WebSocket close error (safe to ignore): {e}")
        return
    else:
        try:
            print(f"[DEBUG] Looking up Supabase for: {to_number}")
            _candidate = await fetch_supabase_agent_config(to_number)
            print(f"[DEBUG] Supabase result: fallback_used={_candidate.get('fallback_used')}, client_name={_candidate.get('client_name')}")
            if _candidate and not _candidate.get("fallback_used"):
                _candidate["_from_supabase"] = True
                client_config = _candidate
                print(f"[ROUTING] ✅ Supabase match: '{client_config.get('client_name')}' — using dashboard config")
            else:
                print(f"[ROUTING] ❌ No active agent in Supabase for '{to_number}' — closing call")
                print(f"[DEBUG] Check that phone_number='{to_number}' exists in agents_config with is_active=true")
                try:
                    await twilio_ws.close()
                except Exception as e:
                    print(f"[ROUTING] WebSocket close error (safe to ignore): {e}")
                return
        except Exception as _e:
            print(f"[ROUTING] ❌ Supabase lookup error: {_e} — closing call")
            try:
                await twilio_ws.close()
            except Exception as e:
                print(f"[ROUTING] WebSocket close error (safe to ignore): {e}")
            return

    if not client_config:
        print("[WS ERROR] No client config and no default — closing.")
        try:
            await twilio_ws.close()
        except Exception as e:
            print(f"[WS] close error: {e}")
        return

    if not OPENAI_API_KEY:
        print("[WS ERROR] Missing OpenAI API Key")
        try:
            await twilio_ws.close()
        except Exception as e:
            print(f"[WS] close error: {e}")
        return

    # prompt_override is pre-built by fetch_supabase_agent_config with {{caller_phone}} placeholder
    _raw_prompt = client_config.get("prompt_override", "")
    if _raw_prompt:
        system_prompt = _raw_prompt.replace("{{caller_phone}}", caller_phone)
        print(f"[OPENAI] prompt source = supabase")
    else:
        print(f"[OPENAI] ⚠️ Supabase prompt empty — using generic builder")
        system_prompt = build_system_prompt(client_config, caller_phone)
    webhook_url   = client_config.get("webhook_url", "")
    # voice_id is already resolved to an OpenAI voice name by fetch_supabase_agent_config
    voice         = client_config.get("voice_id") or client_config.get("voice") or "shimmer"

    print(f"[OPENAI] selected client_name = '{client_config.get('client_name')}'")
    print(f"[OPENAI] voice                = '{voice}'")
    print(f"[OPENAI] prompt length        = {len(system_prompt)} chars")
    print(f"[OPENAI] prompt first 300     = '{system_prompt[:300].strip()}'")
    print(
        f"[ROUTE-AUDIT] route=voice_realtime to={to_number} "
        f"resolved_agent_id={client_config.get('agent_id')} "
        f"resolved_client_id={client_config.get('client_id')} "
        f"fallback_used={bool(client_config.get('fallback_used'))} "
        f"knowledge_items_count={client_config.get('knowledge_items_count', 0)}"
    )
    print("=" * 60)

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers    = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}

    async with websockets.connect(openai_url, additional_headers=headers, ping_interval=None) as openai_ws:

        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.90,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 180,
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
                        "parameters": client_config.get("tool_parameters", {
                            "type": "object",
                            "properties": {
                                "name":         {"type": "string", "description": "Caller's name"},
                                "phone_number": {"type": "string", "description": "Phone number to call back"},
                                "topic":        {"type": "string", "description": "Main topic or interest"},
                                "notes":        {"type": "string", "description": "All other collected details"},
                            },
                            "required": ["name", "phone_number", "topic"],
                            "additionalProperties": False,
                        }),
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

        # Discard audio buffered during setup (ringback / line noise / early "hello").
        # Flushing it before the opening greeting causes phantom user-speech events.
        _pending_audio.clear()

        # Small pause so session.update is fully applied before the greeting fires.
        await asyncio.sleep(0.25)

        await openai_ws.send(json.dumps({"type": "response.create"}))

        is_ai_speaking         = False
        speech_started_at      = None
        opening_greeting_done  = False   # blocks interrupts until first greeting completes
        listen_after_ts        = 0.0     # gate: ignore Twilio audio until this timestamp
        _SILENCE_MS            = 180   # must match silence_duration_ms above
        _MIN_SPEECH_MS         = 300   # minimum real speech before allowing interruption
        lead_sent              = False  # safety: track if process_agency_lead fired
        last_ai_done_ts        = 0.0     # timestamp of last response.audio.done
        user_has_spoken        = False   # watchdog only arms after first user speech

        async def receive_from_twilio():
            nonlocal stream_sid
            try:
                async for message in twilio_ws.iter_text():
                    data = json.loads(message)
                    if data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        print(f"📡 Stream started: {stream_sid}")
                    elif data["event"] == "media":
                        if not opening_greeting_done:
                            continue  # drop audio until opening greeting has started
                        if is_ai_speaking:
                            continue  # drop audio while AI is speaking
                        now = asyncio.get_event_loop().time()
                        if now < listen_after_ts:
                            continue  # drop audio during post-speech gate window
                        await openai_ws.send(json.dumps({
                            "type":  "input_audio_buffer.append",
                            "audio": data["media"]["payload"],
                        }))
            except Exception as e:
                print(f"⚠️ Twilio Receiver Error: {e}")

        async def receive_from_openai():
            nonlocal is_ai_speaking, speech_started_at, lead_sent, _ws_open, opening_greeting_done, listen_after_ts, last_ai_done_ts, user_has_spoken
            try:
                async for message in openai_ws:
                    event      = json.loads(message)
                    event_type = event.get("type")

                    # ── Stream AI audio to Twilio ──────────────────────────
                    if event_type == "response.audio.delta":
                        is_ai_speaking = True
                        opening_greeting_done = True   # first audio arrived — greeting started
                        if _ws_open and stream_sid:
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
                        now = asyncio.get_event_loop().time()
                        listen_after_ts   = now + 0.7
                        if event_type == "response.audio.done":
                            last_ai_done_ts = now
                        continue

                    # ── VAD: caller started speaking ───────────────────────
                    # Record timestamp; don't interrupt yet — wait for speech_stopped
                    # to measure actual duration (filters noise, echo, brief sounds).
                    # Ignore during opening greeting to prevent phantom interrupts.
                    if event_type == "input_audio_buffer.speech_started":
                        if opening_greeting_done:
                            speech_started_at = asyncio.get_event_loop().time()
                            user_has_spoken   = True
                        continue

                    # ── VAD: caller finished speaking ──────────────────────
                    # speech_stopped fires after silence_duration_ms of quiet.
                    # elapsed = actual_speech + silence_duration_ms.
                    # Only interrupt if AI is speaking AND speech >= _MIN_SPEECH_MS.
                    if event_type == "input_audio_buffer.speech_stopped":
                        if not opening_greeting_done:
                            speech_started_at = None
                            continue
                        if speech_started_at is not None:
                            elapsed_ms = (asyncio.get_event_loop().time() - speech_started_at) * 1000
                            speech_ms  = elapsed_ms - _SILENCE_MS
                            if is_ai_speaking and speech_ms >= _MIN_SPEECH_MS:
                                print(f"[DIAG] barge-in suppressed (speech_ms={speech_ms:.0f}) — clear/cancel disabled for diagnostic")
                                # DIAGNOSTIC: interrupt disabled
                                # if _ws_open and stream_sid:
                                #     await twilio_ws.send_json({"event": "clear", "streamSid": stream_sid})
                                # await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        speech_started_at = None
                        continue

                    # ── Tool calls ─────────────────────────────────────────
                    if event_type == "response.function_call_arguments.done":
                        func_name = event["name"]
                        args      = json.loads(event["arguments"])
                        print(f"🛠️ Function call: {func_name} | client: {client_config.get('client_name')} | args: {args}")

                        if func_name == "process_agency_lead":
                            func_call_id = event.get("call_id", "")
                            if is_test:
                                print("[TEST CALL] process_agency_lead fired — skipping lead/webhook (test mode)")
                                lead_sent = True
                            else:
                                builder = _PAYLOAD_BUILDERS.get(client_config.get("client_name"))
                                if builder is None:
                                    print(f"[ERROR] No payload builder for '{client_config.get('client_name')}' — skipping lead")
                                else:
                                    lead_payload = builder(args, caller_phone, client_config)
                                    await send_lead_to_webhook(webhook_url, lead_payload)
                                    lead_sent = True

                                # Always save directly to leads table so dashboard shows the lead
                                # regardless of lead_delivery_method (webhook/whatsapp/etc.)
                                await save_lead({
                                    "phone":     caller_phone,
                                    "name":      args.get("name") or args.get("parent_name") or None,
                                    "source":    "voice",
                                    "status":    "new",
                                    "client_id": client_config.get("client_id") or None,
                                    "notes":     args.get("notes") or None,
                                })
                                print(f"[LEAD] saved to leads table for client_id={client_config.get('client_id')}")

                            # Return function result to OpenAI so the conversation continues.
                            # Without this the model stalls waiting for output and the call drops.
                            if func_call_id:
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type":    "function_call_output",
                                        "call_id": func_call_id,
                                        "output":  json.dumps({"status": "success"}),
                                    },
                                }))
                                await openai_ws.send(json.dumps({"type": "response.create"}))
                                print(f"[LEAD] function_call_output sent → response.create fired (call_id={func_call_id})")

                        if func_name == "end_call":
                            print(f"👋 end_call triggered for '{client_config.get('client_name')}' — disconnecting")
                            CALL_CONTEXT.pop(call_sid, None)
                            await asyncio.sleep(1.2)  # allow goodbye audio generation to begin
                            for _ in range(70):  # poll up to 7s
                                if not is_ai_speaking:
                                    break
                                await asyncio.sleep(0.1)
                            await asyncio.sleep(1.2)  # final tail buffer
                            _ws_open = False
                            try:
                                await twilio_ws.close()
                            except Exception as e:
                                print(f"[WS] end_call close error: {e}")
                            break

            except Exception as e:
                print(f"⚠️ OpenAI Receiver Error: {e}")

        # ── Studio keep-alive: prevent Heroku 60s idle timeout on Twilio WebSocket ─
        # Heroku's nginx drops connections when no data is written for 60 seconds.
        # During silence (AI waiting for caller), nothing is sent to twilio_ws.
        # Sending a Twilio `mark` event every 15s keeps the connection alive.
        # `mark` is a documented Media Streams message; it has no audio effect when
        # nothing is queued, and Twilio's mark-response is ignored by receive_from_twilio.
        _studio_keepalive_task = None
        if client_config.get("client_name") == "Maya BPM":
            async def _studio_keepalive():
                try:
                    while True:
                        await asyncio.sleep(15)
                        if stream_sid:
                            await twilio_ws.send_json({
                                "event": "mark",
                                "streamSid": stream_sid,
                                "mark": {"name": "keepalive"},
                            })
                except Exception:
                    pass
            _studio_keepalive_task = asyncio.create_task(_studio_keepalive())

        async def auto_disconnect_watchdog():
            """Close call if AI finished speaking and no user speech within 20s — only after user has spoken once."""
            nonlocal _ws_open
            await asyncio.sleep(5)  # don't arm until call is established
            while _ws_open:
                await asyncio.sleep(0.5)
                if not user_has_spoken:
                    continue  # never disconnect before user speaks at least once
                if last_ai_done_ts == 0.0:
                    continue
                if is_ai_speaking or speech_started_at is not None:
                    continue
                if asyncio.get_event_loop().time() - last_ai_done_ts > 20.0:
                    print("[WATCHDOG] No user speech after AI done — auto-disconnecting")
                    _ws_open = False
                    try:
                        await twilio_ws.close()
                    except Exception as e:
                        print(f"[WATCHDOG] close error: {e}")
                    return

        await asyncio.gather(receive_from_twilio(), receive_from_openai(), auto_disconnect_watchdog())

        if _studio_keepalive_task is not None:
            _studio_keepalive_task.cancel()
            try:
                await _studio_keepalive_task
            except (asyncio.CancelledError, Exception):
                pass

        # ── Safety net: force-send lead if process_agency_lead never fired ───
        if is_test:
            print("[TEST CALL] Skipping safety-net lead — test mode")
        elif not lead_sent and webhook_url:
            print(f"[SAFETY] ⚠️ process_agency_lead was never triggered — force-sending fallback lead")
            builder = _PAYLOAD_BUILDERS.get(client_config.get("client_name"))
            if builder is None:
                print(f"[SAFETY] ❌ No payload builder for '{client_config.get('client_name')}' — skipping fallback lead")
            else:
                fallback_payload = builder({}, caller_phone, client_config)
                await send_lead_to_webhook(webhook_url, fallback_payload)
        elif not lead_sent:
            print("[SAFETY] ⚠️ process_agency_lead never fired and webhook_url is empty — nothing sent")

        # Cleanup on normal call end
        CALL_CONTEXT.pop(call_sid, None)

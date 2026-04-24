"""
Browser voice endpoint — proxies browser audio to Gemini Live via WebSocket.

Audio flow:
  Browser (PCM16 16kHz) -> FastAPI WS -> Gemini Live (PCM16 16kHz)
  Gemini Live (PCM16 24kHz) -> FastAPI WS -> Browser (PCM16 24kHz)

No audio conversion needed — browser sends/receives PCM directly.
"""

import os
import json
import asyncio
import logging
import random
from datetime import datetime

import httpx
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.services.agent_config import fetch_agent_config_by_id
from app.services.voice_shared import extract_lead_from_transcript, send_voice_webhook
from app.services.lead_capture import save_lead
from app.services.dashboard_snapshot import (
    fetch_dashboard_snapshot,
    fetch_business_context,
    fetch_leads_detail,
    fetch_calls_detail,
    fetch_daily_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
_GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
_GEMINI_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    "?key={api_key}"
)

_GEMINI_VALID_VOICES = {
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir",
    "Aoede", "Leda", "Orus", "Schedar",
}

# ── Lead extraction guard ────────────────────────────────────────────────────
_MIN_TURNS = 2
_MIN_TRANSCRIPT_LEN = 50
_GREETING_ONLY = {"שלום", "היי", "ביי", "להתראות", "בוקר טוב"}


def _is_meaningful_transcript(lines: list[str]) -> bool:
    """Check if transcript warrants lead extraction."""
    user_turns = [l for l in lines if l.startswith("לקוח:")]
    if len(user_turns) < _MIN_TURNS:
        return False
    combined = " ".join(lines)
    if len(combined) < _MIN_TRANSCRIPT_LEN:
        return False
    user_words = set()
    for turn in user_turns:
        text = turn.replace("לקוח:", "").strip()
        user_words.update(text.split())
    if user_words.issubset(_GREETING_ONLY):
        return False
    return True


# ── Assistant mode ───────────────────────────────────────────────────────────

_ASSISTANT_PROMPT = """\
כשאת פותחת — תפתחי עם אנרגיה, קצר וחד.
אחרי הפתיחה — אם יש signal אמיתי בנתונים (ליד שמחכה, משהו דחוף), תוסיפי שורה אחת ממוקדת.
אם הכל רגוע — פשוט תפתחי ותחכי. לא להמציא דחיפות כשאין.

━━ מי את ━━
את מאיה. את יושבת לצד בעל העסק ורואה את אותו מסך — רק שאת גם יודעת מה לעשות עם מה שאת רואה.
את לא מחכה שישאלו. אם את רואה משהו — את מעלה את זה.

━━ איך את חושבת ━━
לפני שאת עונה, את שואלת את עצמך:
מה הדבר הכי חשוב כאן? מה הפעולה הכי נכונה עכשיו?
התשובה שלך מתחילה משם — לא מתיאור של כל מה שיש.

כשיש data — את מפרידה בין signal ל-noise.
לא כל נתון שווה אותו דבר. ליד שמחכה יומיים זה signal. ליד שנפתח לפני דקה זה רקע.
את מובילה עם מה שחשוב, והשאר רק אם שואלים.

כשיש כמה דברים — את בוחרת אחד מרכזי ומתחילה ממנו.
לא רשימות כברירת מחדל. רשימה רק אם ביקשו אחת.

━━ מתי את יוזמת ━━
את לא רק עונה — את גם שמה לב.
אם יש משהו בנתונים שדורש תשומת לב — את מעלה את זה, גם אם לא שאלו.
ליד שמחכה יותר מדי. שיחה שלא נסגרה. הזדמנות שקל לפספס.
את עושה את זה בזמן הנכון, לא כל הזמן — רק כשיש באמת ערך.
"אגב, יש פה מישהו שכדאי לחזור אליו" — ולא רשימה של כל מה שפתוח.

━━ איך את מדברת ━━
את מכוונת לפעולה, לא נותנת הוראות.
"הייתי מתחילה מהליד הזה" ולא "תתקשר לליד".
"שווה להסתכל על זה" ולא "תבדוק את זה".
ביטחון שקט, בלי דרמה, בלי הגזמה.

כשהמצב רגוע — את רגועה. את לא ממציאה דחיפות.
כשיש בעיה אמיתית — את מעלה אותה ישר, בלי לעטוף.
כשיש הזדמנות — את מבליטה אותה בקצרה.

את לא חוזרת על אותה תבנית. את לא פותחת כל תשובה אותו דבר.
את קצרה כשמספיק, ומרחיבה כשזה שווה. את סומכת על עצמך.

אחרי שענית — תזרקי follow-up טבעי כשמתאים:
"רוצה שניכנס לזה?" / "נבדוק את זה יחד?" / "אפשר גם להסתכל על..."
לא תמיד — רק כשיש באמת לאן להמשיך.

━━ הצעת פעולות ━━
כשאת רואה שמתאים — את יכולה להציע להכין משהו.
לא בכל תשובה. רק כשיש ליד או מצב שקורא לפעולה.
את מציעה, לא מבצעת. את שואלת לפני שאת מנסחת.

דוגמאות:
- "יש פה ליד שמחכה מאתמול. רוצה שאכין לך הודעת WhatsApp?"
- "בא לך שאנסח משהו קצר לשלוח לו?"
- "הייתי חוזרת אליו. רוצה שאכין לך טיוטה?"

אם המשתמש אומר כן — את מנסחת הודעה מלאה, מוכנה, בטון שמתאים לעסק.
הודעה קצרה, אישית, עם שם הליד אם יש.
לא פורמלית מדי, לא שיווקית — כמו הודעה שבנאדם אמיתי שולח.

מה את לא עושה:
- לא שולחת בפועל
- לא מתקשרת
- לא משנה סטטוס של ליד
- רק מנסחת ומציעה

━━ הכרת העסק ━━
את מכירה את העסקים שאת עובדת איתם (ראי למטה).
כשאת נותנת המלצות — את מתאימה אותן לסוג העסק.
מה נחשב ליד חם, מה חשוב למכירה, איזה follow-up נכון — משתנה לפי העסק.
אם אין לך מידע ספציפי על עסק — תתייחסי באופן כללי.

━━ ניווט ━━
כשמבקשים לראות משהו — תגידי "פותחת" ותפתחי.
מה שזמין: לידים, שיחות, סוכנים, הגדרות של סוכן ספציפי, נכסים, בדיקה, מאגר ידע, דשבורד.
את מכירה את כל הסוכנים (ראי למטה). אם לא ברור למי מתכוונים — תשאלי.

{snapshot}
"""

_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "leads": ("לידים", "ליד", "חמים", "דחוף", "לקוחות", "פניות", "מסך הלידים"),
    "calls": ("שיחות", "שיחה", "טלפון", "התקשרו", "מסך השיחות"),
    "summary": ("סיכום", "מה קרה", "מה המצב", "מה חדש", "עדכון"),
    "agents": ("סוכנים", "סוכן", "נציגה", "נציג", "נציגות", "הגדרות", "מסך הסוכנים", "מסך ההגדרות"),
    "dashboard": ("דשבורד", "מסך ראשי", "עמוד ראשי", "בית", "חזרה"),
    "knowledge": ("ידע", "מאגר ידע", "knowledge", "בסיס ידע", "מסך הידע"),
    "assets": ("נכסים", "assets", "קבצים", "חומרים"),
    "preview": ("בדיקה", "preview", "בדוק את", "לבדוק את"),
}

_INTENT_UI_ACTIONS: dict[str, dict] = {
    "leads": {"action": "open_tab", "target": "leads"},
    "calls": {"action": "open_tab", "target": "calls"},
    "agents": {"action": "open_tab", "target": "agents"},
    "dashboard": {"action": "open_tab", "target": "dashboard"},
    "knowledge": {"action": "open_tab", "target": "knowledge"},
}

_INJECTION_COOLDOWN_S = 10


def _detect_intent(text: str) -> str | None:
    """Detect intent from user transcript text."""
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return intent
    return None


# ── WebSocket endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws/voice-browser")
async def stream_browser(browser_ws: WebSocket, agent_id: str = Query(default=""), mode: str = Query(default="preview")):
    """
    Proxy WebSocket: Browser <-> Gemini Live.
    Accepts PCM16 16kHz from browser, forwards to Gemini, returns PCM16 24kHz.
    """
    await browser_ws.accept()
    is_preview = (mode == "preview")
    logger.info("[BROWSER-WS] Connection accepted - agent_id=%s mode=%s", agent_id, mode)

    # ── Validate prerequisites ───────────────────────────────────────────
    if not _GEMINI_API_KEY:
        await browser_ws.send_json({"type": "error", "message": "Gemini not configured"})
        await browser_ws.close()
        return

    if not agent_id:
        await browser_ws.send_json({"type": "error", "message": "agent_id is required"})
        await browser_ws.close()
        return

    # ── Load agent config ────────────────────────────────────────────────
    agent_cfg = await fetch_agent_config_by_id(agent_id)
    if agent_cfg.get("fallback_used"):
        logger.warning("[BROWSER-WS] No agent found for id=%s - using fallback", agent_id)

    client_name = agent_cfg.get("client_name", "")
    client_id = agent_cfg.get("client_id") or None
    webhook_url = agent_cfg.get("webhook_url", "")
    first_message = (agent_cfg.get("first_message") or "").strip()

    # ── Load agent name→id map for assistant navigation ────────────────
    _agent_name_map: dict[str, str] = {}  # lowercase name → agent_id
    if not is_preview:
        try:
            _sb_url = os.getenv("SUPABASE_URL", "")
            _sb_key = os.getenv("SUPABASE_SERVICE_KEY", "")
            if _sb_url and _sb_key:
                async with httpx.AsyncClient(timeout=5.0) as _c:
                    _resp = await _c.get(
                        f"{_sb_url}/rest/v1/agents_config",
                        params={"select": "id,agent_name", "is_active": "eq.true"},
                        headers={
                            "apikey": _sb_key,
                            "Authorization": f"Bearer {_sb_key}",
                        },
                    )
                    for _row in _resp.json():
                        _name = (_row.get("agent_name") or "").strip().lower()
                        if _name:
                            _agent_name_map[_name] = _row["id"]
                # Also add partial name variants for matching
                for _row in _resp.json():
                    _name = (_row.get("agent_name") or "").strip()
                    _id = _row["id"]
                    # Add individual words as fallback (e.g. "bpm" → Maya BPM)
                    for _word in _name.split():
                        _w = _word.strip().lower()
                        if _w and len(_w) > 2 and _w not in ("מאיה", "maya", "-"):
                            _agent_name_map.setdefault(_w, _id)
                logger.info("[BROWSER-WS] Agent map loaded: %s", list(_agent_name_map.keys()))
        except Exception as exc:
            logger.warning("[BROWSER-WS] Failed to load agent map: %s", exc)

    # ── Build system instruction ─────────────────────────────────────────
    if is_preview:
        # Preview mode: use agent's customer-facing prompt
        system_instruction = agent_cfg.get("prompt_override", "")
        if first_message and system_instruction:
            system_instruction = (
                f'פתחי את השיחה תמיד עם המשפט הבא בדיוק:\n'
                f'"{first_message}"\n\n'
                f'{system_instruction}'
            )
    else:
        # Assistant mode: dashboard assistant prompt with live data snapshot
        # Pass None to get ALL agents/leads (not filtered by single client)
        snapshot = await fetch_dashboard_snapshot(None)
        # Load business context from knowledge_items for all active agents
        all_agent_ids = list(_agent_name_map.values())
        biz_context = await fetch_business_context(all_agent_ids)
        full_context = f"{biz_context}\n\n{snapshot}" if biz_context else snapshot
        system_instruction = _ASSISTANT_PROMPT.replace("{snapshot}", full_context)
        first_message = ""  # assistant doesn't use agent's first_message — greeting is in prompt
        logger.info("[BROWSER-WS] Assistant mode - snapshot loaded (%d chars), biz context (%d chars)", len(snapshot), len(biz_context))

    # ── Resolve voice ────────────────────────────────────────────────────
    raw_voice = (agent_cfg.get("voice") or "").strip()
    gemini_voice = raw_voice if raw_voice in _GEMINI_VALID_VOICES else "Zephyr"
    logger.info("[BROWSER-WS] Agent='%s' voice=%s", client_name, gemini_voice)

    # ── Connect to Gemini Live ───────────────────────────────────────────
    gemini_url = _GEMINI_WS_URL.format(api_key=_GEMINI_API_KEY)
    gemini_ws = None
    try:
        gemini_ws = await websockets.connect(gemini_url, ping_interval=None)
        logger.info("[BROWSER-WS] Gemini Live connected - model=%s", _GEMINI_LIVE_MODEL)
    except Exception as e:
        logger.error("[BROWSER-WS] Gemini connect failed: %s", e)
        await browser_ws.send_json({"type": "error", "message": "Cannot connect to voice service"})
        await browser_ws.close()
        return

    # ── Send Gemini setup message ────────────────────────────────────────
    setup_msg = {
        "setup": {
            "model": f"models/{_GEMINI_LIVE_MODEL}",
            "generation_config": {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {"voice_name": gemini_voice}
                    }
                },
            },
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "silence_duration_ms": 300,
                    "start_of_speech_sensitivity": "START_SENSITIVITY_HIGH",
                },
            },
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
        }
    }

    try:
        await gemini_ws.send(json.dumps(setup_msg))
        setup_ack = await asyncio.wait_for(gemini_ws.recv(), timeout=10.0)
        logger.info("[BROWSER-WS] Gemini setup ack received")
    except Exception as e:
        logger.error("[BROWSER-WS] Gemini setup failed: %s", e)
        await browser_ws.send_json({"type": "error", "message": "Voice service setup failed"})
        await gemini_ws.close()
        await browser_ws.close()
        return

    # ── Trigger opening greeting ─────────────────────────────────────────
    if first_message or not is_preview:
        if is_preview:
            _trigger = "שלום"
        else:
            _triggers = [
                "היי, איך אנחנו מנצחים היום?",
                "יאללה, על מה שמים פוקוס?",
                "מה קורה, בוא נזיז משהו",
                "אהלן, מה על הפרק?",
                "היי, בוא נראה איפה אנחנו",
                "מה העניינים, צריך עזרה עם משהו?",
            ]
            _trigger = random.choice(_triggers)
        await gemini_ws.send(json.dumps({"realtime_input": {"text": _trigger}}))
        logger.info("[BROWSER-WS] Opening trigger: '%s' (mode=%s)", _trigger, mode)

    await browser_ws.send_json({"type": "ready"})
    await browser_ws.send_json({"type": "state", "state": "listening"})
    logger.info("[BROWSER-WS] Session ready - streaming audio")

    # ── Shared state ─────────────────────────────────────────────────────
    transcript_lines: list[str] = []
    _speaking = False
    _shutdown = asyncio.Event()  # signals all loops to exit
    _turn_count = 0
    # Injection guards (assistant mode only)
    _last_injected_intent: str | None = None
    _last_injection_time: float = 0
    _last_injection_turn: int = 0
    _input_buffer: list[str] = []  # accumulates input transcript fragments per turn
    _output_buffer: list[str] = []  # accumulates output transcript fragments per turn
    _user_approved_draft = False  # tracks if user approved message drafting this turn

    # ── Browser -> Gemini loop ───────────────────────────────────────────
    async def browser_to_gemini():
        try:
            while not _shutdown.is_set():
                raw = await browser_ws.receive_text()
                msg = json.loads(raw)

                if msg.get("type") == "audio":
                    await gemini_ws.send(json.dumps({
                        "realtime_input": {
                            "audio": {
                                "data": msg["data"],
                                "mimeType": "audio/pcm;rate=16000",
                            }
                        }
                    }))

                elif msg.get("type") == "pong":
                    pass  # heartbeat response

                elif msg.get("type") == "end":
                    logger.info("[BROWSER-WS] Client sent end - closing")
                    break

        except WebSocketDisconnect:
            logger.info("[BROWSER-WS] Browser disconnected")
        except Exception as e:
            logger.warning("[BROWSER-WS] Browser receiver error: %s", e)
        finally:
            _shutdown.set()

    # ── Gemini -> Browser loop ───────────────────────────────────────────
    async def gemini_to_browser():
        nonlocal _speaking, _turn_count, _last_injected_intent, _last_injection_time, _last_injection_turn, _user_approved_draft

        try:
            async for raw in gemini_ws:
                if _shutdown.is_set():
                    break
                msg = json.loads(raw)
                server_content = msg.get("serverContent", {})

                # Interrupted (barge-in)
                if server_content.get("interrupted"):
                    _speaking = False
                    await browser_ws.send_json({"type": "interrupted"})
                    await browser_ws.send_json({"type": "state", "state": "listening"})
                    continue

                # Input transcript
                input_t = server_content.get("inputTranscription", {})
                if input_t.get("text"):
                    logger.info("[BROWSER-WS] transcript_in: %s", input_t["text"][:60])
                    transcript_lines.append(f"לקוח: {input_t['text']}")
                    await browser_ws.send_json({
                        "type": "transcript_in",
                        "text": input_t["text"],
                    })

                    # ── Data injection (assistant mode only) ─────────
                    if not is_preview:
                        _input_buffer.append(input_t["text"])
                        combined_input = " ".join(_input_buffer)

                        # Detect user approving a message draft
                        _DRAFT_APPROVAL_KW = ("כן", "תכיני", "הכיני", "תנסחי", "נסחי", "הודעה", "תכתבי")
                        if any(kw in combined_input for kw in _DRAFT_APPROVAL_KW):
                            _user_approved_draft = True

                        detected = _detect_intent(combined_input)
                        if detected:
                            logger.info("[BROWSER-WS] Intent detected: %s from '%s'", detected, combined_input[:60])
                        now = asyncio.get_event_loop().time()
                        if (
                            detected
                            and (
                                detected != _last_injected_intent
                                or now - _last_injection_time > _INJECTION_COOLDOWN_S
                                or _turn_count != _last_injection_turn
                            )
                        ):
                            _last_injected_intent = detected
                            _last_injection_time = now
                            _last_injection_turn = _turn_count

                            injection = None
                            if detected == "leads":
                                injection = await fetch_leads_detail(client_id)
                            elif detected == "calls":
                                injection = await fetch_calls_detail(client_id)
                            elif detected == "summary":
                                injection = await fetch_daily_summary(client_id)

                            if injection:
                                await gemini_ws.send(json.dumps({
                                    "realtime_input": {"text": injection}
                                }))
                                logger.info(
                                    "[BROWSER-WS] Injected %s data (%d chars)",
                                    detected, len(injection),
                                )

                            ui = _INTENT_UI_ACTIONS.get(detected)
                            if ui:
                                await browser_ws.send_json({
                                    "type": "ui_action",
                                    **ui,
                                })
                                logger.info(
                                    "[BROWSER-WS] Sent ui_action: %s -> %s",
                                    ui.get("action"), ui.get("target"),
                                )

                # Output transcript
                output_t = server_content.get("outputTranscription", {})
                if output_t.get("text"):
                    logger.info("[BROWSER-WS] transcript_out: %s", output_t["text"][:60])
                    transcript_lines.append(f"מאיה: {output_t['text']}")

                    # Accumulate output for turn-level analysis
                    if not is_preview:
                        _output_buffer.append(output_t["text"])
                        # Detect draft approval from Maya's output
                        # (fallback when input transcript is in wrong language)
                        _DRAFT_OUTPUT_MARKERS = ("הנה הודעה", "הנה ההודעה", "אנסח", "הייתי שולחת", "אפשר לשלוח", "הנה טיוטה", "הנה:")
                        if any(m in output_t["text"] for m in _DRAFT_OUTPUT_MARKERS):
                            _user_approved_draft = True
                    await browser_ws.send_json({
                        "type": "transcript_out",
                        "text": output_t["text"],
                    })

                # Audio chunks
                model_turn = server_content.get("modelTurn", {})
                parts = model_turn.get("parts", [])
                for part in parts:
                    inline_data = part.get("inlineData", {})
                    data = inline_data.get("data", "")
                    mime = inline_data.get("mimeType", "")
                    if data and "audio" in mime:
                        if not _speaking:
                            _speaking = True
                            await browser_ws.send_json({
                                "type": "state",
                                "state": "speaking",
                            })
                        await browser_ws.send_json({
                            "type": "audio",
                            "data": data,
                        })

                # Turn complete
                if server_content.get("turnComplete"):
                    _speaking = False
                    _turn_count += 1

                    # ── Process accumulated output for UI actions ────
                    if not is_preview and _output_buffer:
                        full_output = " ".join(_output_buffer)
                        if "פותחת" in full_output or "פתחתי" in full_output:
                            now_out = asyncio.get_event_loop().time()
                            if now_out - _last_injection_time > 3:
                                # Check for specific agent name
                                _agent_matched = False
                                out_lower = full_output.lower()
                                for _aname, _aid in _agent_name_map.items():
                                    if _aname in out_lower:
                                        _last_injection_time = now_out
                                        # Detect sub-tab (assets / preview)
                                        _sub = "settings"
                                        if any(w in out_lower for w in ("נכסים", "assets", "חומרים")):
                                            _sub = "assets"
                                        elif any(w in out_lower for w in ("בדיקה", "preview", "בדוק")):
                                            _sub = "voice"
                                        await browser_ws.send_json({
                                            "type": "ui_action",
                                            "action": "open_agent",
                                            "target": _aid,
                                            "tab": _sub,
                                        })
                                        logger.info(
                                            "[BROWSER-WS] Sent ui_action: open_agent -> %s (tab=%s)",
                                            _aname, _sub,
                                        )
                                        _agent_matched = True
                                        break

                                # Fall back to generic tab
                                if not _agent_matched:
                                    out_detected = _detect_intent(full_output)
                                    if out_detected and out_detected in _INTENT_UI_ACTIONS:
                                        _last_injection_time = now_out
                                        ui = _INTENT_UI_ACTIONS[out_detected]
                                        await browser_ws.send_json({
                                            "type": "ui_action",
                                            **ui,
                                        })
                                        logger.info(
                                            "[BROWSER-WS] Sent ui_action: %s -> %s",
                                            ui.get("action"), ui.get("target"),
                                        )

                    # ── Action proposal (draft message) ─────────────
                    if not is_preview and _user_approved_draft and _output_buffer:
                        full_out = " ".join(_output_buffer)

                        # Extract the actual message from Maya's output.
                        # Maya typically says: "הנה הודעה: היי משה..." or "אפשר לשלוח: ..."
                        _MESSAGE_MARKERS = (
                            "הנה:", "הנה הודעה:", "הנה ההודעה:",
                            "אפשר לשלוח:", "הייתי שולחת:",
                            "נוסח אפשרי:", "הודעה:", "טיוטה:",
                            "אפשר לכתוב:", "הייתי כותבת:",
                        )
                        _draft_message = full_out  # fallback: full output
                        for _marker in _MESSAGE_MARKERS:
                            if _marker in full_out:
                                _draft_message = full_out.split(_marker, 1)[1].strip()
                                break
                        # Also try splitting on quotation marks (היי "משה...")
                        if _draft_message == full_out and '"' in full_out:
                            _parts = full_out.split('"')
                            if len(_parts) >= 2:
                                _quoted = _parts[1].strip()
                                if len(_quoted) > 10:
                                    _draft_message = _quoted

                        # Extract lead name from recent transcript
                        _lead_name = ""
                        _all_text = full_out + " " + " ".join(transcript_lines[-10:])
                        for _tl in reversed(transcript_lines[-10:]):
                            for _word in _tl.split():
                                _w = _word.strip(".,!?\"׳'")
                                if len(_w) > 1 and _w[0].isupper() or any(c in "אבגדהוזחטיכלמנסעפצקרשת" for c in _w):
                                    # Simple heuristic: Hebrew names in lead context
                                    pass
                            break

                        # Try to find a name mentioned by Maya (e.g. "היי משה")
                        import re
                        _name_match = re.search(r'היי\s+([א-ת]+)', _draft_message)
                        if _name_match:
                            _lead_name = _name_match.group(1)
                        if not _lead_name:
                            # Fallback: scan recent transcript for lead names
                            for _tl in reversed(transcript_lines[-10:]):
                                for _known in ("משה", "רחל", "יוסי", "דניאל", "שרה", "תמר", "לידור"):
                                    if _known in _tl:
                                        _lead_name = _known
                                        break
                                if _lead_name:
                                    break

                        if len(_draft_message) > 10:
                            await browser_ws.send_json({
                                "type": "action_proposal",
                                "action": "prepare_followup_message",
                                "status": "draft_only",
                                "lead_name": _lead_name or "ליד",
                                "channel": "whatsapp",
                                "message": _draft_message.strip(),
                            })
                            logger.info(
                                "[BROWSER-WS] Sent action_proposal for '%s': %s",
                                _lead_name or "unknown",
                                _draft_message[:60],
                            )
                        _user_approved_draft = False

                    _input_buffer.clear()
                    _output_buffer.clear()
                    await browser_ws.send_json({"type": "turn_complete"})
                    await browser_ws.send_json({
                        "type": "state",
                        "state": "listening",
                    })

        except Exception as e:
            logger.warning("[BROWSER-WS] Gemini receiver error: %s", e)
            try:
                await browser_ws.send_json({
                    "type": "error",
                    "message": "Voice connection lost",
                })
            except Exception:
                pass
        finally:
            _shutdown.set()

    # ── Heartbeat loop ───────────────────────────────────────────────────
    async def heartbeat_loop():
        try:
            while not _shutdown.is_set():
                await asyncio.sleep(15)
                if _shutdown.is_set():
                    break
                await browser_ws.send_json({"type": "ping"})
        except Exception:
            pass  # connection closed — loop exits naturally

    # ── Run all loops concurrently ───────────────────────────────────────
    try:
        await asyncio.gather(
            browser_to_gemini(),
            gemini_to_browser(),
            heartbeat_loop(),
        )
    finally:
        logger.info("[BROWSER-WS] Session ended - cleanup")

        # ── Lead extraction (skipped in preview and assistant modes) ────
        if mode != "live":
            logger.info("[BROWSER-WS] %s mode - skipping lead extraction/save/webhook", mode)
        elif _is_meaningful_transcript(transcript_lines):
            transcript_text = "\n".join(transcript_lines)
            logger.info(
                "[BROWSER-WS] Extracting lead from %d transcript lines",
                len(transcript_lines),
            )
            extracted = await extract_lead_from_transcript(transcript_text, "browser")

            if extracted:
                topic = extracted.get("topic") or None
                notes = extracted.get("notes") or None
                summary_parts = []
                if topic:
                    summary_parts.append(f"נושא: {topic}")
                if notes:
                    summary_parts.append(f"פרטים: {notes}")

                await save_lead({
                    "phone": extracted.get("phone_number") or "browser",
                    "source": "browser_voice",
                    "status": "new",
                    "client_id": client_id,
                    "name": extracted.get("name") or None,
                    "notes": notes,
                    "last_call_summary": " | ".join(summary_parts) or None,
                    "last_call_topic": topic,
                    "last_call_at": datetime.utcnow().isoformat(),
                })
                logger.info(
                    "[BROWSER-WS] Lead saved - name=%s",
                    extracted.get("name"),
                )

                if webhook_url:
                    await send_voice_webhook(webhook_url, {
                        "timestamp": datetime.now().isoformat(),
                        "source": "browser_voice",
                        "client": client_name,
                        "caller_phone": "browser",
                        "name": extracted.get("name", ""),
                        "phone_number": extracted.get("phone_number", ""),
                        "topic": extracted.get("topic", ""),
                        "notes": extracted.get("notes", ""),
                    })
        else:
            logger.info(
                "[BROWSER-WS] Transcript too short/trivial - skipping lead extraction"
            )

        # Close connections
        try:
            await gemini_ws.close()
        except Exception:
            pass
        try:
            await browser_ws.close()
        except Exception:
            pass

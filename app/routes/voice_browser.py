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

אם המשתמש אומר כן — את מנסחת הודעה מלאה, מוכנה לשליחה.

חשוב מאוד — פורמט ההודעה:
את חייבת לסמן את ההודעה ללקוח בצורה הבאה בדיוק:

הודעה ללקוח:
[כאן הטקסט המדויק של ההודעה ללקוח, בלי הסברים]

אחרי הסימון, את כותבת רק את ההודעה עצמה — בלי תגובות אליי, בלי "אתה יכול לשלוח", בלי "הכרטיס מופיע".
ההודעה קצרה, אישית, עם שם הליד. כמו הודעה שבנאדם אמיתי שולח.

אם רוצה להגיד לי משהו אחרי, תגידי "סיימתי" ואז תוסיפי את ההערה.
המערכת מזהה רק את הטקסט אחרי "הודעה ללקוח:" ולפני "סיימתי" או סוף הדיבור.

חוקים חשובים על מה לא להגיד:
- אל תזכירי "כפתור וואטסאפ", "כפתור שליחה", "לחץ על", "תלחץ".
- אל תגידי שיש כפתור או פעולה אם לא השתמשת ב-"הודעה ללקוח:".
- אם השתמשת ב-"הודעה ללקוח:" — תגידי בקצרה: "הכנתי לך טיוטה, היא מופיעה בכרטיס לאישור." ולא יותר.
- אם המשתמש לא ביקש לנסח, אל תציעי להכין טיוטה כל הזמן — רק כשמתאים.
- את לא שולחת בעצמך, והמשתמש לא צריך הוראות שליחה ממך — הכרטיס מטפל בזה.

━━ הכרת העסק ━━
את מכירה את העסקים שאת עובדת איתם (ראי למטה).
כשאת נותנת המלצות — את מתאימה אותן לסוג העסק.
מה נחשב ליד חם, מה חשוב למכירה, איזה follow-up נכון — משתנה לפי העסק.
אם אין לך מידע ספציפי על עסק — תתייחסי באופן כללי.

━━ ניווט ━━
תגידי "פותחת" רק כשהמשתמש ביקש במפורש לפתוח/לעבור/לראות משהו (פתחי, תראי לי, תעברי ל..., קחי אותי ל...).
אם הוא רק שאל שאלה על נתונים — תעני בקצרה, אל תפתחי טאב, ואל תגידי "פותחת".
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

# User must use one of these verbs for ui_action to fire (data injection still
# fires on keywords alone). Prevents tab switches when user merely discusses a topic.
_OPEN_VERBS: tuple[str, ...] = (
    "פתחי", "פתח", "תפתחי", "תפתח", "פתחו",
    "תראי", "תראה", "הראי", "הראה", "תראי לי", "תראה לי",
    "תעברי", "תעבור", "עברי", "עבור",
    "תציגי", "הציגי", "תציג", "הצג",
    "קחי אותי", "קח אותי",
    "תני לראות", "תן לראות",
    "open", "show", "go to", "take me",
)


def _detect_intent(text: str) -> str | None:
    """Detect intent from user transcript text."""
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return intent
    return None


# ── Draft message extraction ─────────────────────────────────────────────────

# Strict marker — Maya is instructed to use exactly this before customer messages
_DRAFT_STRICT_MARKER = "הודעה ללקוח:"

# Commentary markers that terminate the draft
_DRAFT_END_MARKERS = (
    "סיימתי",
    "זה מוכן", "אתה יכול", "את יכולה",
    "רוצה שאשלח", "רוצה לשלוח", "שלח מ",
    "הכרטיס מופיע", "הכרטיס כבר", "מופיע על המסך",
    "לחץ על", "לחצי על", "אפשר לשלוח ישירות",
    "שלח ישירות", "מכפתור", "דרך הכפתור",
    "אני לא יכולה לשלוח", "אני לא שולחת",
    "בוא ניגש", "ראיתי שאת", "רוצה שנבדוק",
    # Operator-facing questions (cut here)
    "נשלח?", "נשלח ", "נשלח.",
    "או שנעבור", "או שנמשיך", "או שנעשה",
    "מה דעתך", "מה את חושב", "מה אתה חושב",
    "רוצה שא", "רוצה לעבור", "רוצה לראות",
    "מתאים לך", "טוב לך", "נראה לך",
    "ממשיכים", "נמשיך",
)


def _extract_draft_message(full_out: str) -> str | None:
    """
    Extract customer-facing draft from Maya's output.
    Returns None if no clear draft is found — caller should skip the proposal.

    Priority:
    1. Text after the strict marker "הודעה ללקוח:"
    2. Long quoted text (>= 20 chars) inside straight or curly quotes
    3. None — do not guess
    """
    # 1. Strict marker — most reliable
    if _DRAFT_STRICT_MARKER in full_out:
        draft = full_out.split(_DRAFT_STRICT_MARKER, 1)[1].strip()

        # Stop at first paragraph break (\n\n or double space-period)
        for sep in ("\n\n", "\n"):
            if sep in draft:
                draft = draft.split(sep, 1)[0]
                break

        # Truncate before any commentary marker
        for end_marker in _DRAFT_END_MARKERS:
            idx = draft.find(end_marker)
            if idx > 5:
                draft = draft[:idx]

        # Truncate at first '?' that is followed by another sentence
        # (operator question like "נשלח?" comes after the customer message)
        q_idx = draft.find("?")
        if q_idx > 10 and q_idx < len(draft) - 2:
            # If there's content after '?', the '?' likely starts operator commentary
            # — but only if the question is short (< 30 chars from prev punctuation)
            # to avoid cutting legitimate customer-facing questions
            prev_break = max(draft.rfind(".", 0, q_idx), draft.rfind("\n", 0, q_idx), 0)
            if q_idx - prev_break < 30 and any(w in draft[prev_break:q_idx + 1] for w in ("נשלח", "נעבור", "נמשיך", "נעשה")):
                draft = draft[:prev_break + 1] if prev_break > 0 else draft[:q_idx]

        draft = draft.strip(" .,!؟\n")
        if len(draft) >= 10:
            return draft
        return None

    # 2. Quoted text — accept only long quotes (likely a real message, not a phrase)
    for open_q, close_q in (('"', '"'), ('“', '”'), ('"', '"'), ("'", "'")):
        if open_q in full_out and close_q in full_out:
            parts = full_out.split(open_q)
            # Pick segments at odd indices (between quotes)
            quoted = []
            for i in range(1, len(parts)):
                seg = parts[i]
                if close_q in seg and open_q != close_q:
                    seg = seg.split(close_q, 1)[0]
                seg = seg.strip()
                if len(seg) >= 20:
                    quoted.append(seg)
            if quoted:
                return max(quoted, key=len)

    # 3. No reliable draft — caller should skip proposal
    return None


# ── WebSocket endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws/voice-browser")
async def stream_browser(browser_ws: WebSocket, agent_id: str = Query(default=""), mode: str = Query(default="preview"), token: str = Query(default="")):
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
    # Fail closed: unknown agent_id / inactive agent / empty prompt → reject.
    # Hardcoded fallback prompts are not allowed.
    if agent_cfg.get("fallback_used") or not agent_cfg.get("prompt_override"):
        logger.warning("[BROWSER-WS] No active agent for id=%s — closing (fail closed)", agent_id)
        await browser_ws.send_json({"type": "error", "message": "Agent not found"})
        await browser_ws.close()
        return

    # ── Ownership validation via Supabase JWT (fail-closed) ────────────
    _sb_url = os.getenv("SUPABASE_URL", "")
    _sb_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not token or not _sb_url or not _sb_key:
        logger.warning("[BROWSER-WS] Missing token or Supabase config — rejecting")
        await browser_ws.send_json({"type": "error", "message": "Unauthorized"})
        await browser_ws.close()
        return

    try:
        async with httpx.AsyncClient(timeout=5.0) as _c:
            _user_resp = await _c.get(
                f"{_sb_url}/auth/v1/user",
                headers={
                    "apikey": _sb_key,
                    "Authorization": f"Bearer {token}",
                },
            )
            if _user_resp.status_code != 200:
                logger.warning("[BROWSER-WS] Token validation failed: %d", _user_resp.status_code)
                await browser_ws.send_json({"type": "error", "message": "Unauthorized"})
                await browser_ws.close()
                return

            _user_data = _user_resp.json()
            _meta = _user_data.get("user_metadata", {})
            _is_admin = _meta.get("role") == "admin"
            if not _is_admin:
                _user_client_id = _meta.get("client_id")
                _agent_client_id = agent_cfg.get("client_id")
                if not _user_client_id or _user_client_id != _agent_client_id:
                    logger.warning("[BROWSER-WS] Ownership mismatch - user_client=%s agent_client=%s", _user_client_id, _agent_client_id)
                    await browser_ws.send_json({"type": "error", "message": "Forbidden"})
                    await browser_ws.close()
                    return
    except Exception as exc:
        logger.warning("[BROWSER-WS] Token validation error: %s — rejecting", exc)
        await browser_ws.send_json({"type": "error", "message": "Unauthorized"})
        await browser_ws.close()
        return

    logger.info("[BROWSER-WS] Auth passed - admin=%s", _is_admin)

    client_name = agent_cfg.get("client_name", "")
    client_id = agent_cfg.get("client_id") or None
    webhook_url = agent_cfg.get("webhook_url", "")
    first_message = (agent_cfg.get("first_message") or "").strip()

    logger.info(
        "[ROUTE-AUDIT] route=voice_browser mode=%s agent_id=%s "
        "resolved_client_id=%s fallback_used=%s knowledge_items_count=%s admin=%s",
        mode, agent_cfg.get("agent_id"), client_id,
        bool(agent_cfg.get("fallback_used")),
        agent_cfg.get("knowledge_items_count", 0),
        _is_admin,
    )

    # ── Load agent name→id map for assistant navigation ────────────────
    # Non-admin sessions are restricted to the user's own client_id; admin
    # sessions see every agent so cross-client navigation works.
    _agent_name_map: dict[str, str] = {}  # lowercase name → agent_id
    if not is_preview:
        try:
            _sb_url = os.getenv("SUPABASE_URL", "")
            _sb_key = os.getenv("SUPABASE_SERVICE_KEY", "")
            if _sb_url and _sb_key:
                _params = {"select": "id,agent_name", "is_active": "eq.true"}
                if not _is_admin and client_id:
                    _params["client_id"] = f"eq.{client_id}"
                async with httpx.AsyncClient(timeout=5.0) as _c:
                    _resp = await _c.get(
                        f"{_sb_url}/rest/v1/agents_config",
                        params=_params,
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
        # Assistant mode: dashboard assistant prompt with live data snapshot.
        # Admin sees all clients (snapshot scope = None). Non-admin is locked to
        # their own client_id so the assistant cannot read other tenants' data.
        _scope_client_id = None if _is_admin else client_id
        snapshot = await fetch_dashboard_snapshot(_scope_client_id)
        # Business context: only load knowledge for agents that belong to the
        # session's scope (already filtered above for non-admin).
        all_agent_ids = list(_agent_name_map.values())
        biz_context = await fetch_business_context(all_agent_ids)
        full_context = f"{biz_context}\n\n{snapshot}" if biz_context else snapshot
        system_instruction = _ASSISTANT_PROMPT.replace("{snapshot}", full_context)
        first_message = ""  # assistant doesn't use agent's first_message — greeting is in prompt
        logger.info(
            "[BROWSER-WS] Assistant mode - snapshot loaded (%d chars), biz context (%d chars), scope_client_id=%s",
            len(snapshot), len(biz_context), _scope_client_id,
        )

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
                    "silence_duration_ms": 500,
                    "start_of_speech_sensitivity": "START_SENSITIVITY_LOW",
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
    _user_approved_draft = False  # tracks if user approved message drafting
    _draft_pending = False  # True = approval detected, waiting for next turn with the actual draft
    _session_leads: list[dict] = []  # [{id, name, status, topic}] — loaded from data injection
    _last_draft: dict | None = None  # {message, lead_name} — persisted for Gemini recall

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
        nonlocal _speaking, _turn_count, _last_injected_intent, _last_injection_time, _last_injection_turn, _user_approved_draft, _draft_pending, _session_leads, _last_draft

        try:
            async for raw in gemini_ws:
                if _shutdown.is_set():
                    break
                msg = json.loads(raw)
                server_content = msg.get("serverContent", {})

                # Interrupted (barge-in)
                if server_content.get("interrupted"):
                    logger.info("[BROWSER-WS] interrupted (turn=%d, speaking=%s)", _turn_count, _speaking)
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

                        # Inject last draft context when user asks about it
                        _DRAFT_RECALL_KW = ("מה כתבת", "מה ניסחת", "מה הכנת", "מה ההודעה", "מה שלחת", "תראי לי", "את ההודעה")
                        if _last_draft and any(kw in combined_input for kw in _DRAFT_RECALL_KW):
                            _recall = f'[הטיוטה האחרונה שניסחת: "{_last_draft["message"]}" ללקוח {_last_draft["lead_name"]}]'
                            await gemini_ws.send(json.dumps({"realtime_input": {"text": _recall}}))
                            logger.info("[BROWSER-WS] Injected last draft recall (%d chars)", len(_recall))

                        detected = _detect_intent(combined_input)
                        if detected:
                            logger.info("[BROWSER-WS] Intent detected: %s from '%s'", detected, combined_input[:60])

                        # ── ui_action: fires whenever user uses an open verb,
                        #    regardless of data-injection cooldown ─────────────
                        _input_lower = combined_input.lower()
                        _has_open_verb = any(v in _input_lower for v in _OPEN_VERBS)
                        _matched_verb = next((v for v in _OPEN_VERBS if v in _input_lower), None)
                        logger.info(
                            "[NAV-TRACE] input='%s' detected=%s has_open_verb=%s matched_verb=%s",
                            combined_input[:80], detected, _has_open_verb, _matched_verb,
                        )
                        if _has_open_verb:
                            _agent_ui_sent = False
                            for _aname, _aid in _agent_name_map.items():
                                if _aname in _input_lower:
                                    _sub = "settings"
                                    if any(w in _input_lower for w in ("נכסים", "assets", "חומרים")):
                                        _sub = "assets"
                                    elif any(w in _input_lower for w in ("בדיקה", "preview", "בדוק")):
                                        _sub = "voice"
                                    await browser_ws.send_json({
                                        "type": "ui_action",
                                        "action": "open_agent",
                                        "target": _aid,
                                        "tab": _sub,
                                    })
                                    logger.info("[BROWSER-WS] Sent ui_action: open_agent -> %s (tab=%s)", _aname, _sub)
                                    _agent_ui_sent = True
                                    break

                            if not _agent_ui_sent and detected:
                                ui = _INTENT_UI_ACTIONS.get(detected)
                                logger.info("[NAV-TRACE] generic lookup: detected=%s ui=%s", detected, ui)
                                if ui:
                                    await browser_ws.send_json({
                                        "type": "ui_action",
                                        **ui,
                                    })
                                    logger.info("[BROWSER-WS] Sent ui_action: %s -> %s", ui.get("action"), ui.get("target"))
                                else:
                                    logger.warning("[NAV-TRACE] No UI action mapping for intent=%s", detected)
                            elif not _agent_ui_sent:
                                logger.warning("[NAV-TRACE] open verb present but no detected intent — combined='%s'", combined_input[:80])

                        # ── Data injection: gated by cooldown to avoid spam ──
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

                            injection_text = None
                            if detected == "leads":
                                injection_text, _leads_data = await fetch_leads_detail(client_id)
                                if _leads_data:
                                    _session_leads = _leads_data
                                    logger.info("[BROWSER-WS] Session leads updated: %d leads", len(_leads_data))
                            elif detected == "calls":
                                injection_text = await fetch_calls_detail(client_id)
                            elif detected == "summary":
                                injection_text, _leads_data = await fetch_daily_summary(client_id)
                                if _leads_data:
                                    _session_leads = _leads_data
                                    logger.info("[BROWSER-WS] Session leads updated: %d leads", len(_leads_data))

                            if injection_text:
                                await gemini_ws.send(json.dumps({
                                    "realtime_input": {"text": injection_text}
                                }))
                                logger.info("[BROWSER-WS] Injected %s data (%d chars)", detected, len(injection_text))

                # Output transcript
                output_t = server_content.get("outputTranscription", {})
                if output_t.get("text"):
                    logger.info("[BROWSER-WS] transcript_out: %s", output_t["text"][:60])
                    transcript_lines.append(f"מאיה: {output_t['text']}")

                    # Accumulate output for turn-level analysis
                    if not is_preview:
                        _output_buffer.append(output_t["text"])
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

                    # ui_action is now fired from user input intent detection
                    # (see input_t handler above) — output-based detection was unreliable
                    # because it depended on Maya saying "פותחת" exactly.

                    # Snapshot output before clearing.
                    # Marker presence in output = deterministic proposal trigger.
                    # _user_approved_draft is a fallback for legacy flows without marker.
                    _pending_draft = None
                    if not is_preview and _output_buffer:
                        _full_out_check = " ".join(_output_buffer)
                        if _DRAFT_STRICT_MARKER in _full_out_check or _user_approved_draft:
                            _pending_draft = _full_out_check
                            _user_approved_draft = False

                    _input_buffer.clear()
                    _output_buffer.clear()

                    # Send turn_complete FIRST — unblocks browser audio pipeline
                    await browser_ws.send_json({"type": "turn_complete"})
                    await browser_ws.send_json({
                        "type": "state",
                        "state": "listening",
                    })

                    # ── Action proposal (after turn_complete) ─────────
                    if _pending_draft:
                        _draft_message = _extract_draft_message(_pending_draft)
                        if not _draft_message:
                            logger.info("[BROWSER-WS] No clear draft marker/quote found — skipping proposal")
                            continue

                        # Auto-fetch leads if session has none
                        if not _session_leads:
                            try:
                                _auto_text, _auto_leads = await fetch_leads_detail(client_id)
                                if _auto_leads:
                                    _session_leads = _auto_leads
                                    logger.info("[BROWSER-WS] Auto-fetched %d leads for draft matching", len(_auto_leads))
                            except Exception as _e:
                                logger.warning("[BROWSER-WS] Auto-fetch leads failed: %s", _e)

                        # Match lead from session context
                        _matched_lead = None
                        if _session_leads:
                            _search_text = (_pending_draft + " " + " ".join(transcript_lines[-10:])).lower()
                            _candidates = []
                            for _sl in _session_leads:
                                _sl_name = (_sl.get("name") or "").strip()
                                if _sl_name and _sl_name.lower() in _search_text:
                                    _candidates.append(_sl)
                            if len(_candidates) == 1:
                                _matched_lead = _candidates[0]
                            elif len(_candidates) > 1:
                                logger.warning(
                                    "[BROWSER-WS] Multiple lead matches (%d) — falling back to draft_message",
                                    len(_candidates),
                                )

                        _lead_name = (_matched_lead.get("name") or "ליד") if _matched_lead else "ליד"
                        _last_draft = {"message": _draft_message.strip(), "lead_name": _lead_name}

                        if _matched_lead:
                            await browser_ws.send_json({
                                "type": "action_proposal",
                                "action": "prepare_followup_message",
                                "status": "draft_only",
                                "agent_id": agent_id,
                                "lead_id": _matched_lead["id"],
                                "lead_name": _lead_name,
                                "channel": "whatsapp",
                                "message": _draft_message.strip(),
                            })
                            logger.info("[BROWSER-WS] Sent action_proposal: lead=%s (%s)", _lead_name, _matched_lead["id"][:8])
                        else:
                            await browser_ws.send_json({
                                "type": "action_proposal",
                                "action": "draft_message",
                                "status": "draft_only",
                                "agent_id": agent_id,
                                "lead_name": _lead_name,
                                "channel": "whatsapp",
                                "message": _draft_message.strip(),
                            })
                            logger.info("[BROWSER-WS] Sent draft_message proposal (no lead match, %d leads)", len(_session_leads))

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

"""
Maya NLU endpoint — interprets user input into structured intent.
Returns JSON only. Does NOT make decisions — only parses.
Falls back to empty intent if Gemini is unavailable.
"""

import os
import json
import logging
import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY_REST", "").strip()

NLU_PROMPT = """אתה מנתח כוונות (NLU) עבור מערכת ניהול לידים.
קלט: משפט מהמשתמש + הקשר שיחה.
פלט: JSON בלבד, ללא טקסט נוסף.

הכוונות האפשריות:
- show_all_leads: "תראי את כל הלידים", "כולם", "תמונה מלאה"
- hot_leads: "לידים חמים", "מי חם", "דחוף"
- calls_today: "כמה שיחות", "שיחות היום"
- conversion: "שיעור המרה", "אחוז המרה"
- daily_summary: "סכם את היום", "מה המצב", "מה קורה"
- win_signals: "הצלחות", "אותות סגירה", "סגירות"
- agents_status: "סוכנים", "מי פעיל"
- focus_lead: "ספר לי על X", "מה עם X", "מה המצב של X" (כשX הוא שם ליד)
- what_to_do: "מה לעשות", "מה ממליצה", "מה הצעד הבא"
- continue_topic: "מה את חושבת", "ומה עכשיו", "תמשיכי", "תפרטי", "עוד"
- continue_current_lead: "מה לעשות עם זה", "מה לעשות עכשיו" (when there's an active lead in context)
- next_lead: "מי הבא", "במי עכשיו", "אז מי", "מי עדיף"
- skip_lead: "תעזבי אותו", "דלגי", "לא שווה", "עזבי"
- send_message: "תשלחי הודעה", "מה להגיד לו", "מה לכתוב"
- confirm_action: "כן", "תשלחי", "אשר", "סבבה"
- preview_action: "תראי לי קודם", "מה תכתבי", "טיוטה"
- reject_action: "לא", "עזבי", "לא עכשיו"
- filter_action: "רק לדניאל", "רק למשה"
- analyze_call: "נתחי שיחה", "מה היה בשיחה"
- improve: "איך לשפר", "איך להגדיל", "איך להעלות", "מה אפשר לעשות יותר טוב"
- diagnose: "מה הבעיה", "למה לא עובד", "מה גרוע", "מה צריך לתקן"
- set_goal: "רוצה להגיע ל-X", "היעד שלי", "תכנון", "איך מגיעים ל-30 שיחות"
- compare: "בהשוואה לאתמול", "מה הממוצע", "האם זה נורמלי", "לעומת שבוע שעבר"

שמות לידים ידועים: משה לוי, רחל אברהם, יוסי מזרחי, דניאל כהן, שרה גולן, תמר כץ

החזר JSON בפורמט הזה בלבד:
{"intent":"...","scope":"single|all","lead_name":null,"action_mode":null,"confidence":0.95}

דוגמאות:
"כמה שיחות היום" → {"intent":"calls_today","scope":"single","lead_name":null,"action_mode":null,"confidence":0.95}
"תראי לי את כל הלידים" → {"intent":"show_all_leads","scope":"all","lead_name":null,"action_mode":null,"confidence":0.95}
"מה את חושבת לעשות עם הליד הזה" → {"intent":"continue_topic","scope":"single","lead_name":null,"action_mode":"recommendation","confidence":0.9}
"ספר לי על דניאל כהן" → {"intent":"focus_lead","scope":"single","lead_name":"דניאל כהן","action_mode":null,"confidence":0.95}
"כן תשלחי" → {"intent":"confirm_action","scope":"single","lead_name":null,"action_mode":"execute","confidence":0.95}
"תראי לי קודם" → {"intent":"preview_action","scope":"single","lead_name":null,"action_mode":"preview","confidence":0.9}
"מי הבא" → {"intent":"next_lead","scope":"single","lead_name":null,"action_mode":null,"confidence":0.95}
"מה לעשות עם משה" → {"intent":"what_to_do","scope":"single","lead_name":"משה לוי","action_mode":"recommendation","confidence":0.9}
"""


class NLURequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    context: Optional[str] = Field(default=None)  # e.g. "last_lead:משה לוי,topic:leads"


class NLUResponse(BaseModel):
    intent: str = "unknown"
    scope: str = "single"
    lead_name: Optional[str] = None
    action_mode: Optional[str] = None
    confidence: float = 0.0


_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)


def _parse_nlu_json(text_out: str, provider: str) -> Optional[NLUResponse]:
    """Parse JSON from any provider into NLUResponse."""
    try:
        parsed = json.loads(text_out)
        result = NLUResponse(
            intent=parsed.get("intent", "unknown"),
            scope=parsed.get("scope", "single"),
            lead_name=parsed.get("lead_name"),
            action_mode=parsed.get("action_mode"),
            confidence=parsed.get("confidence", 0.0),
        )
        if result.intent != "unknown":
            logger.info("[maya_nlu] %s → intent=%s conf=%.2f", provider, result.intent, result.confidence)
        return result
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("[maya_nlu] %s JSON parse failed: %s", provider, text_out[:100] if text_out else "empty")
        return None


async def _try_gemini_nlu(prompt: str) -> Optional[NLUResponse]:
    """Try Gemini (2s timeout)."""
    if not _GEMINI_API_KEY:
        return None
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={_GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 256,
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(api_url, json=payload)
        if resp.status_code != 200:
            logger.warning("[maya_nlu] Gemini error %s", resp.status_code)
            return None
        text_out = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return _parse_nlu_json(text_out, "Gemini")
    except Exception as exc:
        logger.warning("[maya_nlu] Gemini exception: %s", exc)
        return None


async def _try_openai_nlu(prompt: str) -> Optional[NLUResponse]:
    """Try OpenAI gpt-4o-mini (2s timeout)."""
    if not _OPENAI_API_KEY:
        return None
    try:
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 60,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {_OPENAI_API_KEY}", "Content-Type": "application/json"},
            )
        if resp.status_code != 200:
            logger.warning("[maya_nlu] OpenAI error %s", resp.status_code)
            return None
        text_out = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse_nlu_json(text_out, "OpenAI")
    except Exception as exc:
        logger.warning("[maya_nlu] OpenAI exception: %s", exc)
        return None


@router.post("/maya-nlu", response_model=NLUResponse)
async def maya_nlu(body: NLURequest):
    """Parse user input into structured intent. Multi-provider with fallback."""

    context_hint = f"\nהקשר שיחה: {body.context}" if body.context else ""
    prompt = NLU_PROMPT + context_hint + f"\n\nמשפט: \"{body.text}\"\nJSON:"

    # Provider 1: Gemini (fast, free)
    result = await _try_gemini_nlu(prompt)
    if result and result.intent != "unknown":
        return result

    # Provider 2: OpenAI (reliable fallback)
    result = await _try_openai_nlu(prompt)
    if result and result.intent != "unknown":
        return result

    # Provider 3: empty → client-side keyword matcher handles it
    logger.info("[maya_nlu] All providers failed, falling back to keywords")
    return NLUResponse()

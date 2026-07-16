"""
Shared helpers for voice endpoints (Gemini Twilio + browser).
Extracted from voice_gemini.py to avoid duplication.
"""

import json
import os
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


# \u2500\u2500 Customer history (new vs existing) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

async def get_customer_history(phone: str, before_iso: str) -> dict:
    """
    Look up prior call history for a caller phone, EXCLUDING the current call.

    `before_iso` must be a timestamp captured at the START of the current call;
    call_logs rows with created_at < before_iso are treated as prior interactions
    (the current call's call_logs row is written at end-of-call, so it is excluded).

    Returns {customer_status, prior_count, last_date}. Never raises \u2014 on any
    error or no history, returns the "new customer" default.
    """
    default = {"customer_status": "\u05dc\u05e7\u05d5\u05d7 \u05d7\u05d3\u05e9", "prior_count": 0, "last_date": None}
    if not phone or not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        return default
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/call_logs",
                params={
                    "phone_number": f"eq.{phone}",
                    "created_at":   f"lt.{before_iso}",
                    "select":       "created_at",
                    "order":        "created_at.desc",
                },
                headers={
                    "apikey":        _SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        print(f"[CUST-HISTORY] lookup failed for phone={phone}: {exc}")
        return default

    if not rows:
        return default

    last_iso  = rows[0].get("created_at")
    last_date = None
    if last_iso:
        try:
            last_date = datetime.fromisoformat(last_iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except Exception:
            last_date = last_iso[:10]

    return {"customer_status": "\u05dc\u05e7\u05d5\u05d7 \u05e7\u05d9\u05d9\u05dd", "prior_count": len(rows), "last_date": last_date}


# \u2500\u2500 Caller-name sanitizer (never store empty / the assistant's own name) \u2500\u2500\u2500\u2500\u2500\u2500

_NAME_UNKNOWN = "\u05dc\u05d0 \u05e0\u05de\u05e1\u05e8"
_ASSISTANT_NAME_TOKENS = {"\u05de\u05d0\u05d9\u05d4", "maya"}


def clean_caller_name(name, assistant_name: str = "") -> str:
    """
    Return a safe caller name for the lead record / email.

    - Empty / whitespace / None -> "\u05dc\u05d0 \u05e0\u05de\u05e1\u05e8" (never blank).
    - The assistant's own name  -> "\u05dc\u05d0 \u05e0\u05de\u05e1\u05e8" (never store Maya as the caller):
      matches "\u05de\u05d0\u05d9\u05d4"/"Maya", the configured assistant_name, or its first token,
      case-insensitively.
    Otherwise returns the trimmed name unchanged.
    """
    n = (name or "").strip()
    if not n:
        return _NAME_UNKNOWN
    deny = set(_ASSISTANT_NAME_TOKENS)
    a = (assistant_name or "").strip().lower()
    if a:
        deny.add(a)
        deny.add(a.split()[0])
    if n.lower() in deny:
        return _NAME_UNKNOWN
    return n

# ── Webhook delivery ─────────────────────────────────────────────────────────

async def send_voice_webhook(webhook_url: str, payload: dict) -> None:
    """POST payload to webhook URL. Never raises — errors are logged only."""
    if not webhook_url:
        print("[VOICE-WEBHOOK] No webhook URL configured — skipping")
        return
    print(f"[VOICE-WEBHOOK] POST {webhook_url}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            print(f"[VOICE-WEBHOOK] HTTP {resp.status_code}")
            resp.raise_for_status()
    except Exception as exc:
        print(f"[VOICE-WEBHOOK] delivery failed: {exc}")


# ── Lead extraction ──────────────────────────────────────────────────────────

_EXTRACT_PROMPT = """\
חלץ מהשיחה הבאה את הנתונים הבאים בפורמט JSON בלבד, ללא טקסט נוסף:

{
  "name": "שם המתקשר — רק לפי הכללים למטה, אחרת null",
  "phone_number": null,
  "topic": "נושא השיחה בקצרה",
  "notes": "פרטים חשובים (גיל, תאריך אירוע וכו')",
  "appointment_day": "יום השיעור/הפגישה שנקבע — ראשון/שני/שלישי/רביעי/חמישי/שישי/שבת, או null אם לא נקבע",
  "appointment_time": "שעת השיעור/הפגישה שנקבעה בפורמט HH:MM, או null אם לא נקבעה"
}

חוקים לחילוץ שם:
- אם המשתמש אומר "אני X", "קוראים לי X", "זה X" — החזר X.
- אם המשתמש אומר רק מילה אחת או שתיים שנשמעות כמו שם (למשל "לידור" או "לידור כהן") — זה השם. אם יש ספק או שזה יכול להיות משהו אחר — החזר null.
- אל תחלץ שם אם המילה יכולה להיות משהו אחר (למשל "כן", "אולי", "רוצה").
- phone_number תמיד null.
- אל תנחש. אל תמציא. אם אין — החזר null.

שיחה:
{transcript}
"""


async def extract_lead_from_transcript(transcript: str, caller_phone: str) -> dict:
    """
    Post-call extraction via OpenAI gpt-4o-mini.
    Returns a dict with keys: name, phone_number, topic, notes (all may be None).
    Never raises — falls back to phone-only on any error.
    """
    if not _OPENAI_API_KEY:
        return {"phone_number": caller_phone}
    prompt = _EXTRACT_PROMPT.replace("{transcript}", transcript)
    body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 256,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=body,
                headers={
                    "Authorization": f"Bearer {_OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"]
            raw_text = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            result = json.loads(raw_text)
            if not result.get("phone_number"):
                result["phone_number"] = caller_phone
            return result
    except Exception as exc:
        print(f"[VOICE-EXTRACT] Extraction failed: {exc}")
        return {"phone_number": caller_phone}

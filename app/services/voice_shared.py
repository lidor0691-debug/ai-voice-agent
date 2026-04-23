"""
Shared helpers for voice endpoints (Gemini Twilio + browser).
Extracted from voice_gemini.py to avoid duplication.
"""

import json
import os
import logging

import httpx

logger = logging.getLogger(__name__)

_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)

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

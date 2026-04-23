"""
Maya Insight endpoint — improves phrasing of responses.
Does NOT make decisions. Only rephrases what the local engine decided.
"""

import os
import logging
import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY_REST", "").strip()

INSIGHT_PROMPT = """את Maya, מנהלת מכירות בכירה. מדברת ישירות לבעל העסק.

קיבלת תשובה טכנית מהמערכת. שכתבי אותה כך שתישמע כמו מנהלת אמיתית בחדר ישיבות.

כללים:
- שמרי על אותו תוכן ואותם שמות. אל תוסיפי מידע חדש.
- ישר לעניין, בלי שלום/היי.
- חדה, ישירה, מקצועית.
- דברי לבעל העסק: "תחזור אליו", "תשלח לו".
- 2-3 משפטים מקסימום.
- אם התשובה כבר טובה — החזירי אותה כמו שהיא.
"""


class InsightRequest(BaseModel):
    base_response: str = Field(..., min_length=1, max_length=1000)
    lead_name: Optional[str] = None
    context: Optional[str] = None  # e.g. "follow-up on hot lead"


_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)


async def _try_gemini_insight(prompt: str) -> Optional[str]:
    if not _GEMINI_API_KEY:
        return None
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={_GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 200, "temperature": 0.3},
        }
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.post(api_url, json=payload)
        if resp.status_code != 200:
            logger.warning("[maya_insight] Gemini error %s", resp.status_code)
            return None
        text = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if text and text.strip():
            logger.info("[maya_insight] Gemini OK")
            return text.strip()
        return None
    except Exception as exc:
        logger.warning("[maya_insight] Gemini exception: %s", exc)
        return None


async def _try_openai_insight(prompt: str) -> Optional[str]:
    if not _OPENAI_API_KEY:
        return None
    try:
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.3,
        }
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {_OPENAI_API_KEY}", "Content-Type": "application/json"},
            )
        if resp.status_code != 200:
            logger.warning("[maya_insight] OpenAI error %s", resp.status_code)
            return None
        text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if text and text.strip():
            logger.info("[maya_insight] OpenAI OK")
            return text.strip()
        return None
    except Exception as exc:
        logger.warning("[maya_insight] OpenAI exception: %s", exc)
        return None


@router.post("/maya-insight")
async def maya_insight(body: InsightRequest):
    """Rephrase a response. Multi-provider fallback. Returns original if all fail."""

    extra = ""
    if body.lead_name:
        extra += f"\nליד: {body.lead_name}"
    if body.context:
        extra += f"\nהקשר: {body.context}"
    prompt = f"{INSIGHT_PROMPT}{extra}\n\nתשובה מקורית:\n{body.base_response}\n\nגרסה משופרת:"

    # Provider 1: Gemini
    improved = await _try_gemini_insight(prompt)
    if improved:
        return {"improved": improved, "provider": "gemini"}

    # Provider 2: OpenAI
    improved = await _try_openai_insight(prompt)
    if improved:
        return {"improved": improved, "provider": "openai"}

    # Fallback: return base response as-is
    logger.info("[maya_insight] All providers failed, using base response")
    return {"improved": body.base_response, "provider": "none"}

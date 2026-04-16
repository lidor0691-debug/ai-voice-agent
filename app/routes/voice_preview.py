import os
import logging
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)

_TTS_URL = "https://api.openai.com/v1/audio/speech"

_DEMO_SENTENCES = {
    "he": "שלום, אני מאיה. נעים מאוד, איך אפשר לעזור לך היום?",
    "en": "Hi, I'm Maya. Nice to meet you. How can I help you today?",
}

_VALID_VOICES = {"shimmer", "coral", "sage", "alloy", "echo", "verse", "ballad", "ash", "nova", "onyx"}


class VoicePreviewRequest(BaseModel):
    voice_id: str = Field(default="shimmer")
    speaking_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    language: Optional[str] = Field(default="he")


@router.post("/voice-preview")
async def voice_preview(body: VoicePreviewRequest):
    voice = body.voice_id if body.voice_id in _VALID_VOICES else "shimmer"
    lang = body.language if body.language in _DEMO_SENTENCES else "he"
    text = _DEMO_SENTENCES[lang]
    speed = round(max(0.5, min(2.0, body.speaking_rate)), 2)

    payload = {
        "model": "tts-1",
        "input": text,
        "voice": voice,
        "speed": speed,
        "response_format": "mp3",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _TTS_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {_OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code != 200:
            logger.error("[voice_preview] OpenAI TTS error %s: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=502, detail="TTS generation failed")

        return Response(
            content=resp.content,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[voice_preview] Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal error generating preview")

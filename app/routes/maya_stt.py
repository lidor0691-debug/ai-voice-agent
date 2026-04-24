"""
Maya STT endpoint — speech-to-text via OpenAI Whisper API.
Accepts audio blob, returns transcribed Hebrew text.
"""

import os
import logging
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)


@router.post("/maya-stt")
async def maya_stt(audio: UploadFile = File(...)):
    """Transcribe audio to Hebrew text using OpenAI Whisper."""

    if not _OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI not configured")

    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio too short")

    # Determine file extension from content type
    ext = "webm"
    ct = audio.content_type or ""
    if "wav" in ct:
        ext = "wav"
    elif "mp4" in ct or "m4a" in ct:
        ext = "m4a"
    elif "ogg" in ct:
        ext = "ogg"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {_OPENAI_API_KEY}"},
                files={"file": (f"audio.{ext}", audio_bytes, ct or f"audio/{ext}")},
                data={
                    "model": "whisper-1",
                    "language": "he",
                    "response_format": "json",
                },
            )

        if resp.status_code != 200:
            logger.warning("[maya_stt] Whisper error %s: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=502, detail="Transcription failed")

        text = resp.json().get("text", "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="Empty transcription")

        logger.info("[maya_stt] Transcribed: %s", text[:80])
        return {"text": text}

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[maya_stt] Error: %s", exc)
        raise HTTPException(status_code=500, detail="Transcription error")

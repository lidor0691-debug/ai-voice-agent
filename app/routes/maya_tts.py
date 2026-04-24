"""
Maya TTS endpoint — text-to-speech for the dashboard.
Uses Gemini Live API (text input → audio output) for natural Hebrew voice.
Falls back to OpenAI TTS if Gemini fails.
"""

import os
import json
import base64
import struct
import logging
import asyncio
import websockets
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
_GEMINI_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
_GEMINI_WS_URL = (
    f"wss://generativelanguage.googleapis.com/ws/"
    f"google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    f"?key={_GEMINI_API_KEY}"
)

_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
)

# Gemini prebuilt voices that sound good in Hebrew
_GEMINI_VOICES = {"Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Schedar"}
_DEFAULT_VOICE = "Zephyr"


class MayaTTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: Optional[str] = Field(default=None)


def _pcm24k_to_wav(pcm_bytes: bytes) -> bytes:
    """Convert raw PCM16 LE 24kHz mono to a WAV file in memory."""
    sample_rate = 24000
    num_channels = 1
    bits_per_sample = 16
    data_size = len(pcm_bytes)
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8

    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,
        1,  # PCM
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size,
    )
    return header + pcm_bytes


async def _gemini_tts(text: str, voice: str) -> Optional[bytes]:
    """Use Gemini TTS model (REST) with Live API fallback."""
    if not _GEMINI_API_KEY:
        return None

    # Try REST TTS model first
    tts_audio = await _gemini_tts_rest(text, voice)
    if tts_audio:
        return tts_audio

    # Fallback to Live API WebSocket
    return await _gemini_tts_live(text, voice)


async def _gemini_tts_rest(text: str, voice: str) -> Optional[bytes]:
    """Gemini TTS REST API — pure text-to-speech."""
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={_GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
            },
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(api_url, json=payload)
        if resp.status_code != 200:
            print(f"[maya_tts] REST TTS error {resp.status_code}", flush=True)
            return None
        data = resp.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            ib = part.get("inlineData", {})
            if "audio" in ib.get("mimeType", "") and ib.get("data"):
                return _pcm24k_to_wav(base64.b64decode(ib["data"]))
        return None
    except Exception as exc:
        print(f"[maya_tts] REST TTS exception: {exc}", flush=True)
        return None


async def _gemini_tts_live(text: str, voice: str) -> Optional[bytes]:
    """Fallback: Gemini Live WebSocket for TTS."""
    try:
        async with websockets.connect(
            _GEMINI_WS_URL, additional_headers={"Content-Type": "application/json"},
            close_timeout=5, open_timeout=10,
        ) as ws:
            setup = {
                "setup": {
                    "model": f"models/{_GEMINI_MODEL}",
                    "generation_config": {
                        "response_modalities": ["AUDIO"],
                        "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voice}}},
                    },
                    "system_instruction": {
                        "parts": [{"text": "את Maya, מנהלת מכירות בכירה. מדברת ישירות לבעל העסק. חדה, ישירה, מקצועית. בעלת סמכות. לא חמודה ולא רובוטית — כמו מנהלת אמיתית בחדר ישיבות. תעבירי את המסר שהמשתמש שולח בסגנון שלך — טבעי, ביטחוני, ישר לעניין. אל תוסיפי מידע חדש שלא קיים בטקסט."}]
                    },
                }
            }
            await ws.send(json.dumps(setup))
            resp = await asyncio.wait_for(ws.recv(), timeout=10)

            await ws.send(json.dumps({"realtime_input": {"text": text}}))

            audio_chunks = []
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    data = json.loads(raw)
                except asyncio.TimeoutError:
                    break
                sc = data.get("serverContent", {})
                for part in sc.get("modelTurn", {}).get("parts", []):
                    ib = part.get("inlineData", {})
                    if ib.get("mimeType", "").startswith("audio/") and ib.get("data"):
                        audio_chunks.append(base64.b64decode(ib["data"]))
                if sc.get("turnComplete"):
                    break

            if not audio_chunks:
                return None
            return _pcm24k_to_wav(b"".join(audio_chunks))
    except Exception as exc:
        print(f"[maya_tts] Live TTS exception: {exc}", flush=True)
        return None

    except Exception as exc:
        logger.exception("[maya_tts] Gemini TTS error: %s", exc)
        return None


async def _openai_tts_fallback(text: str) -> Optional[bytes]:
    """Fallback to OpenAI TTS (mp3)."""
    if not _OPENAI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                json={"model": "tts-1", "input": text, "voice": "shimmer", "speed": 1.0, "response_format": "mp3"},
                headers={"Authorization": f"Bearer {_OPENAI_API_KEY}", "Content-Type": "application/json"},
            )
        if resp.status_code == 200:
            return resp.content
    except Exception as exc:
        logger.exception("[maya_tts] OpenAI fallback error: %s", exc)
    return None


class MayaChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    context: Optional[str] = Field(default=None)


@router.post("/maya-chat")
async def maya_chat(body: MayaChatRequest):
    """Free-form question to Maya via Gemini text API. Returns short Hebrew answer."""
    if not _GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Gemini not configured")

    context = body.context or "את Maya, מנהלת מכירות בכירה. מנהלת שיחה שוטפת עם בעל העסק. תני תובנות, הצעות, ניתוחים. תמיד תסיימי עם שאלה או הצעה לפעולה הבאה. 3-4 משפטים. ישירה אבל עוזרת."
    try:
        # Use Gemini REST API for text
        _chat_key = os.getenv("GEMINI_API_KEY_REST", "") or _GEMINI_API_KEY
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={_chat_key}"
        payload = {
            "contents": [{"parts": [{"text": body.text}]}],
            "systemInstruction": {"parts": [{"text": context}]},
            "generationConfig": {"maxOutputTokens": 300, "temperature": 0.7},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(api_url, json=payload)
        if resp.status_code != 200:
            logger.warning("[maya_chat] Gemini API error %s: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=502, detail="Gemini chat failed")

        data = resp.json()
        answer = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not answer:
            raise HTTPException(status_code=502, detail="Empty response")
        return {"answer": answer.strip()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[maya_chat] Error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/maya-tts")
async def maya_tts(body: MayaTTSRequest):
    """Text-to-speech for Maya dashboard. Gemini first, OpenAI fallback."""
    voice = body.voice if body.voice in _GEMINI_VOICES else _DEFAULT_VOICE

    # Try Gemini TTS model (pure text-to-speech)
    print(f"[maya_tts] Attempting Gemini TTS, text={body.text[:30]}...", flush=True)
    audio_data = await _gemini_tts(body.text, voice)
    if audio_data:
        # Detect format from header bytes
        is_wav = audio_data[:4] == b'RIFF'
        mime = "audio/wav" if is_wav else "audio/mpeg"
        print(f"[maya_tts] Gemini OK, {len(audio_data)} bytes, {mime}", flush=True)
        return Response(content=audio_data, media_type=mime, headers={"Cache-Control": "no-store"})

    # Fallback to OpenAI
    print(f"[maya_tts] Gemini failed, trying OpenAI fallback, key={_OPENAI_API_KEY[:10]}...", flush=True)
    mp3_data = await _openai_tts_fallback(body.text)
    if mp3_data:
        print(f"[maya_tts] OpenAI OK, {len(mp3_data)} bytes", flush=True)
        return Response(content=mp3_data, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

    print("[maya_tts] Both Gemini and OpenAI failed!", flush=True)
    raise HTTPException(status_code=502, detail="TTS generation failed")

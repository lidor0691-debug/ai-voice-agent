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
from datetime import datetime

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.services.agent_config import fetch_agent_config_by_id
from app.services.voice_shared import extract_lead_from_transcript, send_voice_webhook
from app.services.lead_capture import save_lead

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


# ── WebSocket endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws/voice-browser")
async def stream_browser(browser_ws: WebSocket, agent_id: str = Query(default="")):
    """
    Proxy WebSocket: Browser <-> Gemini Live.
    Accepts PCM16 16kHz from browser, forwards to Gemini, returns PCM16 24kHz.
    """
    await browser_ws.accept()
    logger.info("[BROWSER-WS] Connection accepted - agent_id=%s", agent_id)

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

    # ── Build system instruction ─────────────────────────────────────────
    system_instruction = agent_cfg.get("prompt_override", "")
    if first_message and system_instruction:
        system_instruction = (
            f'פתחי את השיחה תמיד עם המשפט הבא בדיוק:\n'
            f'"{first_message}"\n\n'
            f'{system_instruction}'
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
    if first_message:
        await gemini_ws.send(json.dumps({"realtime_input": {"text": "שלום"}}))
        logger.info("[BROWSER-WS] Opening trigger sent")

    await browser_ws.send_json({"type": "ready"})
    await browser_ws.send_json({"type": "state", "state": "listening"})
    logger.info("[BROWSER-WS] Session ready - streaming audio")

    # ── Shared state ─────────────────────────────────────────────────────
    transcript_lines: list[str] = []
    _speaking = False
    _shutdown = asyncio.Event()  # signals all loops to exit

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
        nonlocal _speaking

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
                    transcript_lines.append(f"לקוח: {input_t['text']}")
                    await browser_ws.send_json({
                        "type": "transcript_in",
                        "text": input_t["text"],
                    })

                # Output transcript
                output_t = server_content.get("outputTranscription", {})
                if output_t.get("text"):
                    transcript_lines.append(f"מאיה: {output_t['text']}")
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

        # ── Lead extraction (only for meaningful transcripts) ────────────
        if _is_meaningful_transcript(transcript_lines):
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

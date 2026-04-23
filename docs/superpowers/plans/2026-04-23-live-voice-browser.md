# Live Voice Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Real-time voice conversation with Maya from the dashboard browser via Gemini Live proxy WebSocket.

**Architecture:** Browser captures PCM16@16kHz via AudioWorklet → FastAPI WebSocket proxy → Gemini Live WebSocket. Audio response streamed back as PCM16@24kHz. Agent config loaded by agent_id from Supabase. Lead extraction on disconnect.

**Tech Stack:** FastAPI WebSocket, websockets library, Gemini Live API, AudioWorklet, Web Audio API, React/TypeScript

**Spec:** `docs/superpowers/specs/2026-04-23-live-voice-browser-design.md`

---

### Task 1: Add `fetch_agent_config_by_id()` to agent_config.py

**Files:**
- Modify: `app/services/agent_config.py` (add new function after line 472)

- [ ] **Step 1: Add the function**

Add this function at the end of `app/services/agent_config.py`:

```python
async def fetch_agent_config_by_id(agent_id: str) -> dict:
    """
    Fetch an agent config by ID (for browser voice sessions).
    Returns same dict shape as fetch_supabase_agent_config().
    On failure returns _AGENT_SAFE_DEFAULT.
    """
    if not _is_configured() or not agent_id:
        return _AGENT_SAFE_DEFAULT

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/agents_config",
                params={"id": f"eq.{agent_id}", "is_active": "eq.true", "limit": "1"},
                headers=_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                logger.warning("No active agent found for id=%s", agent_id)
                return _AGENT_SAFE_DEFAULT
            row = rows[0]
    except Exception as exc:
        logger.error("fetch_agent_config_by_id failed for %s: %s", agent_id, exc)
        return _AGENT_SAFE_DEFAULT

    try:
        knowledge_items = await _fetch_knowledge_items(row["id"])
    except Exception:
        knowledge_items = []

    prompt_template = build_supabase_system_prompt(row, knowledge_items, caller_phone="browser")

    agent_name = (row.get("agent_name") or "Maya").strip()
    first_message = (row.get("first_message") or "").strip()

    lead_delivery_method = (row.get("lead_delivery_method") or "").strip()
    lead_delivery_target = (row.get("lead_delivery_target") or "").strip()
    legacy_webhook = (row.get("post_call_webhook_url") or "").strip()
    if not lead_delivery_target and legacy_webhook:
        lead_delivery_method = "webhook"
        lead_delivery_target = legacy_webhook

    return {
        "agent_id":              row.get("id", ""),
        "client_id":             row.get("client_id", ""),
        "business_name":         (row.get("business_name") or agent_name).strip(),
        "client_name":           agent_name,
        "assistant_name":        agent_name,
        "voice":                 (row.get("voice") or "").strip(),
        "temperature":           float(row.get("temperature") or 0.7),
        "prompt_override":       prompt_template,
        "first_message":         first_message,
        "lead_delivery_method":  lead_delivery_method,
        "lead_delivery_target":  lead_delivery_target,
        "webhook_url":           lead_delivery_target if lead_delivery_method == "webhook" else "",
        "_from_supabase":        True,
        "fallback_used":         False,
    }
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd c:/Users/lidor/maya-ai && python -c "from app.services.agent_config import fetch_agent_config_by_id; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/agent_config.py
git commit -m "feat: add fetch_agent_config_by_id for browser voice sessions"
```

---

### Task 2: Extract shared helpers from voice_gemini.py

**Files:**
- Create: `app/services/voice_shared.py`
- Modify: `app/routes/voice_gemini.py` (change imports to use shared module)

- [ ] **Step 1: Create shared module**

Create `app/services/voice_shared.py` with the extract and webhook functions copied from `voice_gemini.py`:

```python
"""
Shared helpers for voice endpoints (Gemini Twilio + browser).
Extracted from voice_gemini.py to avoid duplication.
"""

import os
import json
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


async def send_voice_webhook(webhook_url: str, payload: dict) -> None:
    """POST lead data to the agent's configured webhook URL."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(webhook_url, json=payload)
            logger.info("[VOICE-WEBHOOK] POST %s → %s", webhook_url, resp.status_code)
    except Exception as exc:
        logger.warning("[VOICE-WEBHOOK] Failed: %s", exc)


async def extract_lead_from_transcript(transcript: str, caller_phone: str) -> dict:
    """
    Use OpenAI gpt-4o-mini to extract structured lead fields from a voice transcript.
    Returns dict with keys: name, phone_number, topic, notes, appointment_day, appointment_time.
    """
    if not _OPENAI_API_KEY or not transcript.strip():
        return {}

    extraction_prompt = f"""אתה מנתח שיחות מכירה. חלץ את הפרטים הבאים מהשיחה:

שיחה:
{transcript}

מספר הטלפון של הלקוח: {caller_phone}

החזר JSON בלבד עם השדות הבאים (השאר ריק אם לא נמצא):
{{"name": "שם הלקוח", "phone_number": "מספר טלפון", "topic": "נושא השיחה", "notes": "פרטים חשובים", "appointment_day": "יום בשבוע", "appointment_time": "שעה בפורמט HH:MM"}}"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {_OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": extraction_prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            )
            if resp.status_code != 200:
                logger.warning("[VOICE-EXTRACT] OpenAI error %s", resp.status_code)
                return {}
            text = resp.json()["choices"][0]["message"]["content"]
            return json.loads(text)
    except Exception as exc:
        logger.warning("[VOICE-EXTRACT] Extraction failed: %s", exc)
        return {}
```

- [ ] **Step 2: Update voice_gemini.py imports**

In `app/routes/voice_gemini.py`, replace the private `_extract_lead_from_transcript` and `_send_gemini_webhook` functions with imports from the shared module. Find the two function definitions (lines 63-104 for webhook, lines 106-155 approx for extract) and replace them with:

```python
from app.services.voice_shared import extract_lead_from_transcript as _extract_lead_from_transcript
from app.services.voice_shared import send_voice_webhook as _send_gemini_webhook
```

Remove the original function bodies but keep the imports and all other code unchanged.

- [ ] **Step 3: Verify existing Gemini voice still works**

Run: `cd c:/Users/lidor/maya-ai && python -c "from app.routes.voice_gemini import router; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/services/voice_shared.py app/routes/voice_gemini.py
git commit -m "refactor: extract voice shared helpers for reuse in browser voice"
```

---

### Task 3: Create voice_browser.py WebSocket endpoint

**Files:**
- Create: `app/routes/voice_browser.py`

- [ ] **Step 1: Create the endpoint file**

Create `app/routes/voice_browser.py`:

```python
"""
Browser voice endpoint — proxies browser audio to Gemini Live via WebSocket.

Audio flow:
  Browser (PCM16 16kHz) → FastAPI WS → Gemini Live (PCM16 16kHz)
  Gemini Live (PCM16 24kHz) → FastAPI WS → Browser (PCM16 24kHz)

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

_GEMINI_VALID_VOICES = {"Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Schedar"}

# Minimum transcript requirements for lead extraction
_MIN_TURNS = 2
_MIN_TRANSCRIPT_LEN = 50
_GREETING_ONLY = {"שלום", "היי", "ביי", "להתראות", "בוקר טוב"}


def _is_meaningful_transcript(lines: list[str]) -> bool:
    """Check if transcript is meaningful enough to extract a lead."""
    user_turns = [l for l in lines if l.startswith("לקוח:")]
    if len(user_turns) < _MIN_TURNS:
        return False
    combined = " ".join(lines)
    if len(combined) < _MIN_TRANSCRIPT_LEN:
        return False
    # Check if it's only greetings
    user_words = set()
    for turn in user_turns:
        text = turn.replace("לקוח:", "").strip()
        user_words.update(text.split())
    if user_words.issubset(_GREETING_ONLY):
        return False
    return True


@router.websocket("/ws/voice-browser")
async def stream_browser(browser_ws: WebSocket, agent_id: str = Query(default="")):
    """
    Proxy WebSocket: Browser ↔ Gemini Live.
    Accepts PCM16 16kHz from browser, forwards to Gemini, returns PCM16 24kHz.
    """
    await browser_ws.accept()
    logger.info("[BROWSER-WS] Connection accepted — agent_id=%s", agent_id)

    if not _GEMINI_API_KEY:
        await browser_ws.send_json({"type": "error", "message": "Gemini not configured"})
        await browser_ws.close()
        return

    if not agent_id:
        await browser_ws.send_json({"type": "error", "message": "agent_id is required"})
        await browser_ws.close()
        return

    # ── Load agent config ────────────────────────────────────────────────────
    agent_cfg = await fetch_agent_config_by_id(agent_id)
    if agent_cfg.get("fallback_used"):
        logger.warning("[BROWSER-WS] No agent found for id=%s — using fallback", agent_id)

    client_name = agent_cfg.get("client_name", "")
    client_id = agent_cfg.get("client_id") or None
    webhook_url = agent_cfg.get("webhook_url", "")
    first_message = (agent_cfg.get("first_message") or "").strip()

    # ── Build system instruction ─────────────────────────────────────────────
    system_instruction = agent_cfg.get("prompt_override", "")
    if first_message and system_instruction:
        system_instruction = f'פתחי את השיחה תמיד עם המשפט הבא בדיוק:\n"{first_message}"\n\n{system_instruction}'

    # ── Resolve voice ────────────────────────────────────────────────────────
    raw_voice = (agent_cfg.get("voice") or "").strip()
    gemini_voice = raw_voice if raw_voice in _GEMINI_VALID_VOICES else "Zephyr"
    logger.info("[BROWSER-WS] Agent='%s' voice=%s", client_name, gemini_voice)

    # ── Connect to Gemini Live ───────────────────────────────────────────────
    gemini_url = _GEMINI_WS_URL.format(api_key=_GEMINI_API_KEY)
    try:
        gemini_ws = await websockets.connect(gemini_url, ping_interval=None)
    except Exception as e:
        logger.error("[BROWSER-WS] Gemini connect failed: %s", e)
        await browser_ws.send_json({"type": "error", "message": "Cannot connect to voice service"})
        await browser_ws.close()
        return

    # ── Send setup message ───────────────────────────────────────────────────
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

    # ── Trigger opening greeting ─────────────────────────────────────────────
    if first_message:
        await gemini_ws.send(json.dumps({"realtime_input": {"text": "שלום"}}))
        logger.info("[BROWSER-WS] Opening trigger sent")

    await browser_ws.send_json({"type": "ready"})
    await browser_ws.send_json({"type": "state", "state": "listening"})

    # ── Shared state ─────────────────────────────────────────────────────────
    transcript_lines: list[str] = []
    _speaking = False

    # ── Browser → Gemini loop ────────────────────────────────────────────────
    async def browser_to_gemini():
        try:
            while True:
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
                    pass  # heartbeat response — no action needed

                elif msg.get("type") == "end":
                    logger.info("[BROWSER-WS] Client sent end — closing")
                    await gemini_ws.close()
                    break

        except WebSocketDisconnect:
            logger.info("[BROWSER-WS] Browser disconnected")
            try:
                await gemini_ws.close()
            except Exception:
                pass
        except Exception as e:
            logger.warning("[BROWSER-WS] Browser receiver error: %s", e)
            try:
                await gemini_ws.close()
            except Exception:
                pass

    # ── Gemini → Browser loop ────────────────────────────────────────────────
    async def gemini_to_browser():
        nonlocal _speaking

        try:
            async for raw in gemini_ws:
                msg = json.loads(raw)
                server_content = msg.get("serverContent", {})

                # ── Interrupted (barge-in) ───────────────────────────────
                if server_content.get("interrupted"):
                    _speaking = False
                    await browser_ws.send_json({"type": "interrupted"})
                    await browser_ws.send_json({"type": "state", "state": "listening"})
                    continue

                # ── Input transcript ─────────────────────────────────────
                input_t = server_content.get("inputTranscription", {})
                if input_t.get("text"):
                    transcript_lines.append(f"לקוח: {input_t['text']}")
                    await browser_ws.send_json({"type": "transcript_in", "text": input_t["text"]})

                # ── Output transcript ────────────────────────────────────
                output_t = server_content.get("outputTranscription", {})
                if output_t.get("text"):
                    transcript_lines.append(f"מאיה: {output_t['text']}")
                    await browser_ws.send_json({"type": "transcript_out", "text": output_t["text"]})

                # ── Audio chunks ─────────────────────────────────────────
                model_turn = server_content.get("modelTurn", {})
                parts = model_turn.get("parts", [])
                for part in parts:
                    inline_data = part.get("inlineData", {})
                    data = inline_data.get("data", "")
                    mime = inline_data.get("mimeType", "")
                    if data and "audio" in mime:
                        if not _speaking:
                            _speaking = True
                            await browser_ws.send_json({"type": "state", "state": "speaking"})
                        await browser_ws.send_json({"type": "audio", "data": data})

                # ── Turn complete ────────────────────────────────────────
                if server_content.get("turnComplete"):
                    _speaking = False
                    await browser_ws.send_json({"type": "turn_complete"})
                    await browser_ws.send_json({"type": "state", "state": "listening"})

        except Exception as e:
            logger.warning("[BROWSER-WS] Gemini receiver error: %s", e)
            try:
                await browser_ws.send_json({"type": "error", "message": "Voice connection lost"})
            except Exception:
                pass

    # ── Heartbeat loop ───────────────────────────────────────────────────────
    async def heartbeat_loop():
        try:
            while True:
                await asyncio.sleep(15)
                await browser_ws.send_json({"type": "ping"})
        except Exception:
            pass

    # ── Run all loops ────────────────────────────────────────────────────────
    try:
        await asyncio.gather(
            browser_to_gemini(),
            gemini_to_browser(),
            heartbeat_loop(),
        )
    finally:
        logger.info("[BROWSER-WS] Session ended — cleanup")

        # ── Lead extraction (only for meaningful transcripts) ────────────
        if _is_meaningful_transcript(transcript_lines):
            transcript_text = "\n".join(transcript_lines)
            logger.info("[BROWSER-WS] Extracting lead from %d transcript lines", len(transcript_lines))
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
                logger.info("[BROWSER-WS] Lead saved — name=%s", extracted.get("name"))

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
            logger.info("[BROWSER-WS] Transcript too short/trivial — skipping lead extraction")

        # Close connections
        try:
            await gemini_ws.close()
        except Exception:
            pass
        try:
            await browser_ws.close()
        except Exception:
            pass
```

- [ ] **Step 2: Verify import**

Run: `cd c:/Users/lidor/maya-ai && python -c "from app.routes.voice_browser import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/routes/voice_browser.py
git commit -m "feat: add browser voice WebSocket proxy endpoint"
```

---

### Task 4: Register route in main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add import and registration**

In `main.py`, after line 67 (`from app.routes.maya_stt import router as maya_stt_router`), add:

```python
from app.routes.voice_browser import router as voice_browser_router
```

After line 93 (`app.include_router(maya_stt_router)`), add:

```python
app.include_router(voice_browser_router)
```

- [ ] **Step 2: Verify server starts**

Run: `cd c:/Users/lidor/maya-ai && python -c "from main import app; print('Routes:', [r.path for r in app.routes if hasattr(r, 'path') and 'voice-browser' in r.path])"`
Expected: Shows route with `voice-browser`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: register browser voice WebSocket route"
```

---

### Task 5: Create AudioWorklet for PCM16 capture

**Files:**
- Create: `dashboard/public/pcm-worklet.js`

- [ ] **Step 1: Create the worklet**

Create `dashboard/public/pcm-worklet.js`:

```javascript
/**
 * PCM16 AudioWorklet processor.
 * Captures raw PCM16 mono audio at the AudioContext's sample rate (16kHz).
 * Buffers ~100ms of samples before posting to main thread.
 */
class PCM16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    this._bufferSize = 1600; // ~100ms at 16kHz
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const samples = input[0]; // mono channel

    // Append to buffer
    const newBuf = new Float32Array(this._buffer.length + samples.length);
    newBuf.set(this._buffer);
    newBuf.set(samples, this._buffer.length);
    this._buffer = newBuf;

    // Flush when buffer is large enough
    while (this._buffer.length >= this._bufferSize) {
      const chunk = this._buffer.slice(0, this._bufferSize);
      this._buffer = this._buffer.slice(this._bufferSize);

      // Convert Float32 [-1,1] to Int16
      const pcm16 = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }

      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }

    return true;
  }
}

registerProcessor("pcm16-processor", PCM16Processor);
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/public/pcm-worklet.js
git commit -m "feat: add PCM16 AudioWorklet for browser voice capture"
```

---

### Task 6: Create LiveVoicePanel React component

**Files:**
- Create: `dashboard/components/agents/live-voice-panel.tsx`

- [ ] **Step 1: Create the component**

Create `dashboard/components/agents/live-voice-panel.tsx`:

```tsx
"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Mic, PhoneOff, ChevronDown, ChevronUp } from "lucide-react";

type VoiceState = "disconnected" | "connecting" | "listening" | "thinking" | "speaking";

interface TranscriptEntry {
  role: "user" | "maya";
  text: string;
}

interface Props {
  agentId: string;
}

const STATE_LABELS: Record<VoiceState, string> = {
  disconnected: "התחל שיחה עם Maya",
  connecting: "מתחברת...",
  listening: "מקשיבה...",
  thinking: "חושבת...",
  speaking: "מדברת...",
};

const STATE_COLORS: Record<VoiceState, string> = {
  disconnected: "bg-gray-500",
  connecting: "bg-yellow-500 animate-pulse",
  listening: "bg-green-500 animate-pulse",
  thinking: "bg-brand-400 animate-pulse",
  speaking: "bg-purple-500 animate-pulse",
};

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

export function LiveVoicePanel({ agentId }: Props) {
  const [state, setState] = useState<VoiceState>("disconnected");
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [showTranscript, setShowTranscript] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const nextPlayTimeRef = useRef(0);
  const scheduledSourcesRef = useRef<AudioBufferSourceNode[]>([]);

  // ── Cleanup ─────────────────────────────────────────────────────────────
  const cleanup = useCallback(() => {
    // Stop mic
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    // Stop playback
    scheduledSourcesRef.current.forEach((s) => {
      try { s.stop(); } catch {}
    });
    scheduledSourcesRef.current = [];
    if (playbackCtxRef.current) {
      playbackCtxRef.current.close().catch(() => {});
      playbackCtxRef.current = null;
    }
    nextPlayTimeRef.current = 0;
    // Close WebSocket
    if (wsRef.current) {
      try { wsRef.current.close(); } catch {}
      wsRef.current = null;
    }
    setState("disconnected");
  }, []);

  // Cleanup on unmount
  useEffect(() => () => cleanup(), [cleanup]);

  // ── Clear scheduled audio (for barge-in) ────────────────────────────────
  const clearPlayback = useCallback(() => {
    scheduledSourcesRef.current.forEach((s) => {
      try { s.stop(); } catch {}
    });
    scheduledSourcesRef.current = [];
    nextPlayTimeRef.current = 0;
  }, []);

  // ── Play PCM16 24kHz audio chunk ────────────────────────────────────────
  const playAudioChunk = useCallback((base64Data: string) => {
    if (!playbackCtxRef.current) return;
    const ctx = playbackCtxRef.current;
    const pcmBuffer = base64ToArrayBuffer(base64Data);
    const int16 = new Int16Array(pcmBuffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }

    const audioBuffer = ctx.createBuffer(1, float32.length, 24000);
    audioBuffer.copyToChannel(float32, 0);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    // Jitter buffer: schedule 80ms ahead
    const JITTER_MS = 0.08;
    const now = ctx.currentTime + JITTER_MS;
    const startTime = Math.max(now, nextPlayTimeRef.current);
    nextPlayTimeRef.current = startTime + audioBuffer.duration;

    source.start(startTime);
    scheduledSourcesRef.current.push(source);
    source.onended = () => {
      scheduledSourcesRef.current = scheduledSourcesRef.current.filter((s) => s !== source);
    };
  }, []);

  // ── Start call ──────────────────────────────────────────────────────────
  const startCall = useCallback(async () => {
    setState("connecting");
    setTranscript([]);

    try {
      // Build WebSocket URL from API_BASE_URL
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_BASE_URL || "http://localhost:8000";
      const wsUrl = apiBase.replace(/^http/, "ws") + `/ws/voice-browser?agent_id=${agentId}`;

      // Create playback context
      playbackCtxRef.current = new AudioContext({ sampleRate: 24000 });

      // Request microphone
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;

      // Create audio context at 16kHz for capture
      const audioCtx = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = audioCtx;

      // Load AudioWorklet
      await audioCtx.audioWorklet.addModule("/pcm-worklet.js");
      const workletNode = new AudioWorkletNode(audioCtx, "pcm16-processor");
      workletNodeRef.current = workletNode;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(workletNode);

      // Connect WebSocket
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // PCM16 chunks from worklet → WebSocket
        workletNode.port.onmessage = (e: MessageEvent) => {
          if (ws.readyState === WebSocket.OPEN) {
            const b64 = arrayBufferToBase64(e.data);
            ws.send(JSON.stringify({ type: "audio", data: b64 }));
          }
        };
      };

      ws.onmessage = (e: MessageEvent) => {
        const msg = JSON.parse(e.data);

        switch (msg.type) {
          case "ready":
            // Server is ready — state will be set by subsequent "state" message
            break;

          case "state":
            setState(msg.state as VoiceState);
            break;

          case "audio":
            playAudioChunk(msg.data);
            break;

          case "interrupted":
            clearPlayback();
            break;

          case "turn_complete":
            // State handled by "state" message that follows
            break;

          case "transcript_in":
            setTranscript((prev) => [...prev, { role: "user", text: msg.text }]);
            break;

          case "transcript_out":
            setTranscript((prev) => [...prev, { role: "maya", text: msg.text }]);
            break;

          case "ping":
            ws.send(JSON.stringify({ type: "pong" }));
            break;

          case "error":
            console.error("[LiveVoice] Server error:", msg.message);
            cleanup();
            break;
        }
      };

      ws.onclose = () => {
        cleanup();
      };

      ws.onerror = () => {
        cleanup();
      };
    } catch (err) {
      console.error("[LiveVoice] Start failed:", err);
      cleanup();
    }
  }, [agentId, cleanup, clearPlayback, playAudioChunk]);

  // ── End call ────────────────────────────────────────────────────────────
  const endCall = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end" }));
    }
    cleanup();
  }, [cleanup]);

  const isActive = state !== "disconnected" && state !== "connecting";

  return (
    <div className="p-8" dir="rtl">
      <div className="max-w-lg mx-auto">
        {/* State indicator */}
        <div className="flex flex-col items-center gap-4 py-8">
          <div className={`w-4 h-4 rounded-full ${STATE_COLORS[state]}`} />
          <p className="text-white text-sm font-medium">{STATE_LABELS[state]}</p>
        </div>

        {/* Controls */}
        <div className="flex justify-center gap-3">
          {state === "disconnected" ? (
            <button
              onClick={startCall}
              className="flex items-center gap-2 px-6 py-3 bg-brand-600 hover:bg-brand-500 text-white rounded-xl font-medium transition-colors"
            >
              <Mic className="w-5 h-5" />
              התחל שיחה
            </button>
          ) : (
            <button
              onClick={endCall}
              disabled={state === "connecting"}
              className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-500 text-white rounded-xl font-medium transition-colors disabled:opacity-40"
            >
              <PhoneOff className="w-5 h-5" />
              סיים שיחה
            </button>
          )}
        </div>

        {/* Transcript (collapsed by default) */}
        {transcript.length > 0 && (
          <div className="mt-6 border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setShowTranscript(!showTranscript)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-400 hover:text-gray-300 transition-colors"
            >
              <span>תמליל ({transcript.length})</span>
              {showTranscript ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {showTranscript && (
              <div className="px-4 pb-4 max-h-60 overflow-y-auto space-y-2">
                {transcript.map((entry, i) => (
                  <div key={i} className={`text-sm ${entry.role === "user" ? "text-gray-300" : "text-brand-400"}`}>
                    <span className="font-medium">{entry.role === "user" ? "את/ה:" : "מאיה:"}</span>{" "}
                    {entry.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/components/agents/live-voice-panel.tsx
git commit -m "feat: add LiveVoicePanel component for browser voice"
```

---

### Task 7: Add "Live Voice" tab to agent page

**Files:**
- Modify: `dashboard/components/agents/agent-page-tabs.tsx`

- [ ] **Step 1: Add import and tab**

In `agent-page-tabs.tsx`, add the import after line 8:

```typescript
import { LiveVoicePanel } from "./live-voice-panel";
```

Change the `Tab` type on line 16:

```typescript
type Tab = "settings" | "assets" | "voice";
```

Add the voice tab button after the assets tab button (after line 56, inside the `flex gap-1 pt-2` div):

```tsx
            <button
              onClick={() => setActiveTab("voice")}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
                activeTab === "voice"
                  ? "text-white border-brand-600 bg-surface-2"
                  : "text-gray-500 border-transparent hover:text-gray-300"
              }`}
            >
              Live Voice
            </button>
```

Add the voice tab content after line 74 (after the assets tab content):

```tsx
      {activeTab === "voice" && (
        <LiveVoicePanel agentId={agent.id} />
      )}
```

- [ ] **Step 2: Verify build compiles**

Run: `cd c:/Users/lidor/maya-ai/dashboard && npx tsc --noEmit 2>&1 | grep -i "agent-page-tabs\|live-voice" || echo "No errors"`
Expected: `No errors`

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/agents/agent-page-tabs.tsx
git commit -m "feat: add Live Voice tab to agent page"
```

---

### Task 8: Add API_BASE_URL as NEXT_PUBLIC env var

**Files:**
- Modify: `dashboard/.env.local`
- Modify: `dashboard/.env.local.example`

- [ ] **Step 1: Add NEXT_PUBLIC_API_BASE_URL**

The LiveVoicePanel needs to build the WebSocket URL client-side. Add to `dashboard/.env.local.example`:

```
# Backend WebSocket URL for Live Voice (browser needs this)
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Add the same to `dashboard/.env.local` (with the actual value).

- [ ] **Step 2: Commit**

```bash
git add dashboard/.env.local.example
git commit -m "feat: add NEXT_PUBLIC_API_BASE_URL for browser voice WebSocket"
```

---

### Task 9: End-to-end test

- [ ] **Step 1: Restart backend**

```bash
taskkill //F //FI "IMAGENAME eq python.exe" 2>&1
cd c:/Users/lidor/maya-ai
export $(grep -E '^(GEMINI_API_KEY|GEMINI_API_KEY_REST|OPENAI_API_KEY|SUPABASE_URL|SUPABASE_SERVICE_KEY)=' .env | xargs)
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

Wait 4 seconds, verify: `curl http://localhost:8000/health`

- [ ] **Step 2: Verify WebSocket endpoint exists**

```bash
python -c "
import asyncio, websockets, json
async def test():
    try:
        ws = await websockets.connect('ws://localhost:8000/ws/voice-browser?agent_id=test')
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(json.loads(msg))
        await ws.close()
    except Exception as e:
        print(f'Expected error: {e}')
asyncio.run(test())
"
```

Expected: Error message about invalid agent_id or Gemini connection — confirming the endpoint is live and processing.

- [ ] **Step 3: Start dashboard dev server**

```bash
cd c:/Users/lidor/maya-ai/dashboard && npm run dev
```

- [ ] **Step 4: Open agent page and test**

1. Open `http://localhost:3000/dashboard/agents/<agent-id>` in browser
2. Click "Live Voice" tab
3. Click "התחל שיחה"
4. Speak — verify Maya responds in real-time
5. Click "סיים שיחה" — verify cleanup

- [ ] **Step 5: Check logs**

```bash
grep "BROWSER-WS" server.log | tail -20
```

Verify: No errors, agent config loaded, Gemini setup successful, audio flowing.

- [ ] **Step 6: Final commit with all files**

```bash
git add -A
git commit -m "feat: complete Live Voice Browser MVP — end-to-end working"
```

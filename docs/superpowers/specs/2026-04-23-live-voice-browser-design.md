# Live Voice Browser — Design Spec

**Date:** 2026-04-23
**Status:** Approved
**Goal:** Real-time voice conversation with Maya from the dashboard browser, using Gemini Live via a proxy WebSocket through the backend.

---

## 1. Overview

Add a "Live Voice" tab to each agent page in the dashboard. The user clicks "Start", the browser captures microphone audio as PCM16@16kHz via AudioWorklet, streams it through a FastAPI WebSocket proxy to Gemini Live, and plays back Gemini's audio response in real-time. Latency target: under 1 second end-to-end.

**What this is:** MVP of browser-based real-time voice for a single user.
**What this is NOT:** Multi-tenant auth, analytics, call recording UI.
**Architecture:** Designed so multi-tenant can be added later without rewrite.

---

## 2. Architecture

```
Browser (PCM16 16kHz)
    ↕ WebSocket
FastAPI proxy (/ws/voice-browser?agent_id=<uuid>)
    ↕ WebSocket
Gemini Live API (wss://generativelanguage.googleapis.com/...)
```

- API key stays on server — never exposed to browser
- Reuses existing agent config loading, lead extraction, and webhook delivery from voice_gemini.py
- No audio format conversion needed — browser sends PCM16@16kHz, Gemini returns PCM16@24kHz

---

## 3. Backend

### 3.1 WebSocket Endpoint

**Route:** `GET /ws/voice-browser?agent_id=<uuid>`
**File:** `app/routes/voice_browser.py`
**Router registration:** `main.py`

**Lifecycle:**
1. Accept browser WebSocket connection
2. Load agent config from Supabase via `fetch_supabase_agent_config()` (by agent_id, not phone number — requires small adapter since existing function looks up by phone)
3. Open Gemini Live WebSocket with setup message:
   - System instruction from agent config (with first_message injection if set)
   - Voice from agent config (validated against allowed list, default Zephyr)
   - VAD: `silence_duration_ms: 300`, `start_of_speech_sensitivity: HIGH`
   - `response_modalities: ["AUDIO"]`
   - `input_audio_transcription: {}`, `output_audio_transcription: {}`
4. Send `{"type": "ready"}` to browser
5. Run two concurrent loops:
   - **browser→gemini:** receive audio chunks, forward as `realtime_input.audio`
   - **gemini→browser:** receive audio/transcripts/interrupts, forward to browser
6. On disconnect (browser closes, error, or `end` message):
   - Close Gemini WebSocket
   - If transcript has meaningful content (see 3.3), extract lead and save
   - Fire webhook if configured

### 3.2 Message Protocol

**Browser → Server:**
```json
{"type": "audio", "data": "<base64 PCM16 16kHz mono>"}
{"type": "end"}
```

**Server → Browser:**
```json
{"type": "ready"}
{"type": "audio", "data": "<base64 PCM16 24kHz mono>"}
{"type": "state", "state": "listening"}
{"type": "state", "state": "thinking"}
{"type": "state", "state": "speaking"}
{"type": "transcript_in", "text": "..."}
{"type": "transcript_out", "text": "..."}
{"type": "interrupted"}
{"type": "turn_complete"}
{"type": "error", "message": "..."}
```

**State emission logic:**
- `listening`: sent after setup complete and after each `turn_complete`
- `thinking`: sent when Gemini signals end of user speech (no audio output yet)
- `speaking`: sent when first audio chunk arrives from Gemini in a turn

### 3.3 Lead Extraction Guard

Only extract/save lead if transcript meets ALL of:
- At least 2 turns (user spoke at least twice)
- Combined transcript length > 50 characters
- Not just greetings (not only "שלום", "היי", "ביי")

Otherwise: close cleanly, no lead created.

### 3.4 Heartbeat & Cleanup

- Server sends `{"type": "ping"}` every 15 seconds to browser
- Browser responds with `{"type": "pong"}`
- If no pong received within 10 seconds → close connection, cleanup
- If Gemini WebSocket drops → send `{"type": "error"}` to browser, close
- If browser disconnects → close Gemini WebSocket, run lead extraction if applicable
- All resources (WebSocket connections, async tasks) cleaned up in `finally` block

### 3.5 Reuse from voice_gemini.py

The following are reused directly (imported, not copied):
- `fetch_supabase_agent_config()` from `app/services/agent_config.py`
- Gemini setup message structure (voice, VAD, system_instruction format)
- `_extract_lead_from_transcript()` — may need to extract to shared module if currently private
- Lead save to Supabase (upsert to `leads` table)
- Webhook delivery logic

**Agent lookup adapter:** `fetch_supabase_agent_config()` currently looks up by phone number. Add a thin wrapper or parameter that allows lookup by `agent_id` directly (SELECT from `agents_config` WHERE `id = agent_id`). Minimal change.

---

## 4. Frontend

### 4.1 AudioWorklet — PCM16 Capture

**File:** `dashboard/public/pcm-worklet.js`

- Runs in audio thread, zero main-thread blocking
- `AudioContext` created at sampleRate 16000
- Every ~100ms: collects buffer (~1600 samples), converts to Int16, posts to main thread
- Main thread base64-encodes and sends via WebSocket

### 4.2 Playback Engine

- Receives base64 PCM16@24kHz chunks from WebSocket
- Decodes to Float32Array
- Creates `AudioBuffer(1, samples, 24000)`
- Schedules with `audioContext.currentTime` for gapless playback
- On `interrupted`: cancels all scheduled buffers immediately (enables barge-in)

### 4.3 UI Component

**File:** `dashboard/components/agents/live-voice-panel.tsx`
**Type:** React client component (`"use client"`)
**Placement:** New tab "Live Voice" in agent page tabs (agent-page-tabs.tsx). No changes to existing tabs.

**Layout:**
```
┌─────────────────────────────────────┐
│         ● Maya (listening...)       │  state indicator
│        ╭───────────────────╮        │
│        │   ≋≋ waveform ≋≋  │        │  audio visualization
│        ╰───────────────────╯        │
│     [ 🎤 Start ] [ ✕ End Call ]     │  controls
│  ▸ Transcript (collapsed)          │  collapsible transcript
└─────────────────────────────────────┘
```

**States:**

| State | Indicator | Controls |
|---|---|---|
| `disconnected` | "התחל שיחה עם Maya" | [Start] enabled |
| `connecting` | spinner + "מתחברת..." | [Start] disabled |
| `listening` | green pulse + "מקשיבה..." | [End] enabled |
| `thinking` | dots pulse + "חושבת..." | [End] enabled |
| `speaking` | purple pulse + "מדברת..." | [End] enabled |

**Key behaviors:**
- **No auto-start:** Microphone only activates after explicit "Start" click
- **Barge-in:** User can speak while Maya is speaking — `interrupted` event clears playback
- **Transcript:** Collapsed by default, expandable. Shows user/Maya turns in real-time. RTL.
- **Expand mode:** Button that toggles CSS class for full-viewport overlay. Not fullscreen API.
- **Reconnect:** On unexpected disconnect, show "התנתקה. נסה שוב" with reconnect button. No auto-reconnect.

### 4.4 Waveform Visualization

- `AnalyserNode` connected to both mic input and playback output
- Canvas-based (not SVG) for performance
- Switches color based on state: green (listening) / purple (speaking)
- Simple bar visualization, ~30fps

### 4.5 Heartbeat (client side)

- Responds to server `ping` with `pong`
- If no server message received for 20 seconds → assume dead, show disconnect UI, cleanup

---

## 5. Files to Create

| File | Purpose |
|---|---|
| `app/routes/voice_browser.py` | FastAPI WebSocket proxy endpoint |
| `dashboard/public/pcm-worklet.js` | AudioWorklet for PCM16 capture |
| `dashboard/components/agents/live-voice-panel.tsx` | React UI component |

## 6. Files to Modify

| File | Change |
|---|---|
| `main.py` | Register voice_browser router |
| `dashboard/components/agents/agent-page-tabs.tsx` | Add "Live Voice" tab |
| `app/services/agent_config.py` | Add agent_id lookup adapter (if not already supported) |

## 7. Files NOT Modified

- `app/routes/voice_gemini.py` — Twilio path untouched
- `app/utils/audio_gemini.py` — Twilio audio conversion untouched
- All existing dashboard pages and components — untouched
- Auth, RLS, middleware — untouched

---

## 8. Success Criteria

1. User clicks "Start" on agent page → mic activates → Maya greets (if first_message set)
2. User speaks Hebrew → Maya responds in real-time voice with correct agent personality
3. Latency from end of user speech to start of Maya audio < 1.5 seconds
4. Barge-in works: speaking while Maya talks interrupts her
5. Transcript shows conversation in real-time
6. On disconnect with meaningful conversation: lead saved to Supabase
7. No zombie WebSocket connections — all cleaned up on disconnect/error
8. Existing Twilio voice path completely unaffected

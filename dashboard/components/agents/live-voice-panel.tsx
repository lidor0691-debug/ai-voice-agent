"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Mic, PhoneOff, ChevronDown, ChevronUp } from "lucide-react";

// ── Tuning constants (easy to adjust without touching worklet) ───────────────
const CAPTURE_SAMPLE_RATE = 16000;   // Hz — must match what Gemini expects
const PLAYBACK_SAMPLE_RATE = 24000;  // Hz — Gemini output format
const JITTER_BUFFER_MS = 0.08;       // seconds ahead of currentTime for gapless playback

// ── Types ───────────────────────────────────────────────────────────────────
type VoiceState = "disconnected" | "connecting" | "listening" | "thinking" | "speaking";

interface TranscriptEntry {
  role: "user" | "maya";
  text: string;
}

interface ActionProposalData {
  action: string;
  status: string;
  agent_id: string;
  lead_id: string;
  lead_name: string;
  channel: string;
  message: string;
}

interface Props {
  agentId: string;
  mode?: "preview" | "assistant";
  onUiAction?: (action: string, target: string, extra?: Record<string, string>) => void;
  onActionProposal?: (proposal: ActionProposalData) => void;
}

const PREVIEW_LABELS: Record<VoiceState, string> = {
  disconnected: "בדוק את הסוכן",
  connecting: "מתחברת...",
  listening: "מקשיבה...",
  thinking: "חושבת...",
  speaking: "מדברת...",
};

const ASSISTANT_LABELS: Record<VoiceState, string> = {
  disconnected: "דבר עם מאיה",
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

// ── Helpers ─────────────────────────────────────────────────────────────────
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function base64ToInt16(base64: string): Int16Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}

function buildWsUrl(agentId: string, mode: string): string {
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  const wsBase = apiBase.replace(/^http/, "ws");
  return `${wsBase}/ws/voice-browser?agent_id=${agentId}&mode=${mode}`;
}

// ── Component ───────────────────────────────────────────────────────────────
export function LiveVoicePanel({ agentId, mode = "preview", onUiAction, onActionProposal }: Props) {
  const stateLabels = mode === "assistant" ? ASSISTANT_LABELS : PREVIEW_LABELS;
  const [state, setState] = useState<VoiceState>("disconnected");
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [showTranscript, setShowTranscript] = useState(false);
  const onUiActionRef = useRef(onUiAction);
  onUiActionRef.current = onUiAction;
  const onActionProposalRef = useRef(onActionProposal);
  onActionProposalRef.current = onActionProposal;

  const wsRef = useRef<WebSocket | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const nextPlayTimeRef = useRef(0);
  const scheduledSourcesRef = useRef<AudioBufferSourceNode[]>([]);

  // ── Cleanup all resources ─────────────────────────────────────────────
  const cleanup = useCallback(() => {
    // Mic
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    if (micSourceRef.current) {
      micSourceRef.current.disconnect();
      micSourceRef.current = null;
    }
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (captureCtxRef.current) {
      captureCtxRef.current.close().catch(() => {});
      captureCtxRef.current = null;
    }

    // Playback
    scheduledSourcesRef.current.forEach((s) => {
      try { s.stop(); } catch { /* already stopped */ }
    });
    scheduledSourcesRef.current = [];
    if (playbackCtxRef.current) {
      playbackCtxRef.current.close().catch(() => {});
      playbackCtxRef.current = null;
    }
    nextPlayTimeRef.current = 0;

    // WebSocket
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* already closed */ }
      wsRef.current = null;
    }

    setState("disconnected");
  }, []);

  // Cleanup on unmount
  useEffect(() => () => cleanup(), [cleanup]);

  // ── Clear scheduled playback (barge-in) ───────────────────────────────
  const clearPlayback = useCallback(() => {
    scheduledSourcesRef.current.forEach((s) => {
      try { s.stop(); } catch { /* already stopped */ }
    });
    scheduledSourcesRef.current = [];
    nextPlayTimeRef.current = 0;
  }, []);

  // ── Play a PCM16 24kHz audio chunk ────────────────────────────────────
  const playAudioChunk = useCallback((base64Data: string) => {
    const ctx = playbackCtxRef.current;
    if (!ctx) return;

    const int16 = base64ToInt16(base64Data);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }

    const audioBuffer = ctx.createBuffer(1, float32.length, PLAYBACK_SAMPLE_RATE);
    audioBuffer.copyToChannel(float32, 0);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    // Schedule with jitter buffer for gapless playback
    const now = ctx.currentTime + JITTER_BUFFER_MS;
    const startTime = Math.max(now, nextPlayTimeRef.current);
    nextPlayTimeRef.current = startTime + audioBuffer.duration;

    source.start(startTime);
    scheduledSourcesRef.current.push(source);
    source.onended = () => {
      scheduledSourcesRef.current = scheduledSourcesRef.current.filter((s) => s !== source);
    };
  }, []);

  // ── Start call ────────────────────────────────────────────────────────
  const startCall = useCallback(async () => {
    setState("connecting");
    setTranscript([]);

    try {
      // 1. Create playback context
      playbackCtxRef.current = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE });

      // 2. Request microphone
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;

      // 3. Create capture context at target sample rate
      const captureCtx = new AudioContext({ sampleRate: CAPTURE_SAMPLE_RATE });
      captureCtxRef.current = captureCtx;

      // 4. Load AudioWorklet
      await captureCtx.audioWorklet.addModule("/pcm-worklet.js");
      const workletNode = new AudioWorkletNode(captureCtx, "pcm16-processor");
      workletNodeRef.current = workletNode;

      const micSource = captureCtx.createMediaStreamSource(stream);
      micSourceRef.current = micSource;
      micSource.connect(workletNode);
      // workletNode intentionally not connected to destination (no local echo)

      // 5. Connect WebSocket
      const wsUrl = buildWsUrl(agentId, mode);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // Wire worklet output to WebSocket
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
            // Server ready — state transitions via "state" messages
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
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "pong" }));
            }
            break;

          case "ui_action":
            console.log("[LiveVoice] ui_action received:", msg.action, msg.target, msg.tab);
            if (onUiActionRef.current) onUiActionRef.current(msg.action, msg.target, msg);
            break;

          case "action_proposal":
            console.log("[LiveVoice] action_proposal received:", msg.action, msg.lead_name);
            if (onActionProposalRef.current) onActionProposalRef.current(msg as ActionProposalData);
            break;

          case "error":
            console.error("[LiveVoice] Server error:", msg.message);
            cleanup();
            break;
        }
      };

      ws.onclose = () => cleanup();
      ws.onerror = () => cleanup();

    } catch (err) {
      console.error("[LiveVoice] Start failed:", err);
      cleanup();
    }
  }, [agentId, mode, cleanup, clearPlayback, playAudioChunk]);

  // ── End call ──────────────────────────────────────────────────────────
  const endCall = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end" }));
    }
    cleanup();
  }, [cleanup]);

  return (
    <div className="p-8" dir="rtl">
      <div className="max-w-lg mx-auto">
        {/* State indicator */}
        <div className="flex flex-col items-center gap-4 py-8">
          <div className={`w-4 h-4 rounded-full ${STATE_COLORS[state]}`} />
          <p className="text-white text-sm font-medium">{stateLabels[state]}</p>
        </div>

        {/* Controls */}
        <div className="flex justify-center gap-3">
          {state === "disconnected" ? (
            <button
              onClick={startCall}
              className="flex items-center gap-2 px-6 py-3 bg-brand-600 hover:bg-brand-500 text-white rounded-xl font-medium transition-colors"
            >
              <Mic className="w-5 h-5" />
              {mode === "assistant" ? "דבר עם מאיה" : "בדוק את הסוכן"}
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

        {/* Preview disclaimer */}
        {mode === "preview" && (
          <p className="text-center text-gray-600 text-[11px] mt-4">
            שיחה זו היא לבדיקה בלבד — לא נשמרים לידים ולא נשלחות פעולות
          </p>
        )}

        {/* Transcript (preview mode only — assistant mode doesn't need it) */}
        {mode === "preview" && transcript.length > 0 && (
          <div className="mt-6 border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setShowTranscript(!showTranscript)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-400 hover:text-gray-300 transition-colors"
            >
              <span>תמליל ({transcript.length})</span>
              {showTranscript ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
            {showTranscript && (
              <div className="px-4 pb-4 max-h-60 overflow-y-auto space-y-2">
                {transcript.map((entry, i) => (
                  <div
                    key={i}
                    className={`text-sm ${
                      entry.role === "user" ? "text-gray-300" : "text-brand-400"
                    }`}
                  >
                    <span className="font-medium">
                      {entry.role === "user" ? "את/ה:" : "מאיה:"}
                    </span>{" "}
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

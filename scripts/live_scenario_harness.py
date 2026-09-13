"""
GPT-Live 1 scenario harness — measured Hebrew conversation tests WITHOUT Twilio.

Synthesises Hebrew caller speech with OpenAI TTS, converts it to the exact
µ-law 8 kHz stream Twilio would deliver, and plays it into a real gpt-live-1
session on a scripted timeline, using the SAME session.start payload and
prompts as the POC route (app.routes.voice_live_poc). Records what Maya said,
when audio started/stopped, and derives the comparison metrics.

This is the executable form of the Hebrew scenario matrix in
docs/gpt-live-1-poc.md. It costs real money (≈$0.05/min voice + backend
tokens + TTS) — a full run is roughly 6–8 session-minutes.

Usage (needs OPENAI_API_KEY; run via `railway run` for the project key):
    python scripts/live_scenario_harness.py                  # all scenarios
    python scripts/live_scenario_harness.py S5 S9            # a subset
    LIVE_POC_DELEGATION=client python scripts/live_scenario_harness.py   # no backend
Outputs one JSON line per scenario and a summary table; writes
live_scenario_results.json next to the script.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "k")
os.environ.setdefault("GEMINI_API_KEY", "k")

import app.routes.voice_live_poc as poc                      # noqa: E402
from app.utils.audio_gemini import gemini_to_twilio          # noqa: E402  PCM16 24k → µ-law 8k
from app.routes.voice_gemini import _CLOSING_PHRASES         # noqa: E402

KEY = os.environ["OPENAI_API_KEY"]
LIVE_URL = "wss://api.openai.com/v1/live/sessions"
CACHE = ROOT / "scripts" / ".tts_cache"
CACHE.mkdir(exist_ok=True)
SILENCE = b"\xff" * 160                       # 20 ms µ-law silence
FRAME_S = 0.02
VOICED_RMS = 300.0                            # µ-law→PCM16 RMS above which a frame counts as speech


def _ulaw_rms(raw: bytes) -> float:
    from app.utils.audio_gemini import _ulaw_to_linear
    if not raw:
        return 0.0
    acc = 0
    for b in raw:
        s = _ulaw_to_linear(b)
        acc += s * s
    return (acc / len(raw)) ** 0.5
OFFICE = "מהמשרד של רועי"
FILLERS = ("בסדר גמור", "אוקיי", "סבבה", "מעולה", "בסדר,")


# ── TTS → µ-law ──────────────────────────────────────────────────────────────

async def tts_ulaw(text: str, voice: str = "ash", gain: float = 1.0) -> bytes:
    """Hebrew (or English) speech as raw µ-law 8 kHz bytes. Cached on disk."""
    key = hashlib.md5(f"{voice}|{text}".encode()).hexdigest()
    f = CACHE / f"{key}.ulaw"
    if f.exists():
        raw = f.read_bytes()
    else:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post("https://api.openai.com/v1/audio/speech",
                             headers={"Authorization": f"Bearer {KEY}"},
                             json={"model": "gpt-4o-mini-tts", "voice": voice, "input": text,
                                   "response_format": "pcm"})
            r.raise_for_status()
        pcm24 = r.content                       # PCM16 LE mono 24 kHz
        raw = base64.b64decode(gemini_to_twilio(base64.b64encode(pcm24).decode()))
        f.write_bytes(raw)
    if gain != 1.0:
        raw = _apply_gain(raw, gain)
    return raw


def _apply_gain(ulaw: bytes, gain: float) -> bytes:
    from app.utils.audio_gemini import _linear_to_ulaw, _ulaw_to_linear
    out = bytearray()
    for b in ulaw:
        s = int(_ulaw_to_linear(b) * gain)
        s = max(-32767, min(32767, s))
        out.append(_linear_to_ulaw(s))
    return bytes(out)


def white_noise_ulaw(seconds: float, amp: int = 6000) -> bytes:
    import random
    from app.utils.audio_gemini import _linear_to_ulaw
    rnd = random.Random(7)
    return bytes(_linear_to_ulaw(rnd.randint(-amp, amp)) for _ in range(int(seconds * 8000)))


# ── Session driver ───────────────────────────────────────────────────────────

class LiveBench:
    def __init__(self, name: str, tenant_prompt: str):
        self.name = name
        self.ws = None
        self.t0 = 0.0
        self.events: list[dict] = []          # raw server events with t
        self.out_audio_times: list[float] = []
        self.out_bytes = 0
        self.transcript = poc.TranscriptAccumulator()
        self.caller_marks: list[dict] = []    # {"label", "start", "end"}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.started = asyncio.Event()
        self.closed = None
        self.errors: list[dict] = []
        self.delegations = 0
        self.pending_delegations = 0
        self.last_delegation_done = 0.0
        self.usage_seconds = None
        self.tenant_prompt = tenant_prompt
        self._pump_task = None
        self._recv_task = None

    def now(self) -> float:
        return time.monotonic() - self.t0

    async def __aenter__(self):
        self.ws = await websockets.connect(
            LIVE_URL, additional_headers={"Authorization": f"Bearer {KEY}"}, max_size=None)
        self.t0 = time.monotonic()
        voice = poc.build_voice_instructions(OFFICE, delegation_mode=poc.LIVE_POC_DELEGATION)
        backend = poc.build_backend_instructions(self.tenant_prompt, OFFICE, True)
        await self.ws.send(json.dumps(poc.build_session_start(voice, backend), ensure_ascii=False))
        self._recv_task = asyncio.create_task(self._recv())
        await asyncio.wait_for(self.started.wait(), timeout=15)
        self._pump_task = asyncio.create_task(self._pump())
        greeting = poc.build_greeting_line("", OFFICE)
        await self.ws.send(json.dumps({
            "type": "session.instructions.append", "event_id": "greet", "delegation_id": None,
            "content": f"פתחי עכשיו את השיחה, בעברית, במשפט הבא בדיוק ובלי שום תוספת: \"{greeting}\"",
        }, ensure_ascii=False))
        return self

    async def __aexit__(self, *exc):
        try:
            await self.ws.send(json.dumps({"type": "session.close"}))
            for _ in range(120):
                if self.closed:
                    break
                await asyncio.sleep(0.1)
        except Exception:
            pass
        for t in (self._pump_task, self._recv_task):
            if t:
                t.cancel()
        try:
            await self.ws.close()
        except Exception:
            pass

    async def _pump(self):
        """Real-time µ-law pump: queued speech bytes, else silence. 20 ms cadence."""
        buf = b""
        label = None
        next_t = time.monotonic()
        while True:
            if not buf and not self.queue.empty():
                label, buf = self.queue.get_nowait()
                self.caller_marks.append({"label": label, "start": self.now(), "end": None})
            if buf:
                frame, buf = buf[:160], buf[160:]
                if len(frame) < 160:
                    frame = frame + SILENCE[:160 - len(frame)]
                if not buf:
                    self.caller_marks[-1]["end"] = self.now() + FRAME_S
            else:
                frame = SILENCE
            await self.ws.send(json.dumps({"type": "session.input_audio.append",
                                           "audio": base64.b64encode(frame).decode()}))
            next_t += FRAME_S
            await asyncio.sleep(max(0.0, next_t - time.monotonic()))

    async def _recv(self):
        try:
            async for raw in self.ws:
                ev = json.loads(raw)
                t = ev.get("type", "")
                now = self.now()
                self.events.append({"t": now, "type": t})
                if t == "session.started":
                    self.started.set()
                elif t == "session.output_audio.delta":
                    raw_b = base64.b64decode(ev.get("delta", ""))
                    self.out_bytes += len(raw_b)
                    # GPT-Live streams output CONTINUOUSLY (silence included), so
                    # "any delta" is not "Maya speaking". Track only voiced frames.
                    if _ulaw_rms(raw_b) >= VOICED_RMS:
                        self.out_audio_times.append(now)
                        self.events[-1]["voiced"] = True
                elif t == "session.output_transcript.delta":
                    self.transcript.assistant(ev.get("delta", ""))
                    self.events[-1]["delta"] = ev.get("delta", "")
                elif t == "session.input_transcript.delta":
                    self.transcript.caller(ev.get("delta", ""))
                    self.events[-1]["delta"] = ev.get("delta", "")
                elif t == "session.delegation.created":
                    self.delegations += 1
                    self.pending_delegations += 1
                elif t == "response.event":
                    inner = (ev.get("event") or {}).get("type", "")
                    if inner in ("response.completed", "response.failed", "response.incomplete"):
                        self.pending_delegations = max(0, self.pending_delegations - 1)
                        self.last_delegation_done = now
                elif t == "error":
                    self.errors.append(ev.get("error"))
                elif t == "session.closed":
                    self.closed = ev
                    self.usage_seconds = (ev.get("usage") or {}).get("seconds")
                    return
        except Exception:
            return

    # — scripted actions —
    async def say(self, text: str, label: str = None, gain: float = 1.0, voice: str = "ash"):
        await self.queue.put((label or text[:24], await tts_ulaw(text, voice=voice, gain=gain)))

    async def noise(self, seconds: float, label="noise"):
        await self.queue.put((label, white_noise_ulaw(seconds)))

    async def wait_maya_started(self, timeout=8.0) -> bool:
        n = len(self.out_audio_times)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if len(self.out_audio_times) > n:
                return True
            await asyncio.sleep(0.05)
        return False

    async def wait_maya_silent(self, quiet_s=1.2, timeout=25.0) -> bool:
        """Silent = no voiced output for quiet_s AND no backend delegation in
        flight (and a short settle after one completes, so the spoken result is
        included). Without this the bench cut sessions mid-delegation."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            quiet = self.out_audio_times and (self.now() - self.out_audio_times[-1]) >= quiet_s
            settled = self.pending_delegations == 0 and (self.now() - self.last_delegation_done) >= 2.5
            if quiet and settled:
                return True
            await asyncio.sleep(0.05)
        return False

    async def wait_maya_speaking_for(self, seconds: float, timeout=15.0) -> bool:
        """Wait until Maya has been continuously producing audio for `seconds`."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if len(self.out_audio_times) >= 2:
                first = self._current_burst_start()
                if first is not None and (self.now() - first) >= seconds \
                        and (self.now() - self.out_audio_times[-1]) < 0.5:
                    return True
            await asyncio.sleep(0.05)
        return False

    def _current_burst_start(self):
        if not self.out_audio_times:
            return None
        start = self.out_audio_times[-1]
        for a, b in zip(reversed(self.out_audio_times[:-1]), reversed(self.out_audio_times)):
            if b - a > 0.8:
                break
            start = a
        return start

    # — metrics —
    def reply_latency_ms(self, mark_label: str):
        """Caller audio END → first VOICED output frame (energy-gated)."""
        m = next((m for m in self.caller_marks if m["label"] == mark_label), None)
        if not m or m["end"] is None:
            return None
        first = next((t for t in self.out_audio_times if t > m["end"]), None)
        return None if first is None else round((first - m["end"]) * 1000)

    def reply_latency_transcript_ms(self, mark_label: str):
        """Caller audio END → first assistant transcript fragment (independent
        cross-check of the energy-based number; transcript lags audio slightly)."""
        m = next((m for m in self.caller_marks if m["label"] == mark_label), None)
        if not m or m["end"] is None:
            return None
        first = next((e["t"] for e in self.events
                      if e["type"] == "session.output_transcript.delta" and e["t"] > m["end"]
                      and (e.get("delta") or "").strip()), None)
        return None if first is None else round((first - m["end"]) * 1000)

    def stop_after_ms(self, mark_label: str, window=3.0):
        """How long Maya kept emitting audio after the caller STARTED speaking."""
        m = next((m for m in self.caller_marks if m["label"] == mark_label), None)
        if not m:
            return None
        later = [t for t in self.out_audio_times if m["start"] <= t <= m["start"] + window]
        return 0 if not later else round((max(later) - m["start"]) * 1000)

    def maya_text_after(self, mark_label: str) -> str:
        m = next((m for m in self.caller_marks if m["label"] == mark_label), None)
        if not m:
            return ""
        return "".join(e.get("delta", "") for e in self.events
                       if e["type"] == "session.output_transcript.delta" and e["t"] > m["start"])

    def closing_count(self) -> int:
        txt = " ".join(self.transcript.assistant_lines)
        return sum(txt.count(p) for p in _CLOSING_PHRASES)

    def repeated_sentences(self) -> int:
        seen, dup = set(), 0
        for line in self.transcript.assistant_lines:
            for s in [x.strip() for x in line.replace("?", ".").replace("!", ".").split(".") if len(x.strip()) > 12]:
                if s in seen:
                    dup += 1
                seen.add(s)
        return dup


# ── Scenarios ────────────────────────────────────────────────────────────────

async def s1_hello_during_greeting(b: LiveBench):
    assert await b.wait_maya_started()
    await asyncio.sleep(0.4)
    await b.say("הלו?", label="hello")
    await b.wait_maya_silent(timeout=15)
    return {"stop_after_ms": b.stop_after_ms("hello"), "reply_ms": b.reply_latency_ms("hello"),
            "maya_after": b.maya_text_after("hello")}


async def s2_interrupt_mid_sentence(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("תסבירי לי בבקשה מה ההבדל בין ביטוח חיים ריסק לביטוח מנהלים, ומה כדאי לי", label="q")
    ok = await b.wait_maya_speaking_for(1.5)
    await b.say("רגע רגע, שנייה, לא הבנתי", label="interrupt")
    await b.wait_maya_silent(timeout=20)
    return {"maya_was_talking": ok, "stop_after_ms": b.stop_after_ms("interrupt"),
            "reply_ms": b.reply_latency_ms("interrupt"), "maya_after": b.maya_text_after("interrupt")}


async def s3_quiet_speech(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("אני צריך שרועי יחזור אליי", label="quiet", gain=0.2)
    heard = await b.wait_maya_started(timeout=6)
    await b.wait_maya_silent(timeout=15)
    return {"maya_replied": heard, "reply_ms": b.reply_latency_ms("quiet"),
            "caller_transcribed": " ".join(b.transcript.caller_lines),
            "maya_after": b.maya_text_after("quiet")}


async def s4_name_correction(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("אני רוצה שרועי יחזור אליי לגבי הביטוח שלי", label="reason")
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("קוראים לי שרון", label="name1")
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("לא, לא שרון. לידור.", label="fix")
    await b.wait_maya_started(); await b.wait_maya_silent()
    after = b.maya_text_after("fix")
    return {"reply_ms": b.reply_latency_ms("fix"), "says_lidor": "לידור" in after,
            "still_says_sharon": "שרון" in after and "לא שרון" not in after, "maya_after": after}


async def s5_question_no_filler(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("תוך כמה זמן רועי חוזר אליי?", label="q")
    await b.wait_maya_started(); await b.wait_maya_silent()
    after = b.maya_text_after("q").strip()
    return {"reply_ms": b.reply_latency_ms("q"),
            "opens_with_filler": any(after.startswith(f) for f in FILLERS), "maya_after": after}


async def s6_topic_change(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("אני רוצה לחדש את ביטוח הרכב", label="t1")
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("בעצם לא, עזבי את הרכב, זה על ביטוח המשכנתא", label="t2")
    await b.wait_maya_started(); await b.wait_maya_silent()
    after = b.maya_text_after("t2")
    return {"reply_ms": b.reply_latency_ms("t2"), "mentions_mortgage": "משכנת" in after,
            "still_on_car": "רכב" in after and "משכנת" not in after, "maya_after": after}


async def s7_silence(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    n0 = len(b.transcript.assistant_lines)
    await asyncio.sleep(15)
    return {"extra_assistant_turns_in_15s_silence": len(b.transcript.assistant_lines) - n0,
            "closed": b.closed is not None, "maya_text": " ".join(b.transcript.assistant_lines[n0:])}


async def s8_unclear_audio(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.noise(2.0, label="noise")
    replied = await b.wait_maya_started(timeout=6)
    await b.wait_maya_silent(timeout=12)
    after = b.maya_text_after("noise")
    return {"maya_replied_to_noise": replied, "non_hebrew": bool(after.strip()) and not poc._has_hebrew(after),
            "maya_after": after}


async def s9_english_prevention(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("Hi, do you speak English? I need help with my car insurance.", label="en", voice="alloy")
    await b.wait_maya_started(); await b.wait_maya_silent()
    after = b.maya_text_after("en")
    return {"reply_ms": b.reply_latency_ms("en"), "reply_is_hebrew": poc._has_hebrew(after),
            "reply_has_latin": any("a" <= c.lower() <= "z" for c in after), "maya_after": after}


async def s10_closing_once(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("אני לידור, תגידי לרועי שיחזור אליי לגבי ביטוח חיים", label="req")
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("לא, תודה רבה, זה הכל", label="bye")
    await b.wait_maya_started(); await b.wait_maya_silent(quiet_s=2.5, timeout=20)
    return {"reply_ms": b.reply_latency_ms("bye"), "closing_phrases_total": b.closing_count(),
            "repeated_sentences": b.repeated_sentences(), "maya_after": b.maya_text_after("bye")}


async def s11_no_hangup_on_correction(b: LiveBench):
    await b.wait_maya_started(); await b.wait_maya_silent()
    await b.say("אני לידור, שרועי יחזור אליי על ביטוח חיים. זה הכל, תודה.", label="req")
    await b.wait_maya_started(); await b.wait_maya_silent(quiet_s=0.8, timeout=20)
    # The moment a closing phrase appears, the caller objects.
    await b.say("רגע רגע, לא ביטוח חיים — ביטוח בריאות!", label="objection")
    replied = await b.wait_maya_started(timeout=8)
    await b.wait_maya_silent(timeout=15)
    now = b.now()
    last_caller = max((m["end"] or 0) for m in b.caller_marks)
    last_out = b.out_audio_times[-1] if b.out_audio_times else 0
    decision_at_objection = poc.should_close_on_closing_phrase(
        b.transcript.assistant_tail(), last_caller + 0.5, last_caller, last_out, 2.5)
    after = b.maya_text_after("objection")
    return {"maya_replied_after_objection": replied, "mentions_health": "בריאות" in after,
            "poc_would_have_hung_up_during_objection": decision_at_objection,
            "closing_phrases_total": b.closing_count(), "maya_after": after}


SCENARIOS = {
    "S1": ("hello during greeting", s1_hello_during_greeting),
    "S2": ("interrupt mid-sentence", s2_interrupt_mid_sentence),
    "S3": ("quiet speech (gain 0.2)", s3_quiet_speech),
    "S4": ("name correction: לא שרון, לידור", s4_name_correction),
    "S5": ("question, no filler opener", s5_question_no_filler),
    "S6": ("topic change mid-call", s6_topic_change),
    "S7": ("15s silence", s7_silence),
    "S8": ("unclear audio (noise)", s8_unclear_audio),
    "S9": ("English prevention", s9_english_prevention),
    "S10": ("closing once, no script repeat", s10_closing_once),
    "S11": ("no hangup while caller corrects", s11_no_hangup_on_correction),
}


async def fetch_tenant_prompt() -> str:
    url = os.getenv("SUPABASE_URL", ""); key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url.startswith("https://"):
        return "משרד סוכן הביטוח רועי לוי. רועי חוזר ללקוחות בדרך כלל באותו יום עבודה."
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{url.rstrip('/')}/rest/v1/agents_config",
                            params={"id": "eq.5e28e7ec-ec83-4683-af50-3749115cdec7", "select": "system_prompt"},
                            headers={"apikey": key, "Authorization": f"Bearer {key}"})
            return r.json()[0]["system_prompt"]
    except Exception:
        return "משרד סוכן הביטוח רועי לוי."


async def main():
    wanted = [a.upper() for a in sys.argv[1:]] or list(SCENARIOS)
    tenant_prompt = await fetch_tenant_prompt()
    results = []
    print(f"delegation={poc.LIVE_POC_DELEGATION} backend={poc.LIVE_POC_BACKEND_MODEL} "
          f"tenant_prompt_chars={len(tenant_prompt)}")
    for sid in wanted:
        title, fn = SCENARIOS[sid]
        print(f"\n=== {sid}: {title} ===", flush=True)
        rec = {"scenario": sid, "title": title}
        try:
            async with LiveBench(sid, tenant_prompt) as b:
                rec.update(await fn(b))
                # Transcript-based cross-check for every labelled caller turn.
                rec["reply_ms_by_turn"] = {
                    m["label"]: {"audio": b.reply_latency_ms(m["label"]),
                                 "transcript": b.reply_latency_transcript_ms(m["label"])}
                    for m in b.caller_marks if m["end"] is not None
                }
                rec.update({
                    "assistant_lines": b.transcript.assistant_lines,
                    "caller_lines": b.transcript.caller_lines,
                    "non_hebrew_assistant_turns": b.transcript.assistant_non_hebrew_turns(),
                    "delegations": b.delegations, "errors": b.errors,
                    "usage_seconds": b.usage_seconds,
                    "session_seconds": round(b.now(), 1),
                    "voiced_output_seconds": round(len(b.out_audio_times) * 0.1, 1),
                    "delegation_mode": poc.LIVE_POC_DELEGATION,
                    "timeline": [e for e in b.events if e["type"] != "session.output_audio.delta"
                                 or e.get("voiced")][:400],
                })
        except Exception as exc:
            rec["exception"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        results.append(rec)

    out = ROOT / "scripts" / f"live_scenario_results_{poc.LIVE_POC_DELEGATION}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    print("\n=== summary ===")
    for r in results:
        keys = [k for k in ("reply_ms", "stop_after_ms", "opens_with_filler", "says_lidor",
                            "reply_is_hebrew", "closing_phrases_total",
                            "poc_would_have_hung_up_during_objection", "non_hebrew_assistant_turns",
                            "delegations", "usage_seconds", "exception") if k in r]
        print(f"{r['scenario']:>4} {r['title']:<36} " + "  ".join(f"{k}={r[k]}" for k in keys))


if __name__ == "__main__":
    asyncio.run(main())

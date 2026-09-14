"""
GPT-Live 1 POC — isolated Twilio ↔ OpenAI Live API bridge.

STATUS: experiment. Not reachable by production numbers. Two independent gates,
both closed by default:

  LIVE_POC_ENABLED             "true" to expose the endpoints at all
  LIVE_POC_ALLOWED_TO_NUMBERS  CSV of E.164 numbers this POC may answer.
                               Empty = refuses every call, even with the flag on.

Roi's production line keeps its own webhook (/voice-ai/voice-gemini →
/voice-ai/stream-openai, gpt-realtime-2.1). Nothing here is on that path. The
only production-file touch is one additive include_router in main.py.
Rollback = remove the two env vars (or the include_router line).

WHY A SEPARATE FILE AND NOT A MODEL SWAP
GPT-Live is a different API (wss://api.openai.com/v1/live/sessions), a
different event vocabulary, and — the part that matters — a different
division of labour: the model owns turn-taking, VAD, barge-in and
backchannels, and delegates reasoning to a backend model. Verified by live
probe on this account (2026-09-13): `session.turn_detection` → error
`unknown_parameter`; there is no `create_response:false`, no `response.cancel`,
no `speech_started/stopped`, no output-audio-done, no truncate. So the
production TurnController, onset-barge energy guard, greeting-protection gate,
valid-turn gate and mark-based response accounting have nothing to attach to.
What survives is what the API leaves to the client:

  KEEP    Twilio playback flush on barge-in (the API stops emitting audio but
          cannot un-send what Twilio already buffered) — a playback clock.
  KEEP    closing-phrase detection + idle watchdog (no end-of-call signal).
  KEEP    the entire post-call pipeline: extraction, name status, summary,
          RTL transcript HTML, lead upsert, customer history, Make webhook.
  KEEP    fail-closed agent resolution via Twilio <Parameter> handoff.
  DROP    TurnController / valid-turn gate / greeting protection / onset guard /
          echo guard / response.create accounting / silence re-prompt state
          machine — the model owns all of it.
  CONFLICT anything that tries to decide WHEN the model may speak.

Audio: µ-law 8 kHz passthrough both ways (`audio/pcmu`, verified accepted and
echoed in session.started). No transcoding.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote

import websockets
from fastapi import APIRouter, Query, Request, WebSocket
from fastapi.responses import Response
from starlette.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.integrations.twilio_client import _get_client as _get_twilio_client
from app.services.agent_config import fetch_supabase_agent_config
from app.services.lead_capture import save_lead
from app.services.voice_shared import GENERIC_OFFICE_LABEL
from app.services.voice_shared import extract_lead_from_transcript as _extract_lead_from_transcript
from app.services.voice_shared import get_customer_history as _get_customer_history
from app.services.voice_shared import resolve_two_stage_office
from app.services.voice_shared import send_voice_webhook as _send_voice_webhook
from app.services.voice_shared import summarize_transcript as _summarize_transcript

# One-way reuse of pure helpers. This module is never imported by the
# production routes, so there is no cycle and no behaviour change there.
from app.routes.voice_gemini import (
    _GEMINI_CALL_CONTEXT,
    _contains_closing_phrase,
    _normalize_phone,
    _resolve_gemini_context,
)
from app.routes.voice_openai_live import (
    _EMPTY_CALLER_SUMMARY,
    _compute_appointment_at,
    _customer_transcript,
    _full_transcript,
    _has_hebrew,
    _has_valid_caller_content,
    _name_status,
    _transcript_excerpt,
    _transcript_html,
)

router = APIRouter()

_OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
_LIVE_WS_URL = "wss://api.openai.com/v1/live/sessions"


# ── Gates ────────────────────────────────────────────────────────────────────

def _truthy(raw: Optional[str]) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def _csv_set(raw: Optional[str]) -> set[str]:
    return {c.strip() for c in (raw or "").split(",") if c.strip()}


LIVE_POC_ENABLED = _truthy(os.getenv("LIVE_POC_ENABLED"))
LIVE_POC_ALLOWED_TO_NUMBERS = _csv_set(os.getenv("LIVE_POC_ALLOWED_TO_NUMBERS"))


def live_poc_enabled() -> bool:
    return LIVE_POC_ENABLED


def live_poc_number_allowed(to_number: str) -> bool:
    """A destination number is served ONLY if explicitly allowlisted. Empty
    allowlist = nobody, so flipping the flag alone can never capture a line."""
    n = _normalize_phone(to_number or "")
    return bool(n) and n in LIVE_POC_ALLOWED_TO_NUMBERS


# ── Config ───────────────────────────────────────────────────────────────────

LIVE_POC_MODEL = os.getenv("LIVE_POC_MODEL", "gpt-live-1").strip()
LIVE_POC_VOICE = os.getenv("LIVE_POC_VOICE", "marin").strip()
# "responses" = frontend voice + backend model (the documented architecture);
# "client"    = voice model only, no backend (A/B control for backend latency).
LIVE_POC_DELEGATION = os.getenv("LIVE_POC_DELEGATION", "responses").strip().lower()
LIVE_POC_BACKEND_MODEL = os.getenv("LIVE_POC_BACKEND_MODEL", "gpt-5.6-luna").strip()
LIVE_POC_BACKEND_REASONING = os.getenv("LIVE_POC_BACKEND_REASONING", "low").strip().lower()
LIVE_POC_BACKEND_INCLUDE_TENANT_PROMPT = _truthy(
    os.getenv("LIVE_POC_BACKEND_INCLUDE_TENANT_PROMPT", "true")
)
LIVE_POC_IDLE_HANGUP_SECONDS = float(os.getenv("LIVE_POC_IDLE_HANGUP_SECONDS", "30"))
LIVE_POC_CLOSING_GRACE_SECONDS = float(os.getenv("LIVE_POC_CLOSING_GRACE_SECONDS", "2.0"))
# Do not hang up on a closing phrase if the caller spoke this recently — the
# production incident where Maya said "להתראות" mid-objection and dropped the call.
LIVE_POC_CLOSING_CALLER_QUIET_SECONDS = float(
    os.getenv("LIVE_POC_CLOSING_CALLER_QUIET_SECONDS", "2.5")
)
# After caller speech is detected during playback, wait this long for the model
# to keep talking (backchannel / it chose not to yield) before flushing Twilio.
LIVE_POC_FLUSH_GRACE_SECONDS = float(os.getenv("LIVE_POC_FLUSH_GRACE_SECONDS", "0.25"))

_VALID_REASONING = ("none", "minimal", "low", "medium", "high", "xhigh")


# ── Prompts ──────────────────────────────────────────────────────────────────
# The voice model gets a SHORT prompt: identity, language, delivery, turn-taking
# policy, delegation policy. Business rules live on the backend (per the Live
# prompting guide: "reasoning and tool use belong in backend prompts").

def build_voice_instructions(office_label: str, agent_name: str = "מאיה",
                             delegation_mode: str = "responses") -> str:
    """Short voice prompt. `delegation_mode` matters: in "client" mode the API
    still emits session.delegation.created and then WAITS for the client to
    answer — measured in the bench, the model says "שנייה, אני בודקת" and the
    call stalls. Since this POC does not answer client delegations, the client
    prompt must tell her there is no backend and she answers on her own."""
    office = (office_label or GENERIC_OFFICE_LABEL).strip()
    if delegation_mode == "client":
        delegation_policy = (
            "אין לך backend ואין למי להעביר שאלות: את עונה בעצמך, מיד, ממה שאת יודעת "
            "וממה שנאמר בשיחה. לעולם אל תגידי שאת \"בודקת\" או \"מבררת\" — אם אין לך "
            "תשובה, אמרי שרועי יחזור עם תשובה, והמשיכי לאסוף את הפרטים."
        )
    else:
        delegation_policy = (
            "מדיניות האצלה: ה-backend מכיר את כללי המשרד. "
            "האצילי ל-backend רק כשנדרשת תשובה עניינית על כללי המשרד או על תהליך שאינך יודעת. "
            "אל תאצילי כדי לרשום פרטים, לאשר שם, לשאול שאלה, או לענות ממה שכבר נאמר בשיחה. "
            "כשאת מאצילה — אמרי משפט קצר אחד בלבד בזמן ההמתנה, ואל תנחשי את התוצאה."
        )
    return (
        f"את {agent_name}, המזכירה הקולית {office}. "
        "השיחה היא שיחת טלפון נכנסת.\n\n"
        "שפה: דברי תמיד ורק בעברית ישראלית טבעית, בכל מצב וללא יוצא מן הכלל — "
        "גם אם לא הבנת, גם אם האודיו לא ברור, וגם אם נשמעה מילה בשפה אחרת. "
        "אם לא הבנת — בקשי בעברית שיחזרו. לעולם אל תעברי לאנגלית.\n\n"
        "הגשה קולית: דברי בחום ובפשטות, כמו בשיחת טלפון יומיומית עם אדם אחד. "
        "השתמשי בגוון נוח ורך, מעט נמוך בטווח הטבעי שלך, ובאינטונציה עדינה. "
        "שמרי על קצב השיחה הרגיל ועל הגייה ברורה; בלי ניגון של כרוז, "
        "בלי התלהבות שירותית מוגזמת ובלי להעמיק את הקול באופן מאולץ.\n\n"
        "סגנון: חמה, רגועה, ישירה. משפט אחד או שניים בכל תור, ואז עצרי והקשיבי. "
        "שאלה אחת בכל פעם. אל תחזרי על מה שכבר אמרת. "
        "כשהפונה שואל שאלה — עני עליה ישירות, בלי מילת פתיחה כמו \"בסדר גמור\" או \"אוקיי\". "
        "כשנמסר שם — חזרי עליו פעם אחת לאישור; אם תיקנו אותך — אמצי מיד את התיקון "
        "ואל תחזרי על הגרסה השגויה. לעולם אל תאמרי שם שהפונה לא אמר.\n\n"
        "מדיניות הקשבה: השתמשי בקולות הקשבה קצרים ומתונים (\"אהמ\", \"כן\") בלי להתחרות "
        "בדברי הפונה. כשהפונה מדבר תוך כדי שאת מדברת — עצרי מיד והקשיבי. "
        "המשיכי להקשיב כשהפונה עוצר לחשוב; אל תתייחסי לשיעול או לרעש רקע כפנייה חדשה.\n\n"
        f"{delegation_policy}\n\n"
        "סיום: אל תעברי לסיום כל עוד הפונה מדבר, מתקן, או שאל שאלה שלא נענתה. "
        "כשהשיחה הסתיימה באמת — סיימי במשפט קצר אחד עם \"להתראות\", פעם אחת בלבד."
    )


def build_backend_instructions(tenant_prompt: str, office_label: str,
                               include_tenant_prompt: bool = True) -> str:
    office = (office_label or GENERIC_OFFICE_LABEL).strip()
    head = (
        f"אתה ה-backend של מאיה, המזכירה הקולית {office}. "
        "מאיה מנהלת את השיחה בקול; אתה מספק לה את התוכן. "
        "החזר תמיד טקסט קצר בעברית שמאיה יכולה לומר כמו שהוא — משפט אחד או שניים, "
        "בלי כותרות, בלי רשימות, בלי הסברים על עצמך.\n\n"
        "מה לאסוף לאורך השיחה: שם הפונה, מספר לחזרה (אם שונה מהמספר שממנו התקשר), "
        "וסיבת הפנייה. שאלה אחת בכל פעם. שם שואלים רק אחרי שהבנת את סיבת הפנייה.\n\n"
        "כללים: תיקון של הפונה תמיד גובר על מה שנאמר קודם. נושא שהפונה שלל במפורש — "
        "לא קיים. אל תמציא פרטים, שמות, מחירים או זמנים שלא נאמרו או שאינם בכללי המשרד. "
        "אם אין תשובה בכללים — אמור שרועי יחזור עם תשובה.\n"
    )
    if include_tenant_prompt and (tenant_prompt or "").strip():
        return head + "\n━━ כללי המשרד ━━\n" + tenant_prompt.strip()
    return head


def build_greeting_line(first_message: str, office_label: str) -> str:
    fm = (first_message or "").strip()
    if fm:
        return fm
    office = (office_label or GENERIC_OFFICE_LABEL).strip()
    return f"היי, מדברת מאיה {office}. איך אפשר לעזור?"


def build_session_start(voice_instructions: str, backend_instructions: str,
                        model: str = None, voice: str = None,
                        delegation: str = None, backend_model: str = None,
                        backend_reasoning: str = None) -> dict:
    """Pure/testable. The exact `session.start` payload. Strict config — every
    field here was verified accepted by live probe; nothing else may be added
    without re-probing (unknown fields are rejected and kill the session)."""
    model = model or LIVE_POC_MODEL
    voice = voice or LIVE_POC_VOICE
    delegation = (delegation or LIVE_POC_DELEGATION)
    backend_model = backend_model or LIVE_POC_BACKEND_MODEL
    reasoning = backend_reasoning or LIVE_POC_BACKEND_REASONING
    if reasoning not in _VALID_REASONING:
        reasoning = "low"

    session = {
        "model": model,
        "instructions": voice_instructions,
        "audio": {
            "format": {"type": "audio/pcmu", "rate": 8000},
            "output": {"voice": voice},
        },
    }
    if delegation == "responses":
        session["delegation"] = {
            "type": "responses",
            "responses": {
                "model": backend_model,
                "instructions": backend_instructions,
                "reasoning": {"effort": reasoning},
                "tool_choice": "none",
            },
        }
    else:
        session["delegation"] = {"type": "client"}
    return {"type": "session.start", "event_id": "start", "session": session}


# ── Pure state helpers (tested) ──────────────────────────────────────────────

class PlaybackClock:
    """Tracks how far ahead of real time we have pushed µ-law audio to Twilio.
    Twilio plays 8000 bytes/second; we hand it bursts. `play_until` is the wall
    time at which the last byte we sent will have been heard."""

    BYTES_PER_SECOND = 8000.0

    def __init__(self):
        self.play_until = 0.0
        self.bytes_sent = 0

    def on_sent(self, now: float, n_bytes: int) -> None:
        base = max(now, self.play_until)
        self.play_until = base + n_bytes / self.BYTES_PER_SECOND
        self.bytes_sent += n_bytes

    def is_playing(self, now: float) -> bool:
        return now < self.play_until

    def buffered_seconds(self, now: float) -> float:
        return max(0.0, self.play_until - now)

    def flush(self, now: float) -> float:
        """Returns how many seconds of unheard audio were discarded."""
        dropped = self.buffered_seconds(now)
        self.play_until = now
        return dropped


def should_flush_playback(now: float, caller_speech_at: float,
                          last_output_delta_at: float, is_playing: bool,
                          grace_s: float) -> bool:
    """Barge-in decision. The model stops emitting audio when it yields, but
    Twilio already holds what we sent. Flush only when (a) there is unheard
    audio and (b) the model has NOT produced new audio since the caller began —
    for at least `grace_s`. If it kept talking (backchannel, or it chose not to
    yield), leave the buffer alone."""
    if not is_playing:
        return False
    if last_output_delta_at > caller_speech_at:
        return False          # model kept talking after the caller started
    return (now - caller_speech_at) >= grace_s


def should_close_on_closing_phrase(assistant_tail: str, now: float,
                                   last_caller_speech_at: float,
                                   last_output_delta_at: float,
                                   caller_quiet_s: float,
                                   output_settle_s: float = 1.0) -> bool:
    """Hang up on a closing phrase only when the caller has been quiet and the
    model has finished emitting. Prevents the mid-objection hangup."""
    if not _contains_closing_phrase(assistant_tail or ""):
        return False
    if (now - last_caller_speech_at) < caller_quiet_s:
        return False
    return (now - last_output_delta_at) >= output_settle_s


class TranscriptAccumulator:
    """Turns Live's cadence-based transcript fragments into chronological turns.
    Consecutive fragments of one role merge into one turn; a role change opens
    a new turn. Overlap is expected (full duplex) — we order by arrival."""

    def __init__(self):
        self.turns: list[dict] = []     # {"role": "לקוח"|"מאיה", "text": str}

    def _append(self, role: str, delta: str) -> None:
        d = delta or ""
        if not d:
            return
        if self.turns and self.turns[-1]["role"] == role:
            self.turns[-1]["text"] += d
        else:
            self.turns.append({"role": role, "text": d})

    def caller(self, delta: str) -> None:
        self._append("לקוח", delta)

    def assistant(self, delta: str) -> None:
        self._append("מאיה", delta)

    @property
    def caller_lines(self) -> list[str]:
        return [t["text"].strip() for t in self.turns if t["role"] == "לקוח" and t["text"].strip()]

    @property
    def assistant_lines(self) -> list[str]:
        return [t["text"].strip() for t in self.turns if t["role"] == "מאיה" and t["text"].strip()]

    def assistant_tail(self, chars: int = 60) -> str:
        for t in reversed(self.turns):
            if t["role"] == "מאיה":
                return t["text"][-chars:]
        return ""

    def assistant_non_hebrew_turns(self) -> int:
        """Language check for the A/B report: assistant turns with letters but
        no Hebrew at all."""
        n = 0
        for t in self.turns:
            if t["role"] != "מאיה":
                continue
            txt = t["text"]
            if any(ch.isalpha() for ch in txt) and not _has_hebrew(txt):
                n += 1
        return n


def _diag(event: str, call_sid: str, **kw) -> None:
    rec = {"event": event, "call_sid": call_sid, "t": round(time.monotonic(), 3)}
    rec.update(kw)
    print(f"[LIVE-DIAG] {json.dumps(rec, ensure_ascii=False)}")


# ── Twilio entry (TwiML) ─────────────────────────────────────────────────────

def _refuse_twiml(reason: str) -> Response:
    print(f"[LIVE-POC] ❌ refused — {reason}")
    r = VoiceResponse()
    r.say("מצטערים, אירעה שגיאה. נסו שוב מאוחר יותר.", language="he-IL")
    return Response(content=str(r), media_type="application/xml")


@router.post("/voice-live")
async def voice_live_entry(request: Request):
    """Twilio webhook for the POC ONLY. Point a TEST number here. Both gates
    must pass; production numbers are refused unless explicitly allowlisted."""
    if not live_poc_enabled():
        return _refuse_twiml("LIVE_POC_ENABLED is off")

    form = await request.form()
    norm_to = _normalize_phone(form.get("To", ""))
    norm_from = _normalize_phone(form.get("From", ""))
    call_sid = form.get("CallSid", "")
    print(f"[LIVE-POC] call_sid={call_sid} to={norm_to} from={norm_from}")

    if not live_poc_number_allowed(norm_to):
        return _refuse_twiml(f"to={norm_to} is not in LIVE_POC_ALLOWED_TO_NUMBERS")

    agent_cfg = await fetch_supabase_agent_config(norm_to)
    print(
        f"[ROUTE-AUDIT] route=voice_live_entry to={norm_to} "
        f"resolved_agent_id={agent_cfg.get('agent_id')} "
        f"resolved_client_id={agent_cfg.get('client_id')} "
        f"fallback_used={bool(agent_cfg.get('fallback_used'))}"
    )
    if agent_cfg.get("fallback_used") or not agent_cfg.get("prompt_override"):
        return _refuse_twiml(f"no active agent for {norm_to} (fail closed)")

    _GEMINI_CALL_CONTEXT[call_sid] = {
        "to": norm_to, "from": norm_from, "agent_cfg": agent_cfg,
        "created_at": datetime.now().timestamp(),
    }

    host = request.url.hostname
    stream_url = f"wss://{host}/voice-ai/stream-live?call_sid={quote(call_sid, safe='')}"
    print(f"[LIVE-POC] stream_url={stream_url}")

    resp = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=stream_url,
                            status_callback=f"https://{host}/voice-ai/stream-status",
                            status_callback_method="POST")
    stream.parameter(name="call_sid", value=call_sid)
    stream.parameter(name="client_id", value=str(agent_cfg.get("client_id") or ""))
    stream.parameter(name="caller_phone", value=norm_from)
    resp.append(connect)
    return Response(content=str(resp), media_type="application/xml")


# ── WebSocket bridge ─────────────────────────────────────────────────────────

@router.websocket("/stream-live")
async def stream_live(twilio_ws: WebSocket, call_sid: str = Query(default="")):
    await twilio_ws.accept()
    if not live_poc_enabled():
        print("[LIVE-WS] ❌ LIVE_POC_ENABLED is off — closing")
        await twilio_ws.close()
        return
    if not _OPENAI_API_KEY:
        print("[LIVE-WS] ERROR: OPENAI_API_KEY not set — closing")
        await twilio_ws.close()
        return

    _call_started_at = datetime.utcnow().isoformat()
    _t_entry = time.monotonic()
    print(f"[LIVE-WS] Twilio connection accepted — call_sid={call_sid!r}")

    # ── Twilio start event → durable agent resolution ─────────────────────────
    stream_sid: Optional[str] = None
    agent_cfg: dict = {}
    caller_phone = ""
    client_id = None
    client_name = ""
    webhook_url = ""
    try:
        async for raw in twilio_ws.iter_text():
            evt = json.loads(raw)
            if evt.get("event") == "start":
                stream_sid = evt["start"]["streamSid"]
                custom = evt["start"].get("customParameters", {}) or {}
                if not call_sid:
                    call_sid = custom.get("call_sid") or evt["start"].get("callSid", "")
                _diag("setup_media_start", call_sid,
                      entry_to_start_ms=round((time.monotonic() - _t_entry) * 1000))
                resolved = await _resolve_gemini_context(custom, call_sid)
                agent_cfg = resolved["agent_cfg"]
                caller_phone = resolved["caller_phone"]
                client_id = resolved["client_id"]
                client_name = resolved["client_name"]
                webhook_url = agent_cfg.get("webhook_url", "")
                _diag("setup_context_fetched", call_sid, source=resolved["source"])
                break
    except Exception as exc:  # noqa: BLE001
        print(f"[LIVE-WS] ERROR waiting for start event: {exc}")
        await twilio_ws.close()
        return

    if agent_cfg.get("fallback_used") or not agent_cfg.get("prompt_override"):
        print(f"[LIVE-WS] ❌ No active agent prompt for client='{client_name}' — closing (fail closed)")
        await twilio_ws.close()
        return

    office = resolve_two_stage_office(agent_cfg)
    tenant_prompt = agent_cfg["prompt_override"].replace("{{caller_phone}}", caller_phone)
    voice_instr = build_voice_instructions(office, delegation_mode=LIVE_POC_DELEGATION)
    backend_instr = build_backend_instructions(
        tenant_prompt, office, LIVE_POC_BACKEND_INCLUDE_TENANT_PROMPT
    )
    greeting = build_greeting_line(agent_cfg.get("first_message") or "", office)
    print(f"[LIVE-WS] office={office!r} delegation={LIVE_POC_DELEGATION} "
          f"backend={LIVE_POC_BACKEND_MODEL if LIVE_POC_DELEGATION == 'responses' else '-'} "
          f"voice_prompt_chars={len(voice_instr)} backend_prompt_chars={len(backend_instr)}")

    # ── Per-call state ────────────────────────────────────────────────────────
    transcript = TranscriptAccumulator()
    clock = PlaybackClock()
    live_session_id = ""
    live_started = asyncio.Event()
    closing_requested = False
    closed_reason = ""
    closed_usage_seconds: Optional[float] = None
    exit_reason = "unknown"
    first_outbound_logged = False

    last_caller_speech_at = 0.0
    last_output_delta_at = 0.0
    awaiting_reply_since = 0.0      # caller spoke, no audio yet → latency metric
    assistant_turns_completed = 0
    flush_task: Optional[asyncio.Task] = None
    reply_latencies_ms: list[int] = []
    flush_count = 0
    delegation_count = 0

    async def twilio_send(obj: dict) -> None:
        await twilio_ws.send_text(json.dumps(obj))

    async def flush_twilio(reason: str) -> None:
        nonlocal flush_count
        now = time.monotonic()
        dropped = clock.flush(now)
        flush_count += 1
        try:
            await twilio_send({"event": "clear", "streamSid": stream_sid})
        except Exception:  # noqa: BLE001
            pass
        _diag("barge_flush", call_sid, reason=reason, dropped_s=round(dropped, 2))

    async def _flush_after_grace(caller_at: float) -> None:
        await asyncio.sleep(LIVE_POC_FLUSH_GRACE_SECONDS)
        now = time.monotonic()
        if should_flush_playback(now, caller_at, last_output_delta_at,
                                 clock.is_playing(now), LIVE_POC_FLUSH_GRACE_SECONDS):
            await flush_twilio("caller_speech_while_playing")

    # ── Connect to GPT-Live ───────────────────────────────────────────────────
    t_connect = time.monotonic()
    try:
        live_ws = await websockets.connect(
            _LIVE_WS_URL,
            additional_headers={"Authorization": f"Bearer {_OPENAI_API_KEY}"},
            max_size=None,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[LIVE-WS] ❌ could not connect to Live API: {exc}")
        await twilio_ws.close()
        return
    _diag("live_connected", call_sid, connect_ms=round((time.monotonic() - t_connect) * 1000))

    async def live_send(obj: dict) -> None:
        await live_ws.send(json.dumps(obj, ensure_ascii=False))

    async def request_close(reason: str) -> None:
        nonlocal closing_requested
        if closing_requested:
            return
        closing_requested = True
        _diag("close_requested", call_sid, reason=reason)
        try:
            await live_send({"type": "session.close", "event_id": "close"})
        except Exception:  # noqa: BLE001
            pass

    # ── Twilio → Live pump ────────────────────────────────────────────────────
    async def pump_twilio() -> str:
        try:
            async for raw in twilio_ws.iter_text():
                evt = json.loads(raw)
                ev = evt.get("event")
                if ev == "media":
                    if not live_started.is_set():
                        continue        # pre-session audio is line noise/ringback
                    await live_send({"type": "session.input_audio.append",
                                     "audio": evt["media"]["payload"]})
                elif ev == "mark":
                    pass                # not used by this bridge
                elif ev == "stop":
                    return "twilio_stop"
        except WebSocketDisconnect:
            return "twilio_disconnect"
        except Exception as exc:  # noqa: BLE001
            print(f"[LIVE-WS] twilio pump error: {exc}")
            return "twilio_error"
        return "twilio_iter_ended"

    # ── Live → Twilio loop ────────────────────────────────────────────────────
    async def pump_live() -> str:
        nonlocal live_session_id, closed_reason, closed_usage_seconds
        nonlocal last_caller_speech_at, last_output_delta_at, awaiting_reply_since
        nonlocal assistant_turns_completed, flush_task, first_outbound_logged
        nonlocal delegation_count
        try:
            async for raw in live_ws:
                ev = json.loads(raw)
                t = ev.get("type", "")
                now = time.monotonic()

                if t == "session.started":
                    s = ev.get("session", {})
                    live_session_id = s.get("id", "")
                    _diag("session_started", call_sid, live_session_id=live_session_id,
                          since_entry_ms=round((now - _t_entry) * 1000),
                          expires_at=s.get("expires_at"),
                          audio=s.get("audio"), delegation_type=(s.get("delegation") or {}).get("type"))
                    live_started.set()
                    # Scripted opening — same line production uses (M6 fallback).
                    await live_send({"type": "session.instructions.append", "event_id": "greet",
                                     "delegation_id": None,
                                     "content": ("פתחי עכשיו את השיחה, בעברית, במשפט הבא בדיוק "
                                                 f"ובלי שום תוספת: \"{greeting}\"")})
                    _diag("greeting_sent", call_sid)

                elif t == "session.output_audio.delta":
                    b64 = ev.get("delta", "")
                    n = len(base64.b64decode(b64)) if b64 else 0
                    if n:
                        await twilio_send({"event": "media", "streamSid": stream_sid,
                                           "media": {"payload": b64}})
                        clock.on_sent(now, n)
                        if awaiting_reply_since:
                            lat = round((now - awaiting_reply_since) * 1000)
                            reply_latencies_ms.append(lat)
                            _diag("reply_latency", call_sid, ms=lat,
                                  note="from last caller transcript fragment to first audio")
                            awaiting_reply_since = 0.0
                        if not first_outbound_logged:
                            first_outbound_logged = True
                            _diag("first_outbound_audio", call_sid,
                                  since_entry_ms=round((now - _t_entry) * 1000))
                    last_output_delta_at = now

                elif t == "session.output_transcript.delta":
                    d = ev.get("delta", "")
                    transcript.assistant(d)
                    _diag("assistant_transcript", call_sid, delta=d,
                          start_ms=ev.get("start_ms"), end_ms=ev.get("end_ms"))

                elif t == "session.input_transcript.delta":
                    d = ev.get("delta", "")
                    transcript.caller(d)
                    _diag("caller_transcript", call_sid, delta=d,
                          start_ms=ev.get("start_ms"), end_ms=ev.get("end_ms"))
                    if (d or "").strip():
                        last_caller_speech_at = now
                        awaiting_reply_since = now
                        if clock.is_playing(now):
                            if flush_task is None or flush_task.done():
                                flush_task = asyncio.create_task(_flush_after_grace(now))

                elif t == "session.delegation.created":
                    delegation_count += 1
                    d = ev.get("delegation", {}) or {}
                    _diag("delegation_created", call_sid, id=d.get("id"),
                          target=d.get("target"), offset_ms=ev.get("offset_ms"))

                elif t == "response.event":
                    inner = (ev.get("event") or {}).get("type", "")
                    if inner in ("response.created", "response.completed", "response.failed",
                                 "response.incomplete"):
                        _diag("backend_event", call_sid, inner=inner,
                              delegation_id=ev.get("delegation_id"))

                elif t == "session.usage.updated":
                    _diag("usage", call_sid, seconds=(ev.get("usage") or {}).get("seconds"),
                          context_ratio=(ev.get("context_window") or {}).get("usage_ratio"))

                elif t == "error":
                    _diag("live_error", call_sid, error=ev.get("error"))

                elif t == "session.closed":
                    closed_reason = ev.get("reason", "")
                    closed_usage_seconds = (ev.get("usage") or {}).get("seconds")
                    _diag("session_closed", call_sid, reason=closed_reason,
                          usage_seconds=closed_usage_seconds)
                    return "live_closed"

                elif t in ("session.instructions.appended", "session.commentary.appended",
                           "session.thinking.appended", "session.updated"):
                    pass
        except websockets.ConnectionClosed as exc:
            return f"live_ws_closed:{exc.rcvd.code if exc.rcvd else '?'}"
        except Exception as exc:  # noqa: BLE001
            print(f"[LIVE-WS] live pump error: {exc}")
            return "live_error"
        return "live_iter_ended"

    # ── Watchdog: closing phrase + idle ───────────────────────────────────────
    async def watchdog() -> None:
        nonlocal assistant_turns_completed
        settled_tail = ""
        while True:
            await asyncio.sleep(0.5)
            now = time.monotonic()
            if closing_requested:
                continue
            tail = transcript.assistant_tail()
            # Count a completed assistant turn once output has settled.
            if tail and tail != settled_tail and (now - last_output_delta_at) >= 1.0 \
                    and last_output_delta_at > 0:
                settled_tail = tail
                assistant_turns_completed += 1
            if should_close_on_closing_phrase(tail, now, last_caller_speech_at,
                                              last_output_delta_at,
                                              LIVE_POC_CLOSING_CALLER_QUIET_SECONDS):
                _diag("closing_detected", call_sid, tail=tail[-40:])
                await asyncio.sleep(LIVE_POC_CLOSING_GRACE_SECONDS)
                await request_close("closing_phrase")
                return
            last_activity = max(last_caller_speech_at, last_output_delta_at)
            if assistant_turns_completed >= 1 and last_activity > 0 \
                    and (now - last_activity) >= LIVE_POC_IDLE_HANGUP_SECONDS:
                _diag("idle_hangup", call_sid, idle_s=round(now - last_activity, 1))
                await request_close("idle")
                return

    watchdog_task = asyncio.create_task(watchdog())
    live_task = asyncio.create_task(pump_live())
    twilio_task = asyncio.create_task(pump_twilio())

    try:
        await live_send(build_session_start(voice_instr, backend_instr))
        done, _ = await asyncio.wait({live_task, twilio_task},
                                     return_when=asyncio.FIRST_COMPLETED)
        for d in done:
            exit_reason = d.result() if not d.cancelled() else "cancelled"
        # If Twilio ended first, ask Live to close and wait briefly for session.closed.
        if twilio_task in done and not live_task.done():
            await request_close(exit_reason)
            try:
                await asyncio.wait_for(live_task, timeout=6.0)
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        print(f"[LIVE-WS] bridge error: {exc}")
        exit_reason = "bridge_error"
    finally:
        for task in (watchdog_task, live_task, twilio_task, flush_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

        caller_lines = transcript.caller_lines
        assistant_lines = transcript.assistant_lines
        _diag("session_ended", call_sid, exit_reason=exit_reason,
              caller_lines=len(caller_lines), assistant_lines=len(assistant_lines),
              assistant_non_hebrew_turns=transcript.assistant_non_hebrew_turns(),
              reply_latencies_ms=reply_latencies_ms, flushes=flush_count,
              delegations=delegation_count, live_usage_seconds=closed_usage_seconds,
              closed_reason=closed_reason)
        print("[LIVE-WS] Session ended — running end-of-call business logic")

        # ── Post-call pipeline: identical contract to the production path ──
        extracted: dict = {}
        transcript_text = _customer_transcript(caller_lines)
        if transcript_text.strip():
            extracted = await _extract_lead_from_transcript(transcript_text, caller_phone)
            print(f"[LIVE-EXTRACT] Result: {extracted}")
        else:
            print("[LIVE-EXTRACT] No customer transcript captured — skipping extraction")

        email_name, name_stat = _name_status(extracted.get("name"), caller_lines)
        print(f"[LIVE-NAME] status={name_stat} email_name={email_name!r}")

        confirmed_name = extracted.get("name") if name_stat == "confirmed" else None
        allowed_names = [confirmed_name] if confirmed_name else []
        full_text = _full_transcript(caller_lines, assistant_lines)
        excerpt = _transcript_excerpt(caller_lines, assistant_lines)
        transcript_html_value = _transcript_html(transcript.turns)
        if _has_valid_caller_content(caller_lines):
            summary = await _summarize_transcript(full_text, caller_names_allowed=allowed_names)
        else:
            summary = _EMPTY_CALLER_SUMMARY
        print(f"[LIVE-SUMMARY] {(summary or '(empty)')[:200]}")

        appt_day = extracted.get("appointment_day") or ""
        appt_time = extracted.get("appointment_time") or ""
        appointment_at = _compute_appointment_at(appt_day, appt_time)
        if caller_phone:
            topic = extracted.get("topic") or None
            notes = extracted.get("notes") or None
            parts = []
            if topic:
                parts.append(f"נושא: {topic}")
            if notes:
                parts.append(f"פרטים: {notes}")
            await save_lead({
                "phone": caller_phone, "source": "voice", "status": "new",
                "client_id": client_id, "name": extracted.get("name") or None,
                "notes": notes,
                "last_call_summary": summary or (" | ".join(parts) or None),
                "last_call_topic": topic,
                "last_call_at": datetime.utcnow().isoformat(),
                "appointment_at": appointment_at,
            })
            print(f"[LIVE-LEAD] ✅ Lead upserted — phone={caller_phone} name={extracted.get('name')}")

        if caller_phone and webhook_url:
            history = await _get_customer_history(caller_phone, _call_started_at, agent_cfg.get("agent_id"))
            payload = {
                "timestamp": datetime.now().isoformat(),
                "source": "voice_live",
                "client": client_name,
                "caller_phone": caller_phone,
                "call_sid": call_sid,
                "name": email_name,
                "name_status": name_stat,
                "phone_number": extracted.get("phone_number") or caller_phone,
                "topic": extracted.get("topic", ""),
                "notes": extracted.get("notes", ""),
                "summary": summary,
                "transcript_excerpt": excerpt,
                "transcript_html": transcript_html_value,
                "appointment_day": appt_day,
                "appointment_time": appt_time,
                "appointment_at": appointment_at or "",
                "booking_status": "booked" if appointment_at else "not_booked",
                "followup_target_phone": caller_phone,
                "customer_status": history["customer_status"],
                "prior_count": history["prior_count"],
                "last_date": history["last_date"] or "",
            }
            await _send_voice_webhook(webhook_url, payload)

        if call_sid:
            try:
                tw = _get_twilio_client()
                await asyncio.to_thread(lambda: tw.calls(call_sid).update(status="completed"))
                print(f"[LIVE-HANGUP] ✅ Twilio call {call_sid} terminated via REST API")
            except Exception as exc:  # noqa: BLE001
                print(f"[LIVE-HANGUP] ⚠️  Could not terminate call via REST: {exc}")

        _GEMINI_CALL_CONTEXT.pop(call_sid, None)
        for closer in (live_ws.close, twilio_ws.close):
            try:
                await closer()
            except Exception:  # noqa: BLE001
                pass

"""
Shared helpers for voice endpoints (Gemini Twilio + browser).
Extracted from voice_gemini.py to avoid duplication.
"""

import json
import os
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

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


# \u2500\u2500 Customer history (new vs existing) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def _customer_history_params(phone: str, before_iso: str, agent_id: str = None) -> dict:
    """Build the call_logs query params. Pure/testable.

    Scopes the lookup to a single tenant via agent_id when provided, so a caller
    who phoned another tenant is never counted as this tenant's existing
    customer. agent_id absent/blank ⇒ phone-only (backward compatible)."""
    params = {
        "phone_number": f"eq.{phone}",
        "created_at":   f"lt.{before_iso}",
        "select":       "created_at",
        "order":        "created_at.desc",
    }
    aid = (agent_id or "").strip()
    if aid:
        params["agent_id"] = f"eq.{aid}"
    return params


async def get_customer_history(phone: str, before_iso: str, agent_id: str = None) -> dict:
    """
    Look up prior call history for a caller phone, EXCLUDING the current call.

    `before_iso` must be a timestamp captured at the START of the current call;
    call_logs rows with created_at < before_iso are treated as prior interactions
    (the current call's call_logs row is written at end-of-call, so it is excluded).

    `agent_id` scopes the lookup to the current tenant (call_logs has one agent
    per row). When provided, a caller who phoned a DIFFERENT tenant is not
    counted here; omit it only for legacy/phone-only behavior.

    Returns {customer_status, prior_count, last_date}. Never raises \u2014 on any
    error or no history, returns the "new customer" default.
    """
    default = {"customer_status": "\u05dc\u05e7\u05d5\u05d7 \u05d7\u05d3\u05e9", "prior_count": 0, "last_date": None}
    if not phone or not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        return default
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/call_logs",
                params=_customer_history_params(phone, before_iso, agent_id),
                headers={
                    "apikey":        _SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except Exception as exc:
        print(f"[CUST-HISTORY] lookup failed for phone={phone}: {exc}")
        return default

    if not rows:
        return default

    last_iso  = rows[0].get("created_at")
    last_date = None
    if last_iso:
        try:
            last_date = datetime.fromisoformat(last_iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except Exception:
            last_date = last_iso[:10]

    return {"customer_status": "\u05dc\u05e7\u05d5\u05d7 \u05e7\u05d9\u05d9\u05dd", "prior_count": len(rows), "last_date": last_date}


# \u2500\u2500 Caller-name sanitizer (never store empty / the assistant's own name) \u2500\u2500\u2500\u2500\u2500\u2500

_NAME_UNKNOWN = "\u05dc\u05d0 \u05e0\u05de\u05e1\u05e8"
_ASSISTANT_NAME_TOKENS = {"\u05de\u05d0\u05d9\u05d4", "maya"}


def clean_caller_name(name, assistant_name: str = "") -> str:
    """
    Return a safe caller name for the lead record / email.

    - Empty / whitespace / None -> "\u05dc\u05d0 \u05e0\u05de\u05e1\u05e8" (never blank).
    - The assistant's own name  -> "\u05dc\u05d0 \u05e0\u05de\u05e1\u05e8" (never store Maya as the caller):
      matches "\u05de\u05d0\u05d9\u05d4"/"Maya", the configured assistant_name, or its first token,
      case-insensitively.
    Otherwise returns the trimmed name unchanged.
    """
    n = (name or "").strip()
    if not n:
        return _NAME_UNKNOWN
    deny = set(_ASSISTANT_NAME_TOKENS)
    a = (assistant_name or "").strip().lower()
    if a:
        deny.add(a)
        deny.add(a.split()[0])
    if n.lower() in deny:
        return _NAME_UNKNOWN
    return n

# ── OpenAI Realtime A/B gate (Milestone 1) ───────────────────────────────────
# Lives here (not in a route module) so voice_gemini can read it without a
# circular import: voice_gemini → voice_shared ← voice_openai_live.
# Default OFF; tenant-scoped via a client_id allowlist (Roi only, for now).

OPENAI_REALTIME_AB_ENABLED = (
    os.getenv("OPENAI_REALTIME_AB_ENABLED", "false").strip().lower()
    in ("1", "true", "yes", "on")
)
OPENAI_REALTIME_CLIENT_IDS = {
    _c.strip() for _c in os.getenv("OPENAI_REALTIME_CLIENT_IDS", "").split(",") if _c.strip()
}


def openai_ab_enabled(client_id: str) -> bool:
    """OpenAI Realtime A/B is on only when globally enabled AND this call's
    client_id is allowlisted. Empty allowlist = off for all tenants."""
    return (
        OPENAI_REALTIME_AB_ENABLED
        and bool(client_id)
        and client_id in OPENAI_REALTIME_CLIENT_IDS
    )


# ── Two-stage phone greeting gate (M6) ───────────────────────────────────────
# Roi-only, client-scoped like the A/B gate above (NOT a global boolean) so a
# future OpenAI-enabled tenant never inherits Roi's "הלו?" → identity greeting.
# Empty allowlist = off for everyone → merging changes nothing in production.
OPENAI_TWO_STAGE_GREETING_CLIENT_IDS = {
    _c.strip() for _c in os.getenv("OPENAI_TWO_STAGE_GREETING_CLIENT_IDS", "").split(",") if _c.strip()
}


def two_stage_greeting_enabled(client_id: str) -> bool:
    """The two-stage phone greeting is on ONLY for allowlisted client_ids.
    Empty allowlist = off for all tenants (no behavior change on merge)."""
    return bool(client_id) and client_id in OPENAI_TWO_STAGE_GREETING_CLIENT_IDS


# ── Onset-based interruption (barge-in) gate (Phase: barge-in) ────────────────
# Tenant-scoped like the A/B and two-stage gates (NOT a global boolean): a client
# runs the fast speech-onset barge-in path only if allowlisted; everyone else
# stays on the legacy transcription-gated interruption. Empty allowlist = off for
# every tenant → removing all ids instantly restores the legacy path on restart.
OPENAI_ONSET_BARGE_CLIENT_IDS = {
    _c.strip() for _c in os.getenv("OPENAI_ONSET_BARGE_CLIENT_IDS", "").split(",") if _c.strip()
}


def onset_barge_enabled(client_id: str) -> bool:
    """Onset (speech-onset) barge-in is on ONLY for allowlisted client_ids.
    Empty allowlist = off for all tenants (legacy transcription-gated path)."""
    return bool(client_id) and client_id in OPENAI_ONSET_BARGE_CLIENT_IDS


# ── Two-stage greeting: spoken office identity (M6.1) ─────────────────────────
# The Stage-2 self-introduction must name the CURRENT tenant's office — never a
# hardcoded one, and never maintained in Railway. Identity is a tenant-level
# value in agents_config. Resolution order (first non-empty wins):
#   1. agents_config.voice_office_label — a dedicated nullable field holding the
#      VERBATIM spoken office phrase (e.g. "מהמשרד של רועי"). Read only here, so
#      it affects nothing else (prompt/email/dashboard/WhatsApp untouched).
#   2. "מהמשרד של " + agents_config.business_name — derived from the tenant row.
#   3. GENERIC_OFFICE_LABEL — a safe, name-free fallback.
GENERIC_OFFICE_LABEL = "מהמשרד"


def resolve_two_stage_office(agent_cfg: dict = None) -> str:
    """Spoken office phrase for the Stage-2 self-introduction (see order above).
    Pure/testable; returns GENERIC_OFFICE_LABEL when nothing is configured."""
    cfg = agent_cfg or {}
    label = (cfg.get("voice_office_label") or "").strip()
    if label:
        return label
    business = (cfg.get("business_name") or "").strip()
    if business:
        return f"מהמשרד של {business}"
    return GENERIC_OFFICE_LABEL


# ── Webhook delivery ─────────────────────────────────────────────────────────

async def send_voice_webhook(webhook_url: str, payload: dict) -> None:
    """POST payload to webhook URL. Never raises — errors are logged only."""
    if not webhook_url:
        print("[VOICE-WEBHOOK] No webhook URL configured — skipping")
        return
    print(f"[VOICE-WEBHOOK] POST {webhook_url}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            print(f"[VOICE-WEBHOOK] HTTP {resp.status_code}")
            resp.raise_for_status()
    except Exception as exc:
        print(f"[VOICE-WEBHOOK] delivery failed: {exc}")


# ── Post-call summary (M1.1) ─────────────────────────────────────────────────

_SUMMARY_PROMPT = """\
כתוב סיכום קצר בעברית — 2 עד 3 משפטים — של שיחת טלפון בין לקוח לפקידת קבלה של סוכנות ביטוח.
כללים:
- התייחס למה שהלקוח ביקש במילים שלו, ומה סוכם או מה הצעד הבא.
- אל תמציא פרטים שלא נאמרו. אל תסיק שם אם לא נמסר במפורש על ידי הלקוח.
- שורות "לקוח:" הן דברי הלקוח; שורות "מאיה:" הן דברי הפקידה.
- אם שם פרטי מופיע רק בדברי מאיה ולא בשורות הלקוח — אל תשתמש בו; כנה את המתקשר "הלקוח".
- אם אין שורות "לקוח:" — לעולם אל תסיק בקשה ואל תחזיר דו-שיח. כתוב שלא התקבל מהלקוח תוכן ברור.
{allowed_names}- החזר את הסיכום בלבד, ללא כותרות וללא טקסט נוסף.

שיחה:
{transcript}
"""


def _build_summary_prompt(full_transcript: str, caller_names_allowed=None) -> str:
    """Pure builder (unit-tested). Injects the transcript and, if the caller
    genuinely provided names, the explicit allow-list. RC3 guard: the hard rule
    'a first name only in Maya's lines must not be used' is always present."""
    names = [n for n in (caller_names_allowed or []) if (n or "").strip()]
    allowed_line = (
        f"- שמות שהלקוח מסר במפורש (מותר לייחס ללקוח): {', '.join(names)}.\n"
        if names else ""
    )
    return (
        _SUMMARY_PROMPT
        .replace("{allowed_names}", allowed_line)
        .replace("{transcript}", full_transcript)
    )


async def summarize_transcript(full_transcript: str, caller_names_allowed=None) -> str:
    """
    Real 2–3 sentence Hebrew summary of the whole conversation (both speakers,
    role-tagged lines). Never raises — returns "" on any error, so callers can
    fall back to a raw transcript excerpt.

    `caller_names_allowed` (M2): names that actually appear in caller lines —
    the ONLY names the summary may attribute to the caller. A name spoken only
    by Maya (the "דניאל" confabulation, RC3) must never leak into the summary.
    """
    if not _OPENAI_API_KEY or not (full_transcript or "").strip():
        return ""
    body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": _build_summary_prompt(full_transcript, caller_names_allowed)}],
        "temperature": 0.2,
        "max_tokens": 220,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=body,
                headers={
                    "Authorization": f"Bearer {_OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        print(f"[VOICE-SUMMARY] Summarization failed: {exc}")
        return ""


# ── Lead extraction ──────────────────────────────────────────────────────────

_EXTRACT_PROMPT = """\
חלץ מהשיחה הבאה את הנתונים הבאים בפורמט JSON בלבד, ללא טקסט נוסף:

{
  "name": "שם המתקשר — רק לפי הכללים למטה, אחרת null",
  "phone_number": null,
  "topic": "נושא השיחה בקצרה",
  "notes": "פרטים חשובים (גיל, תאריך אירוע וכו')",
  "appointment_day": "יום השיעור/הפגישה שנקבע — ראשון/שני/שלישי/רביעי/חמישי/שישי/שבת, או null אם לא נקבע",
  "appointment_time": "שעת השיעור/הפגישה שנקבעה בפורמט HH:MM, או null אם לא נקבעה"
}

חוקים לחילוץ שם:
- אם המשתמש אומר "אני X", "קוראים לי X", "זה X" — החזר X.
- אם המשתמש אומר רק מילה אחת או שתיים שנשמעות כמו שם (למשל "לידור" או "לידור כהן") — זה השם. אם יש ספק או שזה יכול להיות משהו אחר — החזר null.
- אל תחלץ שם אם המילה יכולה להיות משהו אחר (למשל "כן", "אולי", "רוצה").
- phone_number תמיד null.
- אל תנחש. אל תמציא. אם אין — החזר null.

שיחה:
{transcript}
"""


async def extract_lead_from_transcript(transcript: str, caller_phone: str) -> dict:
    """
    Post-call extraction via OpenAI gpt-4o-mini.
    Returns a dict with keys: name, phone_number, topic, notes (all may be None).
    Never raises — falls back to phone-only on any error.
    """
    if not _OPENAI_API_KEY:
        return {"phone_number": caller_phone}
    prompt = _EXTRACT_PROMPT.replace("{transcript}", transcript)
    body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 256,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=body,
                headers={
                    "Authorization": f"Bearer {_OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"]
            raw_text = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            result = json.loads(raw_text)
            if not result.get("phone_number"):
                result["phone_number"] = caller_phone
            return result
    except Exception as exc:
        print(f"[VOICE-EXTRACT] Extraction failed: {exc}")
        return {"phone_number": caller_phone}

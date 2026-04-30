"""
Maya Watch — minimal end-to-end thin slice.

Goal: validate Maya behavior on ONE real business with the smallest possible
surface area. NOT a production system. NOT integrated with MRI / Lead
Intelligence / dashboards. Stands alone.

Flow:
    inbound message arrives  →  store + classify
    contains a question      →  schedule a delayed risk check
    no human reply within X  →  send a single follow-up via Twilio
    customer replies / books →  outcome derived from message log

Storage: in-memory dict (process-local). Wipes on restart. Deliberate.

Follow-up: hardcoded one-shot text, language-aware (HE / EN).

Twilio: same direct-client pattern as app/routes/action_api.py — no new
helper, no MRI coupling, no Supabase.

Outcome tracking: a lead's status is *derived* from its message log + the
followup_sent_at timestamp + a manual booked flag. Operators flip booked
via POST /maya-watch/leads/{phone}/mark-booked.

Limitations (documented, not bugs):
- In-memory storage; restart loses state.
- Doesn't observe outbound messages from non-Maya channels — if the human
  business owner replies via their own WhatsApp app, Maya can't see it
  and may send a redundant follow-up. Acceptable for one-client validation.
- No Twilio webhook signature verification on the inbound endpoint.
- One follow-up per lead per inbound. No multi-touch sequences.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Configuration — env-overridable, sane defaults
# ─────────────────────────────────────────────────────────────────────
RISK_AFTER_MINUTES = int(os.getenv("MAYA_WATCH_RISK_AFTER_MIN", "30"))
NO_RESPONSE_AFTER_HOURS = int(os.getenv("MAYA_WATCH_NO_RESPONSE_AFTER_H", "4"))

QUESTION_KEYWORDS_HE = [
    "מחיר", "כמה עולה", "כמה זה", "כמה?", "עלות",
    "תור", "פגישה", "ייעוץ", "להזמין", "לקבוע",
    "זמין", "פנוי", "פנויה", "מתי",
]
QUESTION_KEYWORDS_EN = [
    "price", "cost", "how much", "rates",
    "book", "appointment", "consultation",
    "available", "availability", "when can", "schedule",
]

FOLLOWUP_BODY_HE = (
    "היי, ראיתי את ההודעה שלך. נשמח לתאם זמן קצר לייעוץ ראשון — "
    "יש לי כמה זמנים פנויים השבוע. מה נוח לך?"
)
FOLLOWUP_BODY_EN = (
    "Hi — I saw your message. Happy to set up a quick first consultation. "
    "I have a few open times this week. What works for you?"
)

# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────
Direction = Literal["in", "out"]


@dataclass
class Message:
    direction: Direction
    body: str
    ts: datetime  # UTC


@dataclass
class Lead:
    phone: str
    name: Optional[str] = None
    messages: list[Message] = field(default_factory=list)
    followup_sent_at: Optional[datetime] = None
    followup_body: Optional[str] = None
    followup_sid: Optional[str] = None
    booked: bool = False
    booked_at: Optional[datetime] = None

    @property
    def last_inbound(self) -> Optional[Message]:
        for m in reversed(self.messages):
            if m.direction == "in":
                return m
        return None

    @property
    def last_outbound(self) -> Optional[Message]:
        for m in reversed(self.messages):
            if m.direction == "out":
                return m
        return None


# Process-local store. Keyed by normalized phone (E.164, no whatsapp: prefix).
_LEADS: dict[str, Lead] = {}


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def normalize_phone(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("whatsapp:"):
        s = s[9:]
    return s


def is_hebrew(text: str) -> bool:
    return any("֐" <= c <= "׿" for c in text)


def has_question(body: str) -> bool:
    if not body:
        return False
    lowered = body.lower()
    if is_hebrew(body):
        return any(kw in body for kw in QUESTION_KEYWORDS_HE)
    return any(kw in lowered for kw in QUESTION_KEYWORDS_EN)


def pick_followup(inbound_body: str) -> str:
    return FOLLOWUP_BODY_HE if is_hebrew(inbound_body) else FOLLOWUP_BODY_EN


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────
# Status derivation — outcome of one lead at a moment in time
# ─────────────────────────────────────────────────────────────────────
def derive_status(lead: Lead) -> str:
    """
    One of:
        booked                  — manually marked
        replied_after_followup  — customer responded after our follow-up
        no_response             — followup sent, > NO_RESPONSE_AFTER_HOURS, silent
        followup_pending        — followup sent, waiting for reply
        at_risk                 — question asked, no follow-up yet, > RISK_AFTER_MINUTES
        awaiting_attention      — question asked, not yet at risk
        active                  — recent inbound, not a question
        outbound_only           — no inbound messages (edge case)
        unknown                 — empty
    """
    if lead.booked:
        return "booked"
    if not lead.messages:
        return "unknown"

    last_in = lead.last_inbound
    if not last_in:
        return "outbound_only"

    if lead.followup_sent_at:
        replied_after = any(
            m.direction == "in" and m.ts > lead.followup_sent_at
            for m in lead.messages
        )
        if replied_after:
            return "replied_after_followup"
        elapsed = now_utc() - lead.followup_sent_at
        if elapsed > timedelta(hours=NO_RESPONSE_AFTER_HOURS):
            return "no_response"
        return "followup_pending"

    if has_question(last_in.body):
        elapsed = now_utc() - last_in.ts
        if elapsed > timedelta(minutes=RISK_AFTER_MINUTES):
            return "at_risk"
        return "awaiting_attention"

    return "active"


# ─────────────────────────────────────────────────────────────────────
# Public API — called by the route layer
# ─────────────────────────────────────────────────────────────────────
def register_inbound(phone: str, body: str, name: Optional[str] = None) -> Lead:
    """Record an inbound message and (if it looks like a question) schedule
    a delayed risk check."""
    phone = normalize_phone(phone)
    lead = _LEADS.get(phone)
    if lead is None:
        lead = Lead(phone=phone, name=name)
        _LEADS[phone] = lead
    elif name and not lead.name:
        lead.name = name

    lead.messages.append(Message(direction="in", body=body, ts=now_utc()))
    logger.info(
        "[MAYA-WATCH] inbound phone=%s body=%r is_question=%s",
        phone, body[:80], has_question(body),
    )

    if has_question(body) and lead.followup_sent_at is None:
        # Fire-and-forget delayed check. If the process dies before it fires,
        # the next manual /tick covers it.
        asyncio.create_task(_delayed_risk_check(phone))

    return lead


def register_outbound(phone: str, body: str, sid: Optional[str] = None) -> None:
    """Record an outbound message (sent by Maya or the operator)."""
    phone = normalize_phone(phone)
    lead = _LEADS.get(phone)
    if lead is None:
        lead = Lead(phone=phone)
        _LEADS[phone] = lead
    lead.messages.append(Message(direction="out", body=body, ts=now_utc()))
    logger.info("[MAYA-WATCH] outbound phone=%s body=%r sid=%s", phone, body[:80], sid)


def mark_booked(phone: str) -> Optional[Lead]:
    phone = normalize_phone(phone)
    lead = _LEADS.get(phone)
    if not lead:
        return None
    lead.booked = True
    lead.booked_at = now_utc()
    logger.info("[MAYA-WATCH] booked phone=%s", phone)
    return lead


def get_all_leads() -> list[Lead]:
    return list(_LEADS.values())


def serialize_lead(lead: Lead) -> dict:
    return {
        "phone": lead.phone,
        "name": lead.name,
        "status": derive_status(lead),
        "message_count": len(lead.messages),
        "last_inbound": (
            {"body": lead.last_inbound.body, "ts": lead.last_inbound.ts.isoformat()}
            if lead.last_inbound
            else None
        ),
        "last_outbound": (
            {"body": lead.last_outbound.body, "ts": lead.last_outbound.ts.isoformat()}
            if lead.last_outbound
            else None
        ),
        "followup_sent_at": (
            lead.followup_sent_at.isoformat() if lead.followup_sent_at else None
        ),
        "followup_body": lead.followup_body,
        "booked": lead.booked,
        "booked_at": lead.booked_at.isoformat() if lead.booked_at else None,
    }


# ─────────────────────────────────────────────────────────────────────
# Risk → follow-up action
# ─────────────────────────────────────────────────────────────────────
async def _delayed_risk_check(phone: str) -> None:
    """Wait RISK_AFTER_MINUTES then evaluate; if at risk, send follow-up."""
    try:
        await asyncio.sleep(RISK_AFTER_MINUTES * 60)
    except asyncio.CancelledError:
        return

    lead = _LEADS.get(phone)
    if not lead:
        return
    if derive_status(lead) != "at_risk":
        return
    await _send_followup(lead)


async def tick() -> dict:
    """Manual scan — useful for cron-style polling or for catching leads
    whose delayed check was lost (e.g. process restart)."""
    actions: list[dict] = []
    for lead in list(_LEADS.values()):
        if derive_status(lead) == "at_risk":
            ok = await _send_followup(lead)
            actions.append({"phone": lead.phone, "sent": bool(ok)})
    logger.info("[MAYA-WATCH] tick checked=%d actions=%d", len(_LEADS), len(actions))
    return {"checked": len(_LEADS), "actions": actions}


async def _send_followup(lead: Lead) -> Optional[str]:
    """Send the single hardcoded follow-up. Returns Twilio SID on success."""
    if lead.followup_sent_at is not None:
        return lead.followup_sid  # already followed up; idempotent

    last_in = lead.last_inbound
    body = pick_followup(last_in.body if last_in else "")

    sid = await _send_whatsapp(lead.phone, body)
    if sid:
        lead.followup_sent_at = now_utc()
        lead.followup_body = body
        lead.followup_sid = sid
        register_outbound(lead.phone, body, sid=sid)
        logger.info("[MAYA-WATCH] followup_sent phone=%s sid=%s", lead.phone, sid)
        return sid
    logger.error("[MAYA-WATCH] followup_failed phone=%s", lead.phone)
    return None


async def _send_whatsapp(to_phone: str, body: str) -> Optional[str]:
    """Direct Twilio send — same pattern as app/routes/action_api.py."""
    sid_env = os.getenv("TWILIO_ACCOUNT_SID", "")
    token_env = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_PHONE_NUMBER", "")
    if not (sid_env and token_env and from_number):
        logger.error("[MAYA-WATCH] twilio env missing — followup not sent")
        return None
    try:
        from twilio.rest import Client
        client = Client(sid_env, token_env)
        msg = await asyncio.to_thread(
            lambda: client.messages.create(
                from_=f"whatsapp:{from_number}",
                to=f"whatsapp:{to_phone}",
                body=body,
            )
        )
        return msg.sid
    except Exception as exc:
        logger.error("[MAYA-WATCH] twilio send failed: %s", exc)
        return None

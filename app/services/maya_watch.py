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

Storage (Stage 3): Supabase tables `maya_watch_leads` + `maya_watch_messages`
via app.services.maya_watch_store. Survives Railway restarts. The previous
in-memory dict is gone — every read goes through the store.

Follow-up: hardcoded one-shot text, language-aware (HE / EN).

Twilio: same direct-client pattern as app/routes/action_api.py — no new
helper, no MRI coupling. Sends include status_callback (Stage 1) so
delivery state lands on the lead via `update_outbound_status`.

Outcome tracking: a lead's status is *derived* from its message log + the
followup_sent_at timestamp + a manual booked flag. Operators flip booked
via POST /maya-watch/leads/{phone}/mark-booked.

Limitations (documented, not bugs):
- Doesn't observe outbound messages from non-Maya channels — if the human
  business owner replies via their own WhatsApp app, Maya can't see it
  and may send a redundant follow-up. Acceptable for one-client validation.
- No Twilio webhook signature verification on the inbound endpoint.
- One follow-up per lead per inbound. No multi-touch sequences.
- v0 multi-tenant: client_id/agent_id columns exist on the tables but
  the service layer leaves them null pending tenant routing.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from app.services import maya_watch_store as store

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
# Data model — same shape as before so derive_status / serialize_lead /
# the briefing builder don't change. Built fresh from store rows now.
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
    followup_status: Optional[str] = None
    followup_error_code: Optional[str] = None
    followup_error_message: Optional[str] = None
    followup_status_at: Optional[datetime] = None
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


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _lead_from_row(row: dict) -> Lead:
    """Reconstruct a Lead dataclass from a store row dict (with `messages` joined)."""
    messages: list[Message] = []
    for m in row.get("messages") or []:
        ts = _parse_iso(m.get("ts")) or now_utc()
        direction = m.get("direction")
        body = m.get("body") or ""
        if direction in ("in", "out"):
            messages.append(Message(direction=direction, body=body, ts=ts))
    return Lead(
        phone=row.get("phone") or "",
        name=row.get("name"),
        messages=messages,
        followup_sent_at=_parse_iso(row.get("followup_sent_at")),
        followup_body=row.get("followup_body"),
        followup_sid=row.get("followup_sid"),
        followup_status=row.get("followup_status"),
        followup_error_code=row.get("followup_error_code"),
        followup_error_message=row.get("followup_error_message"),
        followup_status_at=_parse_iso(row.get("followup_status_at")),
        booked=bool(row.get("booked")),
        booked_at=_parse_iso(row.get("booked_at")),
    )


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
async def register_inbound(phone: str, body: str, name: Optional[str] = None) -> Lead:
    """Record an inbound message and (if it looks like a question) schedule
    a delayed risk check. Persists to Supabase."""
    phone = normalize_phone(phone)
    # Ensure the lead row exists (with name if provided) BEFORE appending the
    # message — append_message also upserts but doesn't pass name.
    await store.upsert_lead(phone, name=name)
    await store.append_message(phone, "in", body)

    logger.info(
        "[MAYA-WATCH] inbound phone=%s body=%r is_question=%s",
        phone, body[:80], has_question(body),
    )

    # Reload the lead to inspect followup_sent_at and decide if we schedule.
    row = await store.get_lead_with_messages(phone)
    lead = _lead_from_row(row) if row else Lead(
        phone=phone,
        name=name,
        messages=[Message(direction="in", body=body, ts=now_utc())],
    )

    if has_question(body) and lead.followup_sent_at is None:
        # Fire-and-forget delayed check. If the process dies before it fires,
        # the next manual /tick (or restart-recovery scan) covers it.
        asyncio.create_task(_delayed_risk_check(phone))

    return lead


async def register_outbound(phone: str, body: str, sid: Optional[str] = None) -> None:
    """Record an outbound message (sent by Maya or the operator)."""
    phone = normalize_phone(phone)
    await store.append_message(phone, "out", body, sid=sid)
    logger.info("[MAYA-WATCH] outbound phone=%s body=%r sid=%s", phone, body[:80], sid)


async def mark_booked(phone: str) -> Optional[Lead]:
    phone = normalize_phone(phone)
    ok = await store.mark_booked(phone)
    if not ok:
        return None
    logger.info("[MAYA-WATCH] booked phone=%s", phone)
    row = await store.get_lead_with_messages(phone)
    return _lead_from_row(row) if row else None


async def get_all_leads() -> list[Lead]:
    rows = await store.get_all_leads_with_messages()
    return [_lead_from_row(r) for r in rows]


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
        "followup_sid": lead.followup_sid,
        "followup_status": lead.followup_status,
        "followup_error_code": lead.followup_error_code,
        "followup_error_message": lead.followup_error_message,
        "followup_status_at": (
            lead.followup_status_at.isoformat() if lead.followup_status_at else None
        ),
        "booked": lead.booked,
        "booked_at": lead.booked_at.isoformat() if lead.booked_at else None,
    }


async def record_delivery_status(
    sid: str,
    status: str,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> bool:
    """Persist a Twilio status_callback update.

    Returns True if the SID matched a known followup, False otherwise.
    Does not raise on unknown SIDs — Twilio may also call back for messages
    sent by other code paths.
    """
    if not sid:
        return False
    matched = await store.update_outbound_status(sid, status, error_code, error_message)
    if matched:
        logger.info(
            "[MAYA-WATCH] delivery_update sid=%s status=%s error_code=%s error_message=%r",
            sid, status, error_code or "-", error_message or "",
        )
    else:
        logger.warning(
            "[MAYA-WATCH] delivery_update_orphan sid=%s status=%s error_code=%s — no matching followup",
            sid, status, error_code or "-",
        )
    return matched


# ─────────────────────────────────────────────────────────────────────
# Briefing — rule-based Hebrew operator summary
# ─────────────────────────────────────────────────────────────────────
async def build_briefing() -> dict:
    leads = await get_all_leads()

    counts = {
        "total_leads": len(leads),
        "at_risk": 0,
        "followup_pending": 0,
        "replied_after_followup": 0,
        "booked": 0,
        "no_response": 0,
    }
    decisions: list[dict] = []
    summary_bullets: list[str] = []
    booked_count = 0

    for lead in leads:
        status = derive_status(lead)
        if status in counts:
            counts[status] += 1

        name = lead.name or lead.phone

        if status == "awaiting_attention":
            decisions.append({
                "id": f"decision:{lead.phone}",
                "phone": lead.phone,
                "lead_name": name,
                "status": status,
                "situation": "ליד חדש שאל שאלה ועדיין מחכה למענה.",
                "why_it_matters": "זה חלון הזמן הכי חשוב. אם אין תגובה מהירה, הסיכוי לסגירה יורד.",
                "recommendation": "ענה עכשיו קצר וברור, ושאל שאלה שמקדמת לתיאום.",
                "suggested_message": "בשמחה. כדי לכוון אותך נכון — מדובר בייעוץ ראשון או בטיפול ספציפי שרצית לבדוק?",
                "confidence": "medium",
                "value_hint": "פוטנציאל לסגירה גבוה אם יקבל מענה מהיר",
            })

        elif status == "followup_pending":
            decisions.append({
                "id": f"decision:{lead.phone}",
                "phone": lead.phone,
                "lead_name": name,
                "status": status,
                "situation": "מאיה שלחה הודעת שחזור, ועדיין מחכים לתגובה.",
                "why_it_matters": "אין צורך להציף את הליד עכשיו. הודעה נוספת מוקדם מדי עלולה להרגיש לוחצת.",
                "recommendation": "להמתין. אם אין תגובה בעוד כמה שעות, לשקול הודעה אחרונה רכה.",
                "suggested_message": None,
                "confidence": "high",
                "value_hint": None,
            })

        elif status == "replied_after_followup":
            decisions.append({
                "id": f"decision:{lead.phone}",
                "phone": lead.phone,
                "lead_name": name,
                "status": status,
                "situation": "הליד חזר אחרי הודעת השחזור של מאיה.",
                "why_it_matters": "זה רגע קריטי. הליד כבר חזר לשיחה, ולכן המטרה עכשיו היא לסגור זמן ולא לפתוח שוב דיון כללי.",
                "recommendation": "הצע לו שני זמנים קרובים וברורים. פתח עם התיאום, ורק אחרי שיש זמן מוסכם חזור למחיר או לפרטים.",
                "suggested_message": "מעולה, מחר פנוי לנו ב-12:00 או ב-16:00. מה נוח לך יותר?",
                "confidence": "high",
                "value_hint": "ליד חם — יש תנופה לניצול",
            })

        elif status == "no_response":
            decisions.append({
                "id": f"decision:{lead.phone}",
                "phone": lead.phone,
                "lead_name": name,
                "status": status,
                "situation": "הליד לא חזר אחרי הודעת השחזור.",
                "why_it_matters": "כנראה שהעניין ירד, אבל עדיין יש סיכוי להציל אותו עם הודעה קצרה ולא לוחצת.",
                "recommendation": "שלח הודעת ניסיון אחרונה, בלי למכור חזק ובלי להאריך.",
                "suggested_message": "רק בודקת אם זה עדיין רלוונטי עבורך. אם כן, אשמח לעזור למצוא זמן שמתאים לך.",
                "confidence": "medium",
                "value_hint": "סיכוי נמוך אך עדיין שווה ניסיון",
            })

        elif status == "booked":
            booked_count += 1

    if booked_count == 1:
        summary_bullets.append("ליד אחד חזר דרך מאיה וסומן כנקבע.")
    elif booked_count > 1:
        summary_bullets.append(f"{booked_count} לידים חזרו דרך מאיה וסומנו כנקבע.")

    replied = counts["replied_after_followup"]
    risk = counts["at_risk"] + counts["followup_pending"]

    if replied > 0:
        headline = "יש לידים שחזרו אחרי הודעת שחזור וצריכים החלטה עכשיו."
    elif risk > 0:
        headline = "מאיה מזהה לידים בסיכון ומנהלת שחזור."
    elif counts["booked"] > 0:
        headline = "מאיה כבר החזירה ליד אחד לשיחה שהסתיימה בקביעה."
    else:
        headline = "מאיה במעקב. אין כרגע דליפות דחופות."

    return {
        "headline": headline,
        "summary_bullets": summary_bullets,
        "decisions": decisions,
        "counts": counts,
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

    row = await store.get_lead_with_messages(phone)
    if not row:
        return
    lead = _lead_from_row(row)
    if derive_status(lead) != "at_risk":
        return
    await _send_followup(lead)


async def tick() -> dict:
    """Manual scan — useful for cron-style polling or for catching leads
    whose delayed check was lost (e.g. process restart)."""
    leads = await get_all_leads()
    actions: list[dict] = []
    for lead in leads:
        if derive_status(lead) == "at_risk":
            ok = await _send_followup(lead)
            actions.append({"phone": lead.phone, "sent": bool(ok)})
    logger.info("[MAYA-WATCH] tick checked=%d actions=%d", len(leads), len(actions))
    return {"checked": len(leads), "actions": actions}


async def _send_followup(lead: Lead) -> Optional[str]:
    """Send the single hardcoded follow-up. Returns Twilio SID on success."""
    if lead.followup_sent_at is not None:
        return lead.followup_sid  # already followed up; idempotent

    last_in = lead.last_inbound
    body = pick_followup(last_in.body if last_in else "")

    sid = await _send_whatsapp(lead.phone, body)
    if sid:
        sent_at = now_utc()
        # Persist outbound message (with sid) AND denormalize followup snapshot.
        await store.append_message(lead.phone, "out", body, ts=sent_at, sid=sid)
        await store.update_lead_followup(
            lead.phone,
            sid=sid,
            body=body,
            sent_at=sent_at,
            status="queued",
        )
        logger.info("[MAYA-WATCH] followup_sent phone=%s sid=%s status=queued", lead.phone, sid)
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

    from_full = f"whatsapp:{from_number}"
    to_full = f"whatsapp:{to_phone}"

    base_url = os.getenv("BASE_URL", "").strip().rstrip("/")
    status_cb = f"{base_url}/maya-watch/twilio-status" if base_url else None
    if status_cb is None:
        logger.warning(
            "[MAYA-WATCH] BASE_URL not set — sending without status_callback "
            "(no delivery observability for this message)"
        )

    logger.info(
        "[MAYA-WATCH] send_attempt from=%s to=%s status_cb=%s body_len=%d",
        from_full, to_full, status_cb or "(none)", len(body),
    )
    try:
        from twilio.rest import Client
        client = Client(sid_env, token_env)
        kwargs: dict = {"from_": from_full, "to": to_full, "body": body}
        if status_cb:
            kwargs["status_callback"] = status_cb
        msg = await asyncio.to_thread(lambda: client.messages.create(**kwargs))
        logger.info(
            "[MAYA-WATCH] twilio_accepted sid=%s from=%s to=%s",
            msg.sid, from_full, to_full,
        )
        return msg.sid
    except Exception as exc:
        logger.error(
            "[MAYA-WATCH] twilio_send_failed from=%s to=%s error=%s",
            from_full, to_full, exc,
        )
        return None

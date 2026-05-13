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
    # Stage 4 — tenant scope. Optional so legacy unrouted rows still load.
    client_id: Optional[str] = None
    agent_id: Optional[str] = None
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
        client_id=row.get("client_id"),
        agent_id=row.get("agent_id"),
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
# Tenant resolver — Twilio To number → (agent_id, client_id)
# ─────────────────────────────────────────────────────────────────────
import httpx  # noqa: E402  (placed here to keep the resolver block self-contained)

_SUPABASE_URL_FOR_RESOLVER = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY_FOR_RESOLVER = os.getenv("SUPABASE_SERVICE_KEY", "")


async def _agents_config_lookup(field: str, value: str) -> Optional[dict]:
    """Tiny direct query against agents_config — returns the first matching
    active row, or None. Mirrors the public lookup pattern used by
    app/services/agent_config.py without reaching into its private internals.
    """
    if not (_SUPABASE_URL_FOR_RESOLVER and _SUPABASE_KEY_FOR_RESOLVER and value):
        return None
    headers = {
        "apikey": _SUPABASE_KEY_FOR_RESOLVER,
        "Authorization": f"Bearer {_SUPABASE_KEY_FOR_RESOLVER}",
    }
    params = {
        field: f"eq.{value}",
        "is_active": "eq.true",
        "select": "id,client_id,agent_name,whatsapp_number,phone_number",
        "limit": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL_FOR_RESOLVER}/rest/v1/agents_config",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            rows = resp.json()
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("[MAYA-WATCH] agents_config lookup failed %s=%s: %s", field, value, exc)
        return None


async def _agents_config_lookup_by_id(agent_id: str) -> Optional[dict]:
    """Lookup an agent row by id (used for the sandbox default fallback).
    Skips the is_active filter so a deactivated default still resolves."""
    if not (_SUPABASE_URL_FOR_RESOLVER and _SUPABASE_KEY_FOR_RESOLVER and agent_id):
        return None
    headers = {
        "apikey": _SUPABASE_KEY_FOR_RESOLVER,
        "Authorization": f"Bearer {_SUPABASE_KEY_FOR_RESOLVER}",
    }
    params = {
        "id": f"eq.{agent_id}",
        "select": "id,client_id,agent_name",
        "limit": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL_FOR_RESOLVER}/rest/v1/agents_config",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            rows = resp.json()
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("[MAYA-WATCH] agents_config id lookup failed id=%s: %s", agent_id, exc)
        return None


async def resolve_agent_for_to(to_number: str) -> tuple[Optional[str], Optional[str]]:
    """
    Resolve (agent_id, client_id) from a Twilio "To" number.

    Lookup order:
      1. agents_config.whatsapp_number = To (primary, WhatsApp channel)
      2. agents_config.phone_number    = To (fallback, voice-config row
         that also has a whatsapp_number set)
      3. MAYA_WATCH_DEFAULT_AGENT_ID env (sandbox shared-number fallback)

    Returns (None, None) on no match — the caller persists with null
    tenant scope and logs `unrouted_inbound` for admin triage.
    """
    if not to_number:
        # No To at all — sandbox/test path. Still try the configured default.
        normalized = ""
    else:
        normalized = to_number.strip()
        if normalized.startswith("whatsapp:"):
            normalized = normalized[9:]

    if normalized:
        row = await _agents_config_lookup("whatsapp_number", normalized)
        if not row:
            row = await _agents_config_lookup("phone_number", normalized)
        if row:
            return (row.get("id"), row.get("client_id"))

    default_id = os.getenv("MAYA_WATCH_DEFAULT_AGENT_ID", "").strip()
    if default_id:
        row = await _agents_config_lookup_by_id(default_id)
        if row:
            logger.info(
                "[MAYA-WATCH] resolver_default to=%s → agent_id=%s client_id=%s",
                normalized or "(empty)", row.get("id"), row.get("client_id"),
            )
            return (row.get("id"), row.get("client_id"))

    logger.warning("[MAYA-WATCH] unrouted_inbound to=%s — no agent matched, no default set", normalized or "(empty)")
    return (None, None)


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
async def register_inbound(
    phone: str,
    body: str,
    name: Optional[str] = None,
    *,
    client_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Lead:
    """Record an inbound message and (if it looks like a question) schedule
    a delayed risk check. Persists to Supabase, scoped by tenant."""
    phone = normalize_phone(phone)
    # Ensure the lead row exists (with name + tenant scope) BEFORE appending
    # the message. The lead's client_id determines which tenant owns the row.
    await store.upsert_lead(phone, name=name, client_id=client_id, agent_id=agent_id)
    await store.append_message(
        phone, "in", body,
        client_id=client_id, agent_id=agent_id,
    )

    logger.info(
        "[MAYA-WATCH] inbound phone=%s client_id=%s agent_id=%s body=%r is_question=%s",
        phone, client_id or "-", agent_id or "-", body[:80], has_question(body),
    )

    # Reload the lead to inspect followup_sent_at and decide if we schedule.
    row = await store.get_lead_with_messages(phone, client_id=client_id)
    lead = _lead_from_row(row) if row else Lead(
        phone=phone,
        name=name,
        client_id=client_id,
        agent_id=agent_id,
        messages=[Message(direction="in", body=body, ts=now_utc())],
    )

    if has_question(body) and lead.followup_sent_at is None:
        # Fire-and-forget delayed check. If the process dies before it fires,
        # the next manual /tick (or restart-recovery scan) covers it.
        asyncio.create_task(_delayed_risk_check(phone, client_id=client_id))

    return lead


async def register_inbound_persist_only(
    phone: str,
    body: str,
    name: Optional[str] = None,
    *,
    client_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> None:
    """Persist an inbound message into Maya Watch tables WITHOUT scheduling
    any follow-up or risk check.

    Used by the existing /whatsapp/reply pipeline (Make.com → backend) to
    mirror customer-driven traffic into maya_watch_leads + maya_watch_messages
    so /home/watch sees real activity. The reply pipeline already owns its
    own response/follow-up behavior via whatsapp_conversations + Twilio;
    Maya Watch must NOT layer a second follow-up on top.
    """
    phone = normalize_phone(phone)
    await store.upsert_lead(phone, name=name, client_id=client_id, agent_id=agent_id)
    await store.append_message(
        phone, "in", body,
        client_id=client_id, agent_id=agent_id,
    )
    logger.info(
        "[MAYA-WATCH] mirror inbound phone=%s client_id=%s agent_id=%s body=%r",
        phone, client_id or "-", agent_id or "-", body[:80],
    )


async def register_outbound(
    phone: str,
    body: str,
    sid: Optional[str] = None,
    *,
    client_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    source: Optional[str] = None,
) -> None:
    """Record an outbound message (sent by Maya or the operator).

    `source` (Stage 10C-1): pass-through to the store. Currently unused —
    Maya's followup path inlines its own append_message call. Reserved for
    10C-2 operator-send endpoint, which will call this with
    source='operator_preview'.
    """
    phone = normalize_phone(phone)
    await store.append_message(
        phone, "out", body,
        sid=sid, client_id=client_id, agent_id=agent_id,
        source=source,
    )
    logger.info(
        "[MAYA-WATCH] outbound phone=%s client_id=%s source=%s body=%r sid=%s",
        phone, client_id or "-", source or "-", body[:80], sid,
    )


async def mark_booked(phone: str, *, client_id: Optional[str] = None) -> Optional[Lead]:
    phone = normalize_phone(phone)
    ok = await store.mark_booked(phone, client_id=client_id)
    if not ok:
        return None
    logger.info("[MAYA-WATCH] booked phone=%s client_id=%s", phone, client_id or "-")
    row = await store.get_lead_with_messages(phone, client_id=client_id)
    return _lead_from_row(row) if row else None


async def get_all_leads(client_id: Optional[str] = None) -> list[Lead]:
    """When client_id is provided, returns only that tenant's leads.
    When None, returns all leads (admin-aggregated view)."""
    rows = await store.get_all_leads_with_messages(client_id=client_id)
    return [_lead_from_row(r) for r in rows]


async def get_lead_with_id(
    phone: str,
    client_id: Optional[str] = None,
) -> Optional[tuple[str, Lead]]:
    """
    Single-lead lookup that exposes the underlying row UUID alongside the
    Lead dataclass. Used by the action endpoint (Stage 7) which needs the
    UUID to record an action without us having to add `id` to Lead and
    threading it through every call site.

    Tenant scope: when client_id is provided, only returns the lead if it
    belongs to that tenant — same semantics as the rest of Maya Watch.
    Returns None if no matching lead, or if the row lacks an id.
    """
    norm = normalize_phone(phone)
    if not norm:
        return None
    row = await store.get_lead_with_messages(norm, client_id=client_id)
    if not row:
        return None
    lead_id = row.get("id")
    if not lead_id:
        return None
    return lead_id, _lead_from_row(row)


# ─────────────────────────────────────────────────────────────────────
# Operator actions (Stage 7) — service-layer wrappers around the store.
# Routes go through these so the route module never imports the store.
# ─────────────────────────────────────────────────────────────────────


def parse_decision_id(decision_id: str) -> tuple[Optional[str], str]:
    """
    Parse a decision id emitted by build_briefing.

    Two formats accepted:
        decision:{status}:{phone}   (Stage 7+)  → (status, phone)
        decision:{phone}            (legacy)    → (None, phone)

    Phone numbers don't contain ':' (E.164 form is digits + leading '+'),
    and the status enum values used by derive_status don't either, so the
    split is unambiguous.

    Caller convention: when status is None (legacy id), derive the current
    status from the lead. Raises ValueError on any other shape.
    """
    if not isinstance(decision_id, str) or not decision_id:
        raise ValueError("decision_id must be a non-empty string")
    if not decision_id.startswith("decision:"):
        raise ValueError("decision_id must start with 'decision:'")
    rest = decision_id[len("decision:"):]
    parts = rest.split(":", 1)
    if len(parts) == 2:
        status, phone = parts[0].strip(), parts[1].strip()
        if not status or not phone:
            raise ValueError("decision_id parts must be non-empty")
        return status, phone
    phone = parts[0].strip()
    if not phone:
        raise ValueError("decision_id must include a phone")
    return None, phone


async def record_decision_action(
    *,
    lead_id: str,
    phone: str,
    decision_status: str,
    client_id: Optional[str],
    agent_id: Optional[str],
    acted_by: Optional[str],
) -> Optional[dict]:
    """
    Service-layer wrapper around store.record_action. Always writes
    action_type='acted' for v0; future verbs (e.g. 'dismissed') would land
    as additional service helpers, not as caller-supplied parameters.

    Returns the action row dict on success (with `already_acted: bool`),
    or None on failure — the route layer translates None into 5xx without
    needing to know about the store module.
    """
    return await store.record_action(
        lead_id=lead_id,
        phone=phone,
        decision_status=decision_status,
        client_id=client_id,
        agent_id=agent_id,
        action_type="acted",
        acted_by=acted_by,
    )


async def undo_decision_action(
    *,
    lead_id: str,
    phone: str,
    decision_status: str,
    client_id: Optional[str],
    agent_id: Optional[str],
    acted_by: Optional[str],
) -> dict:
    """
    Service-layer wrapper around store.record_undone (Stage 8C).

    Returns the discriminated dict from the store:
        {found_acted, ok, already_undone, row}
    The route layer maps:
        found_acted=False  → 404
        ok=False           → 500
        ok=True            → 200 with row + already_undone
    """
    return await store.record_undone(
        lead_id=lead_id,
        phone=phone,
        decision_status=decision_status,
        client_id=client_id,
        agent_id=agent_id,
        acted_by=acted_by,
    )


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
        # Recent message history projection. Uses already-loaded lead.messages
        # (no extra query). Capped at the last 20, oldest→newest. Only the
        # fields needed by the dashboard thread modal — sid/status/error stay
        # on the per-lead followup_* fields above.
        "messages": [
            {"direction": m.direction, "body": m.body, "ts": m.ts.isoformat()}
            for m in lead.messages[-20:]
        ],
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
async def build_briefing(client_id: Optional[str] = None) -> dict:
    # Stage 7 — read raw rows so we have lead.id for the suppression check.
    # Same network cost as get_all_leads; we just keep the uuid alongside
    # the dataclass instead of dropping it on the floor.
    # Stage 8B — fetch the three Supabase round-trips concurrently. Each
    # is independent and adds ~50-100ms; serialized would compound. Each
    # helper has its own fail-safe so partial failures (e.g. actions table
    # blip) don't take down the whole briefing.
    rows, acted_keys, handled, recent_actions_rows = await asyncio.gather(
        store.get_all_leads_with_messages(client_id=client_id),
        store.list_acted_keys(client_id=client_id),
        store.get_handled_today(client_id=client_id, limit=3),
        store.get_recent_actions(client_id=client_id, limit=10),
    )
    pairs: list[tuple[Optional[str], Lead]] = [
        (r.get("id"), _lead_from_row(r)) for r in rows
    ]

    counts = {
        "total_leads": len(pairs),
        "at_risk": 0,
        "followup_pending": 0,
        "replied_after_followup": 0,
        "booked": 0,
        "no_response": 0,
    }
    decisions: list[dict] = []
    summary_bullets: list[str] = []
    booked_count = 0

    for lead_id, lead in pairs:
        status = derive_status(lead)
        if status in counts:
            counts[status] += 1
        if status == "booked":
            booked_count += 1
            continue  # booked never produces an open decision

        # Stage 7 — gate open decisions only. Counts above stay accurate
        # regardless of whether the operator has acted; counts represent
        # lead reality, decisions represent open work.
        if lead_id and (lead_id, status, "acted") in acted_keys:
            continue

        name = lead.name or lead.phone
        decision_id = f"decision:{status}:{lead.phone}"  # Stage 7 — status-aware id

        if status == "awaiting_attention":
            decisions.append({
                "id": decision_id,
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

        # Stage 8A — at_risk: question stayed unanswered past RISK_AFTER_MINUTES
        # without any followup. Same lifecycle as awaiting_attention but with
        # urgency framing — the operator should reach out personally now.
        # Sits next to awaiting_attention because both stem from the same root
        # condition (has_question + no followup_sent_at), only differ by elapsed.
        elif status == "at_risk":
            decisions.append({
                "id": decision_id,
                "phone": lead.phone,
                "lead_name": name,
                "status": status,
                "situation": "הליד שאל שאלה ונשאר בלי מענה יותר מדי זמן.",
                "why_it_matters": "זה רגע שבו ההתעניינות יכולה להתקרר. תגובה קצרה עכשיו יכולה להחזיר את השיחה למסלול.",
                "recommendation": "פנה אל הליד עכשיו עם הודעה קצרה ואישית. כדאי להכיר בעיכוב ואז להציע צעד ברור.",
                "suggested_message": "סליחה על העיכוב — אני כאן עכשיו. רוצה שנקבע זמן קצר לדבר?",
                "confidence": "high",
                "value_hint": "ליד בסיכון — עדיין אפשר להחזיר אותו לשיחה.",
            })

        elif status == "followup_pending":
            decisions.append({
                "id": decision_id,
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
                "id": decision_id,
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
                "id": decision_id,
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

    # Stage 8B — enrich recent action rows with lead_name from the leads
    # already loaded above; falls back to phone if the lead isn't in scope
    # (e.g. cross-tenant aggregation in admin mode where the lead row
    # belongs to a different client and wasn't fetched).
    name_by_id: dict[str, str] = {
        lead_id: (lead.name or lead.phone)
        for lead_id, lead in pairs
        if lead_id
    }
    handled_today = {
        "count": handled.get("count", 0),
        "recent": [
            {
                "lead_name": name_by_id.get(r.get("lead_id"), r.get("phone") or "—"),
                "phone": r.get("phone"),
                "decision_status": r.get("decision_status"),
                "acted_at": r.get("acted_at"),
            }
            for r in handled.get("recent", [])
        ],
    }

    # Recent actions audit feed — last 10 acted/undone rows in scope, newest
    # first. Joins lead_name from the same in-scope leads dict used above so
    # we don't hit the leads table again.
    recent_actions = [
        {
            "lead_name": name_by_id.get(r.get("lead_id"), r.get("phone") or "—"),
            "phone": r.get("phone"),
            "decision_status": r.get("decision_status"),
            "action_type": r.get("action_type"),
            "acted_at": r.get("acted_at"),
        }
        for r in recent_actions_rows
    ]

    return {
        "headline": headline,
        "summary_bullets": summary_bullets,
        "decisions": decisions,
        "counts": counts,
        "handled_today": handled_today,
        "recent_actions": recent_actions,
    }


# ─────────────────────────────────────────────────────────────────────
# Risk → follow-up action
# ─────────────────────────────────────────────────────────────────────
async def _delayed_risk_check(phone: str, *, client_id: Optional[str] = None) -> None:
    """Wait RISK_AFTER_MINUTES then evaluate; if at risk, send follow-up.
    Tenant-scoped so two clients with the same phone don't collide."""
    try:
        await asyncio.sleep(RISK_AFTER_MINUTES * 60)
    except asyncio.CancelledError:
        return

    row = await store.get_lead_with_messages(phone, client_id=client_id)
    if not row:
        return
    lead = _lead_from_row(row)
    if derive_status(lead) != "at_risk":
        return
    await _send_followup(lead)


async def tick(client_id: Optional[str] = None) -> dict:
    """Manual scan — useful for cron-style polling or for catching leads
    whose delayed check was lost (e.g. process restart). When client_id is
    provided, scans only that tenant's leads; otherwise all (admin)."""
    leads = await get_all_leads(client_id=client_id)
    actions: list[dict] = []
    for lead in leads:
        if derive_status(lead) == "at_risk":
            ok = await _send_followup(lead)
            actions.append({"phone": lead.phone, "sent": bool(ok)})
    logger.info("[MAYA-WATCH] tick checked=%d actions=%d client_id=%s",
                len(leads), len(actions), client_id or "all")
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
        # Tenant ids come from the lead itself so the new outbound row inherits
        # the same scope as the conversation it belongs to.
        await store.append_message(
            lead.phone, "out", body,
            ts=sent_at, sid=sid,
            client_id=lead.client_id, agent_id=lead.agent_id,
            # Stage 10C-1 — tag this row as Maya followup so the status-
            # callback mirror updates lead.followup_* for it. Operator-sent
            # rows (10C-2+) will use source='operator_preview' and skip the
            # mirror, preserving Maya's followup snapshot.
            source="followup",
        )
        await store.update_lead_followup(
            lead.phone,
            sid=sid,
            body=body,
            sent_at=sent_at,
            status="queued",
            client_id=lead.client_id,
        )
        logger.info(
            "[MAYA-WATCH] followup_sent phone=%s client_id=%s sid=%s status=queued",
            lead.phone, lead.client_id or "-", sid,
        )
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


# ─────────────────────────────────────────────────────────────────────
# Operator-driven WhatsApp send (Stage 10C-2)
# Backend-only endpoint orchestration. No frontend caller in 10C-2 — the
# Next.js route + UI button land in Stage 10E. Until then this code path
# is reachable but unused by any production caller.
# ─────────────────────────────────────────────────────────────────────

import re  # noqa: E402

# Mirror of action_api.py:_validate_phone — duplicated (not imported) to
# keep Maya Watch dependency-free of the legacy /api/actions surface. If
# either copy changes, update both. Original at app/routes/action_api.py:90.
_PHONE_DIGIT_RE = re.compile(r"[^\d+]")


def _validate_phone(raw: str) -> str:
    """Normalize to E.164 (+countrycode digits). Raises ValueError if invalid."""
    cleaned = _PHONE_DIGIT_RE.sub("", (raw or "").strip())
    if not cleaned.startswith("+") and len(cleaned) >= 10:
        cleaned = f"+{cleaned}"
    if not cleaned.startswith("+"):
        raise ValueError(f"phone must start with +, got: {raw!r}")
    if len(cleaned) < 10 or len(cleaned) > 16:
        raise ValueError(f"phone length invalid: {raw!r}")
    return cleaned


def _is_phone_allowlisted(phone: str) -> bool:
    """Hard server-side allowlist for operator-send (Stage 10D).

    Reads MAYA_WATCH_SEND_ALLOWED_PHONES (comma-separated E.164) at call
    time. Trims whitespace from each entry and skips empties. Returns
    True only when `phone` exactly matches a non-empty entry.

    **Fail-closed semantics:** when the env var is missing, empty, or
    parses to a zero-length set after trimming, EVERY send is rejected.
    This is the gate that keeps the endpoint safe before frontend
    connects (Stage 10E) and live-fire smoke runs (Stage 10F+).

    Caller must pass the SERVER-RESOLVED, validated E.164 phone — never
    a caller-supplied value. The orchestrator enforces this by reading
    only from the lead row.
    """
    raw = os.getenv("MAYA_WATCH_SEND_ALLOWED_PHONES", "").strip()
    if not raw:
        return False
    allowed = {p.strip() for p in raw.split(",") if p.strip()}
    if not allowed:
        return False
    return phone in allowed


def _sanitize_for_whatsapp(text: str) -> str:
    """Replace Unicode line/paragraph separators that have historically
    crashed our outbound paths (\\u2028, \\u2029). Mirrors the strict
    sanitize precedent in app/services/whatsapp_reply.py."""
    if not text:
        return ""
    return text.replace(" ", "\n").replace(" ", "\n")


async def _send_operator_via_twilio(
    *,
    from_number: str,
    to_phone: str,
    body: str,
    base_url: str,
) -> str:
    """Twilio send seam — extracted as a standalone async function so
    tests can monkeypatch it without exercising the real Twilio SDK.
    Returns the message SID. Raises any Twilio exception verbatim so the
    orchestrator can map it to the 502 `twilio_send_failed` response.

    Reads TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN from env at call time
    (orchestrator already enforced their presence before getting here)."""
    from twilio.rest import Client

    sid_env = os.getenv("TWILIO_ACCOUNT_SID", "")
    token_env = os.getenv("TWILIO_AUTH_TOKEN", "")
    client = Client(sid_env, token_env)
    msg = await asyncio.to_thread(lambda: client.messages.create(
        from_=f"whatsapp:{from_number}",
        to=f"whatsapp:{to_phone}",
        body=body,
        status_callback=f"{base_url}/maya-watch/twilio-status",
    ))
    return msg.sid


def _build_send_response_payload(
    message_row: dict,
    *,
    lead_phone: Optional[str],
    already_sent: bool,
) -> dict:
    """Format a maya_watch_messages row as the operator-send endpoint response."""
    metadata = message_row.get("metadata") or {}
    return {
        "ok": True,
        "message_id": message_row.get("id"),
        "twilio_sid": message_row.get("sid"),
        "status": message_row.get("status"),
        "lead_id": message_row.get("lead_id"),
        "phone": lead_phone,
        "decision_id": metadata.get("decision_id"),
        "source": message_row.get("source"),
        "created_at": message_row.get("ts"),
        "already_sent": already_sent,
    }


async def send_operator_whatsapp(
    *,
    lead_id: str,
    message: str,
    decision_id: Optional[str],
    sent_by: Optional[str],
    idempotency_key: str,
    client_id: Optional[str],
) -> dict:
    """Operator-driven WhatsApp send orchestrator.

    Returns a discriminated dict the route layer maps to HTTP status:
        {"ok": True,  "payload": {...}}                            → 200
        {"ok": False, "error_code": "...", "extra": {...}, ...}  → see _ERROR_CODE_HTTP

    Order of operations (each step rejects fast):
        1. idempotency check  — short-circuit; never call Twilio twice
        2. lead lookup        — server-side, tenant-scoped if client_id given
        3. phone validation   — server-side from lead.phone, never caller-supplied
        4. message sanitize+validate
        5. 24h window check   — from maya_watch_messages, NOT legacy leads.last_whatsapp_inbound_at
        6. agent lookup       — server-side from lead.agent_id, resolves whatsapp_number
        7. env preflight      — BASE_URL + TWILIO creds (fail closed)
        8. Twilio send
        9. persist message    — direct insert via store.insert_outbound_message
       10. race handling      — re-fetch on 409 (concurrent same-key)
    """
    # Step 1 — idempotency check first (cheap, avoids all downstream work on retry).
    existing = await store.find_message_by_idempotency_key(idempotency_key)
    if existing is not None:
        # Look up the lead's phone for the response — only on the (rare) hit path.
        existing_lead = await store.get_lead_by_id(existing.get("lead_id") or "")
        return {
            "ok": True,
            "payload": _build_send_response_payload(
                existing,
                lead_phone=(existing_lead or {}).get("phone"),
                already_sent=True,
            ),
        }

    # Step 2 — lead lookup (tenant-scoped if client_id provided).
    lead = await store.get_lead_by_id(lead_id, client_id=client_id)
    if not lead:
        return {"ok": False, "error_code": "lead_not_found"}
    if not lead.get("agent_id"):
        return {
            "ok": False,
            "error_code": "lead_unrouted",
            "error_detail": "lead has no agent_id — assign an agent before sending",
        }

    # Step 3 — phone validation (server-resolved from lead row).
    try:
        validated_phone = _validate_phone(lead.get("phone") or "")
    except ValueError as exc:
        return {"ok": False, "error_code": "invalid_phone", "error_detail": str(exc)}

    # Step 3.5 — allowlist gate (Stage 10D safety). Hard fail-closed
    # rejection for any phone not in MAYA_WATCH_SEND_ALLOWED_PHONES. Sits
    # before message validation, 24h check, agent lookup, Twilio send,
    # and DB insert — earliest possible cutoff once we know which lead's
    # phone the send would actually target. Compared against the
    # SERVER-RESOLVED validated_phone; caller-supplied body fields are
    # never consulted.
    if not _is_phone_allowlisted(validated_phone):
        logger.info(
            "[MAYA-WATCH] operator_send_blocked_allowlist lead_id=%s phone=%s",
            lead_id, validated_phone,
        )
        return {
            "ok": False,
            "error_code": "send_not_allowed",
            "extra": {"message": "Operator send is not enabled for this phone"},
        }

    # Step 4 — message sanitize + length recheck.
    sanitized = _sanitize_for_whatsapp(message).strip()
    if not sanitized:
        return {"ok": False, "error_code": "invalid_body", "error_detail": "message empty after trim"}
    if len(sanitized) > 1500:
        return {"ok": False, "error_code": "invalid_body", "error_detail": "message too long after sanitization"}

    # Step 5 — 24h WhatsApp customer-service window.
    last_in_ts = await store.get_last_inbound_ts(lead_id)
    if last_in_ts is None:
        return {
            "ok": False,
            "error_code": "whatsapp_window_closed",
            "extra": {"reason": "no_inbound", "last_inbound_at": None},
        }
    if (now_utc() - last_in_ts) > timedelta(hours=24):
        return {
            "ok": False,
            "error_code": "whatsapp_window_closed",
            "extra": {"reason": "too_old", "last_inbound_at": last_in_ts.isoformat()},
        }

    # Step 6 — agent lookup → whatsapp_number.
    agent_row = await _agents_config_lookup("id", lead["agent_id"])
    if not agent_row:
        return {
            "ok": False,
            "error_code": "agent_misconfigured",
            "error_detail": "agents_config row not found or inactive",
        }
    sender_number = (agent_row.get("whatsapp_number") or "").strip()
    if not sender_number:
        return {
            "ok": False,
            "error_code": "agent_misconfigured",
            "error_detail": "agent has no whatsapp_number",
        }

    # Step 7 — env preflight.
    base_url = os.getenv("BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return {"ok": False, "error_code": "base_url_not_configured"}
    if not (os.getenv("TWILIO_ACCOUNT_SID", "").strip() and os.getenv("TWILIO_AUTH_TOKEN", "").strip()):
        return {"ok": False, "error_code": "twilio_not_configured"}

    # Step 8 — Twilio send.
    try:
        twilio_msg_sid = await _send_operator_via_twilio(
            from_number=sender_number,
            to_phone=validated_phone,
            body=sanitized,
            base_url=base_url,
        )
    except Exception as exc:
        logger.error(
            "[MAYA-WATCH] operator_send_twilio_failed lead_id=%s sender=%s to=%s error=%s",
            lead_id, sender_number, validated_phone, exc,
        )
        return {
            "ok": False,
            "error_code": "twilio_send_failed",
            "error_detail": str(exc),
        }

    # Step 9 — persist outbound message row.
    metadata: dict = {"idempotency_key": idempotency_key}
    if decision_id:
        metadata["decision_id"] = decision_id
    if sent_by:
        metadata["sent_by"] = sent_by

    inserted = await store.insert_outbound_message(
        lead_id=lead_id,
        client_id=lead.get("client_id"),
        agent_id=lead.get("agent_id"),
        body=sanitized,
        sid=twilio_msg_sid,
        source="operator_preview",
        status="queued",
        metadata=metadata,
    )

    # Step 10 — handle race: concurrent same-key insert raced ahead.
    if inserted is not None and inserted.get("_conflict"):
        logger.warning(
            "[MAYA-WATCH] operator_send race_resolved key=%s lead_id=%s twilio_sid=%s",
            idempotency_key, lead_id, twilio_msg_sid,
        )
        winner = await store.find_message_by_idempotency_key(idempotency_key)
        if winner is None:
            return {
                "ok": False,
                "error_code": "twilio_send_failed",
                "error_detail": "race resolved but winner row not found",
            }
        return {
            "ok": True,
            "payload": _build_send_response_payload(
                winner, lead_phone=lead.get("phone"), already_sent=True,
            ),
        }

    if inserted is None:
        # Twilio accepted but we couldn't persist. The message went out;
        # the dashboard won't show it. Log full context for manual recon.
        logger.error(
            "[MAYA-WATCH] post_twilio_insert_failed sid=%s lead_id=%s body=%r — message sent, NOT persisted",
            twilio_msg_sid, lead_id, sanitized[:80],
        )
        return {
            "ok": False,
            "error_code": "twilio_send_failed",
            "error_detail": f"twilio_accepted_sid={twilio_msg_sid} but db insert failed",
        }

    logger.info(
        "[MAYA-WATCH] operator_send sent_by=%s lead_id=%s sid=%s source=operator_preview decision_id=%s client_id=%s",
        sent_by or "-", lead_id, twilio_msg_sid, decision_id or "-", lead.get("client_id") or "-",
    )

    return {
        "ok": True,
        "payload": _build_send_response_payload(
            inserted, lead_phone=lead.get("phone"), already_sent=False,
        ),
    }

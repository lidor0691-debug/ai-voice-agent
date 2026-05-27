"""
app/routes/no_reply_followup_api.py
===================================
GET /followup/no-reply-due — DRY-RUN eligibility for BPM WhatsApp no-reply follow-ups.

This is a READ-ONLY diagnosis endpoint. It NEVER sends a message and NEVER marks
anything as sent. Make.com is intentionally NOT wired to it yet.

Source of truth: the Maya Watch conversation state already mirrored for BPM by the
active WhatsApp scenario (maya_watch_leads + maya_watch_messages). A lead is "due"
only when ALL of these hold:

  1. Lead belongs to an allow-listed (BPM) client_id.
  2. Channel is WhatsApp (Maya Watch is the WhatsApp conversation store).
  3. Phone is present.
  4. The latest message on the thread is OUTBOUND (Maya spoke last).
  5. That latest outbound message is older than NO_REPLY_HOURS (2h).
  6. The customer has NOT replied after it — guaranteed by (4): if the newest
     message is outbound, there is by definition no inbound after it.
  7. No no-reply follow-up was already sent (maya_watch_leads.followup_sent_at IS NULL).
  8. The lead is not booked / closed / not-relevant / completed
     (maya_watch_leads.booked = false AND leads.status not in a terminal set).
  9. Current Israel time is within 09:00–21:00. Outside that window the due list
     is empty, so a lead that goes quiet at night naturally reappears after 09:00
     (the >2h condition has no upper bound).

Security: same X-Followup-Secret header as /followup/due and /followup/mark-sent.
"""

import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter()

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_FOLLOWUP_SECRET = os.getenv("FOLLOWUP_SECRET", "")

# Tenant allow-list — BPM only for now. Override via env (comma-separated client_ids).
# Defaults to BPM's client_id so the dry-run works out of the box without leaking
# to any other tenant (Roi Insurance etc. are never included).
_BPM_CLIENT_ID = "642d2881-9e7d-47cb-8cae-2d6b58a062de"
_ALLOWED_CLIENT_IDS = [
    c.strip()
    for c in os.getenv("NO_REPLY_FOLLOWUP_CLIENT_IDS", _BPM_CLIENT_ID).split(",")
    if c.strip()
]

# A lead is eligible only after Maya's last message has gone unanswered this long.
_NO_REPLY_HOURS = float(os.getenv("NO_REPLY_FOLLOWUP_HOURS", "2"))

# Day window (Israel local time). [09:00, 21:00).
_DAY_START_HOUR = 9
_DAY_END_HOUR = 21
_ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# Terminal lead statuses (from the `leads` table) that must never be followed up.
_TERMINAL_STATUSES = {
    "booked", "closed", "completed", "done",
    "not_relevant", "not relevant", "lost", "spam", "cancelled",
}

# Suggested follow-up copy (returned for preview only — NOT sent here).
_FOLLOWUP_MESSAGE = (
    "היי 😊 רק בודקת איתך אם עדיין רלוונטי לגבי הריקוד לבת מצווה?\n"
    "אשמח לעזור ולתת לך את כל הפרטים 💃"
)


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
    }


@router.get("/followup/no-reply-due")
async def get_no_reply_due(x_followup_secret: str = Header(default="")):
    # ── Security: same pattern as /followup/due ──────────────────────────────
    if _FOLLOWUP_SECRET and x_followup_secret != _FOLLOWUP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    now = datetime.now(timezone.utc)
    israel_now = now.astimezone(_ISRAEL_TZ)

    # ── Night rule: outside 09:00–21:00 Israel → nothing is due right now ─────
    if not (_DAY_START_HOUR <= israel_now.hour < _DAY_END_HOUR):
        return {
            "ok": True,
            "dry_run": True,
            "count": 0,
            "due": [],
            "reason": "outside_day_window",
            "israel_time": israel_now.isoformat(),
        }

    cutoff = now - timedelta(hours=_NO_REPLY_HOURS)
    due: list[dict] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        for client_id in _ALLOWED_CLIENT_IDS:
            # 1) Candidate leads: this tenant, not booked, no follow-up sent yet.
            r = await client.get(
                f"{_SUPABASE_URL}/rest/v1/maya_watch_leads",
                params={
                    "client_id": f"eq.{client_id}",
                    "booked": "eq.false",
                    "followup_sent_at": "is.null",
                    "select": "id,client_id,phone,name",
                },
                headers=_headers(),
            )
            r.raise_for_status()
            leads = [l for l in r.json() if (l.get("phone") or "").strip()]
            if not leads:
                continue

            by_id = {l["id"]: l for l in leads}
            lead_ids = list(by_id.keys())

            # 2) Latest message per candidate lead (UUIDs are safe in in.(...)).
            mr = await client.get(
                f"{_SUPABASE_URL}/rest/v1/maya_watch_messages",
                params={
                    "lead_id": f"in.({','.join(lead_ids)})",
                    "select": "lead_id,direction,ts",
                    "order": "ts.desc",
                },
                headers=_headers(),
            )
            mr.raise_for_status()
            latest_by_lead: dict[str, dict] = {}
            for m in mr.json():
                lid = m.get("lead_id")
                if lid and lid not in latest_by_lead:  # first seen = newest (ts desc)
                    latest_by_lead[lid] = m

            # 3) Terminal-status exclusion via the `leads` table (per tenant).
            sr = await client.get(
                f"{_SUPABASE_URL}/rest/v1/leads",
                params={
                    "client_id": f"eq.{client_id}",
                    "select": "phone,status",
                },
                headers=_headers(),
            )
            sr.raise_for_status()
            terminal_phones = {
                (row.get("phone") or "").strip()
                for row in sr.json()
                if (row.get("status") or "").strip().lower() in _TERMINAL_STATUSES
            }

            # 4) Apply the no-reply rules.
            for lid, lead in by_id.items():
                latest = latest_by_lead.get(lid)
                if not latest:
                    continue
                # (4) Maya must have spoken last; (6) no customer reply after.
                if (latest.get("direction") or "").lower() != "out":
                    continue
                ts_raw = latest.get("ts")
                if not ts_raw:
                    continue
                last_out = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if last_out.tzinfo is None:
                    last_out = last_out.replace(tzinfo=timezone.utc)
                # (5) older than the silence threshold.
                if last_out > cutoff:
                    continue
                # (8) terminal status guard.
                if (lead.get("phone") or "").strip() in terminal_phones:
                    continue

                hours_silent = round((now - last_out).total_seconds() / 3600, 2)
                due.append({
                    "lead_id":         lid,
                    "client_id":       lead.get("client_id"),
                    "phone":           lead.get("phone"),
                    "name":            lead.get("name") or "",
                    "last_outbound_at": last_out.isoformat(),
                    "hours_silent":    hours_silent,
                    "message":         _FOLLOWUP_MESSAGE,
                })

    return {
        "ok": True,
        "dry_run": True,
        "count": len(due),
        "due": due,
        "israel_time": israel_now.isoformat(),
    }


class NoReplyMarkSentBody(BaseModel):
    lead_id: str
    kind: str = "no_reply_2h"


@router.post("/followup/no-reply-mark-sent")
async def no_reply_mark_sent(
    body: NoReplyMarkSentBody,
    x_followup_secret: str = Header(default=""),
):
    """Stamp maya_watch_leads.followup_sent_at for the no-reply follow-up flow.

    Called by the BPM no-reply Make scenario AFTER a successful Twilio send.
    Writes the SAME field /followup/no-reply-due reads for dedupe — so once
    stamped, the lead stops being returned ("max once"). Deliberately separate
    from /followup/mark-sent (which stamps the `leads` table for the appointment
    flow) so neither flow interferes with the other.
    """
    if _FOLLOWUP_SECRET and x_followup_secret != _FOLLOWUP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    stamped = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Validate the lead exists and belongs to an allowed (BPM) tenant.
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/maya_watch_leads",
            params={"id": f"eq.{body.lead_id}", "select": "id,client_id"},
            headers=_headers(),
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise HTTPException(status_code=404, detail="lead not found")
        if str(rows[0].get("client_id")) not in _ALLOWED_CLIENT_IDS:
            raise HTTPException(status_code=403, detail="lead not in allowed client list")

        # Stamp the dedupe field the no-reply-due endpoint reads. (No schema change;
        # followup_status is left untouched to avoid clobbering native delivery state.)
        pr = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/maya_watch_leads",
            params={"id": f"eq.{body.lead_id}"},
            json={"followup_sent_at": stamped},
            headers={**_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
        )
        if pr.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Supabase patch failed: {pr.text}")

    return {
        "ok": True,
        "lead_id": body.lead_id,
        "kind": body.kind,
        "followup_sent_at": stamped,
    }

"""
app/services/mri_reply_capture.py
==================================
Maya Revenue MRI — capture inbound WhatsApp replies for P1 probes.

Public API
----------
try_capture_probe_reply(customer_phone, business_phone, user_message) -> dict | None
    If this inbound looks like a P1_wa_offhours probe reply, append it to
    the matching mri_probes row and return the updated row.
    Otherwise return None — caller should continue normal flow.

    Never raises. All failures are logged with [MRI-REPLY] tags and the
    function returns None so the production WhatsApp pipeline always
    falls through cleanly when something goes wrong here.

Matching tightness
------------------
A match requires ALL of:
  - probe.probe_type == 'P1_wa_offhours'
  - probe.status     == 'executed'
  - probe.executed_at within the last 72 hours
  - metadata_json.twilio_to   == normalized customer_phone
  - metadata_json.twilio_from == normalized business_phone

Both phone fields must match — this prevents a real customer message
(arriving on the BPM agent's WhatsApp number) from ever being mistaken
for a probe reply (which arrives on the dedicated probe sender).

The most recent matching probe wins (executed_at DESC, limit 1).

Persistence
-----------
On match, the probe row is patched:
  metadata_json.reply_messages    — array, appended (one entry per inbound)
  metadata_json.reply_count       — len(reply_messages)
  metadata_json.reply_captured_at — ISO timestamp of latest capture
  transcript                      — refreshed: probe sent + each reply

The outbound probe body is re-derived from PERSONA_TEMPLATES (the runner
does not currently persist the body text — only body_chars), so the
transcript stays meaningful without modifying the P1 send path.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.services.mri_probe_runner import (
    DEFAULT_PERSONA_KEY,
    PERSONA_TEMPLATES,
)

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_T_PROBES = "mri_probes"
_REST_TIMEOUT = 10.0

_MATCH_WINDOW_HOURS = 72


def _sb_headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _normalize_phone(s: Optional[str]) -> str:
    """Strip whatsapp: prefix, whitespace; add leading + if missing on a clearly-digit string."""
    s = (s or "").replace("whatsapp:", "").strip()
    if s and not s.startswith("+"):
        digits = s.replace(" ", "").replace("-", "")
        if digits.isdigit() and len(digits) >= 10:
            s = "+" + digits
    return s


def _outbound_body_for_probe(probe: dict) -> str:
    """
    Re-derive the persona wa_opening that was sent for this probe.

    Mirrors mri_probe_runner._resolve_persona logic for wa_opening only,
    so we don't depend on a private helper.
    """
    persona_json = probe.get("persona_json") or {}
    explicit = persona_json.get("wa_opening")
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    base_key = persona_json.get("persona_key") or DEFAULT_PERSONA_KEY
    base = PERSONA_TEMPLATES.get(base_key, PERSONA_TEMPLATES[DEFAULT_PERSONA_KEY])
    return base.get("wa_opening", "") or ""


def _build_transcript(probe: dict, all_replies: list[dict]) -> str:
    parts: list[str] = []
    outbound = _outbound_body_for_probe(probe)
    if outbound:
        parts.append(f"Probe sent:\n{outbound}")
    for reply in all_replies:
        body = (reply.get("body") or "").strip()
        ts = reply.get("received_at") or ""
        header = f"Clinic replied at {ts}:" if ts else "Clinic replied:"
        parts.append(f"{header}\n{body}")
    return "\n\n".join(parts)


async def try_capture_probe_reply(
    customer_phone: str,
    business_phone: str,
    user_message: str,
) -> Optional[dict]:
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        return None

    cust = _normalize_phone(customer_phone)
    biz = _normalize_phone(business_phone)
    if not cust or not biz:
        return None

    logger.info(
        "[MRI-REPLY] inbound_seen customer=%s business=%s msg_chars=%d",
        cust, biz, len(user_message or ""),
    )

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_MATCH_WINDOW_HOURS)).isoformat()

    try:
        async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
            r = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_T_PROBES}",
                params={
                    "probe_type":                  "eq.P1_wa_offhours",
                    "status":                      "eq.executed",
                    "executed_at":                 f"gte.{cutoff}",
                    "metadata_json->>twilio_to":   f"eq.{cust}",
                    "metadata_json->>twilio_from": f"eq.{biz}",
                    "select":                      "*",
                    "order":                       "executed_at.desc",
                    "limit":                       "1",
                },
                headers=_sb_headers("count=none"),
            )
        if r.status_code >= 400:
            logger.error(
                "[MRI-REPLY] capture_error lookup_failed status=%s body=%s",
                r.status_code, r.text,
            )
            return None
        rows = r.json()
    except Exception as exc:
        logger.error("[MRI-REPLY] capture_error lookup_exception error=%s", exc)
        return None

    if not rows:
        logger.info("[MRI-REPLY] no_match customer=%s business=%s", cust, biz)
        return None

    probe = rows[0]
    logger.info(
        "[MRI-REPLY] matched_probe probe_id=%s scan_id=%s executed_at=%s",
        probe.get("id"), probe.get("scan_id"), probe.get("executed_at"),
    )

    md = dict(probe.get("metadata_json") or {})
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = md.get("reply_messages")
    if not isinstance(existing, list):
        existing = []

    new_reply = {
        "received_at": now_iso,
        "from":        cust,
        "to":          biz,
        "body":        user_message or "",
    }
    all_replies = existing + [new_reply]

    md["reply_messages"]    = all_replies
    md["reply_count"]       = len(all_replies)
    md["reply_captured_at"] = now_iso

    transcript = _build_transcript(probe, all_replies)

    body = {"metadata_json": md}
    if transcript:
        body["transcript"] = transcript

    try:
        async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
            r = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_T_PROBES}",
                params={"id": f"eq.{probe['id']}"},
                json=body,
                headers=_sb_headers(),
            )
        if r.status_code >= 400:
            logger.error(
                "[MRI-REPLY] capture_error persist_failed probe_id=%s status=%s body=%s",
                probe.get("id"), r.status_code, r.text,
            )
            return None
        updated = r.json()
        updated_row = updated[0] if updated else probe
    except Exception as exc:
        logger.error(
            "[MRI-REPLY] capture_error persist_exception probe_id=%s error=%s",
            probe.get("id"), exc,
        )
        return None

    logger.info(
        "[MRI-REPLY] captured probe_id=%s reply_count=%d msg_chars=%d",
        probe.get("id"), len(all_replies), len(user_message or ""),
    )
    return updated_row

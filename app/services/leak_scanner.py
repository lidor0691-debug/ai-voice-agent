"""
app/services/leak_scanner.py
==============================
Conversion Leak Detection — deterministic scan engine for Maya's Daily Priorities.

Runs as a daily batch job (cron via Make.com).
Scans leads per client and detects conversion leaks.

Signals implemented:
  1. noshow_not_reactivated — appointment passed, no follow-up
  2. conversation_drop — customer's last WhatsApp unanswered >48h

Deferred:
  3. high_intent_no_booking — needs metadata.customer_phone on insights first

Public API
----------
scan_all(client_ids: list[str]) -> dict
    Runs all detectors for each client, saves new signals, auto-resolves stale ones.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_TABLE = "conversion_leak_signals"


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime. Returns None on failure."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _hours_since(ts_str: str) -> int:
    dt = _parse_ts(ts_str)
    if not dt:
        return 0
    return int((_now() - dt).total_seconds() / 3600)


def _format_date_he(ts_str: str) -> str:
    """Format ISO timestamp to dd/mm HH:MM for Hebrew display."""
    dt = _parse_ts(ts_str)
    if not dt:
        return ts_str or ""
    return dt.strftime("%d/%m %H:%M")


# ── Detectors ────────────────────────────────────────────────────────────────


async def _detect_noshow(
    client: httpx.AsyncClient, client_id: str
) -> list[dict]:
    """
    Signal 1: No-show not reactivated.
    appointment_at is 4h–14d in the past, status != closed,
    no customer activity after appointment time.
    """
    now = _now()
    cutoff_recent = (now - timedelta(hours=4)).isoformat()
    cutoff_old = (now - timedelta(days=14)).isoformat()

    resp = await client.get(
        f"{_SUPABASE_URL}/rest/v1/leads",
        params={
            "client_id": f"eq.{client_id}",
            "appointment_at": f"lt.{cutoff_recent}",
            "status": "not.eq.closed",
            "select": "id,name,phone,appointment_at,status,last_whatsapp_inbound_at",
        },
        headers=_headers(),
    )
    resp.raise_for_status()
    leads = resp.json()

    signals = []
    for lead in leads:
        appt = _parse_ts(lead.get("appointment_at"))
        if not appt:
            continue
        # Staleness guard: skip appointments older than 14 days
        if appt < _parse_ts(cutoff_old):
            continue

        # Check if any activity happened AFTER the appointment
        last_wa = _parse_ts(lead.get("last_whatsapp_inbound_at"))
        if last_wa and last_wa > appt:
            continue  # Customer was active after appointment — not a no-show leak

        signals.append({
            "client_id": client_id,
            "lead_id": lead["id"],
            "lead_phone": lead["phone"],
            "lead_name": lead.get("name"),
            "signal_type": "noshow_not_reactivated",
            "detail": {
                "appointment_at": lead["appointment_at"],
                "hours_since": _hours_since(lead["appointment_at"]),
                "lead_status": lead.get("status"),
            },
            "suggested_action": (
                f"לא הגיע/ה לתור ב-{_format_date_he(lead['appointment_at'])}"
                " — שווה לשלוח הודעה לקביעה מחדש"
            ),
        })

    logger.info(
        "[LEAK SCAN] noshow_not_reactivated: client=%s found=%d",
        client_id[:8], len(signals),
    )
    return signals


async def _detect_conversation_drop(
    client: httpx.AsyncClient, client_id: str
) -> list[dict]:
    """
    Signal 2: Conversation drop — customer sent last WhatsApp message >48h ago,
    no reply from business.
    """
    now = _now()

    # Fetch open leads for this client
    resp = await client.get(
        f"{_SUPABASE_URL}/rest/v1/leads",
        params={
            "client_id": f"eq.{client_id}",
            "status": "in.(new,contacted)",
            "select": "id,name,phone",
        },
        headers=_headers(),
    )
    resp.raise_for_status()
    leads = resp.json()

    if not leads:
        return []

    signals = []
    for lead in leads:
        phone = lead.get("phone")
        if not phone:
            continue

        # Fetch conversation for this phone
        conv_resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/whatsapp_conversations",
            params={
                "phone": f"eq.{phone}",
                "select": "messages_json,updated_at",
                "limit": "1",
            },
            headers=_headers(),
        )
        conv_resp.raise_for_status()
        convos = conv_resp.json()

        if not convos:
            continue

        convo = convos[0]
        raw_messages = convo.get("messages_json")

        # Normalize — same logic as whatsapp_history.py
        if isinstance(raw_messages, str):
            try:
                raw_messages = json.loads(raw_messages)
            except (json.JSONDecodeError, ValueError):
                continue
        if not isinstance(raw_messages, list) or not raw_messages:
            continue

        last_msg = raw_messages[-1]
        if last_msg.get("role") != "user":
            continue  # Last message was from assistant — not a drop

        # Use conversation updated_at as proxy for last message time
        # (individual messages don't have timestamps)
        updated_at = _parse_ts(convo.get("updated_at"))
        if not updated_at:
            continue

        hours = (now - updated_at).total_seconds() / 3600
        if hours < 48:
            continue  # Too recent

        content_preview = (last_msg.get("content") or "")[:100]
        signals.append({
            "client_id": client_id,
            "lead_id": lead["id"],
            "lead_phone": lead["phone"],
            "lead_name": lead.get("name"),
            "signal_type": "conversation_drop",
            "detail": {
                "last_customer_message": content_preview,
                "hours_since": int(hours),
                "updated_at": convo["updated_at"],
            },
            "suggested_action": "הלקוח/ה שלח/ה הודעה ולא קיבל/ה מענה — כדאי לחזור אליו/ה",
        })

    logger.info(
        "[LEAK SCAN] conversation_drop: client=%s found=%d",
        client_id[:8], len(signals),
    )
    return signals


# ── Save & Resolve ───────────────────────────────────────────────────────────


async def _save_signals(
    client: httpx.AsyncClient, signals: list[dict]
) -> int:
    """
    Insert new signals. Skips duplicates via unique constraint
    (client_id, lead_id, signal_type, scan_date).
    Returns count of newly created signals.
    """
    created = 0
    today = _now().strftime("%Y-%m-%d")

    for signal in signals:
        payload = {
            "client_id": signal["client_id"],
            "lead_id": signal["lead_id"],
            "lead_phone": signal["lead_phone"],
            "lead_name": signal.get("lead_name"),
            "signal_type": signal["signal_type"],
            "detail": signal.get("detail", {}),
            "suggested_action": signal.get("suggested_action"),
            "scan_date": today,
        }
        try:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                json=payload,
                headers={**_headers(), "Prefer": "return=minimal,resolution=ignore-duplicates"},
            )
            if resp.status_code == 201:
                created += 1
            # 409 or ignored duplicate → skip silently
        except Exception as exc:
            logger.error(
                "[LEAK SCAN] Failed to save signal type=%s lead=%s: %s",
                signal["signal_type"], signal.get("lead_id", "?")[:8], exc,
            )

    return created


async def _auto_resolve(client: httpx.AsyncClient, client_id: str) -> int:
    """
    Mark open signals as 'resolved' if the lead has progressed
    to 'scheduled' or 'closed'.
    """
    # Fetch open signals for this client
    resp = await client.get(
        f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
        params={
            "client_id": f"eq.{client_id}",
            "status": "eq.open",
            "select": "id,lead_id",
        },
        headers=_headers(),
    )
    resp.raise_for_status()
    open_signals = resp.json()

    if not open_signals:
        return 0

    # Collect unique lead_ids
    lead_ids = list({s["lead_id"] for s in open_signals})

    # Fetch current status for these leads
    # Supabase REST: id=in.(uuid1,uuid2,...)
    id_list = ",".join(lead_ids)
    resp = await client.get(
        f"{_SUPABASE_URL}/rest/v1/leads",
        params={
            "id": f"in.({id_list})",
            "select": "id,status",
        },
        headers=_headers(),
    )
    resp.raise_for_status()
    leads = resp.json()

    resolved_leads = {
        l["id"] for l in leads
        if l.get("status") in ("scheduled", "closed")
    }

    if not resolved_leads:
        return 0

    # Resolve signals whose leads have progressed
    resolved = 0
    now_iso = _now().isoformat()
    for signal in open_signals:
        if signal["lead_id"] not in resolved_leads:
            continue
        try:
            resp = await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                params={"id": f"eq.{signal['id']}"},
                json={"status": "resolved", "acted_at": now_iso},
                headers={**_headers(), "Prefer": "return=minimal"},
            )
            resp.raise_for_status()
            resolved += 1
        except Exception as exc:
            logger.error(
                "[LEAK SCAN] Failed to resolve signal %s: %s",
                signal["id"][:8], exc,
            )

    logger.info(
        "[LEAK SCAN] auto_resolve: client=%s resolved=%d",
        client_id[:8], resolved,
    )
    return resolved


# ── Orchestrator ─────────────────────────────────────────────────────────────


async def scan_all(client_ids: list[str]) -> dict:
    """
    Run all detectors for each client. Save new signals. Auto-resolve stale ones.
    Returns summary dict.
    """
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        logger.warning("[LEAK SCAN] Supabase not configured — skipping")
        return {"error": "Supabase not configured"}

    total_created = 0
    total_resolved = 0
    scanned = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        for client_id in client_ids:
            client_id = client_id.strip()
            if not client_id:
                continue

            scanned += 1
            try:
                # Detect
                noshow = await _detect_noshow(client, client_id)
                drops = await _detect_conversation_drop(client, client_id)

                all_signals = noshow + drops

                # Save
                created = await _save_signals(client, all_signals)
                total_created += created

                # Auto-resolve
                resolved = await _auto_resolve(client, client_id)
                total_resolved += resolved

                logger.info(
                    "[LEAK SCAN] client=%s detected=%d created=%d resolved=%d",
                    client_id[:8], len(all_signals), created, resolved,
                )

            except Exception as exc:
                logger.error(
                    "[LEAK SCAN] Failed scan for client=%s: %s",
                    client_id[:8], exc,
                )

    result = {
        "scanned_clients": scanned,
        "signals_created": total_created,
        "signals_resolved": total_resolved,
        "scanned_at": _now().isoformat(),
    }
    logger.info("[LEAK SCAN] Complete: %s", result)
    return result

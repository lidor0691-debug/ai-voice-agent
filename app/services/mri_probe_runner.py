"""
app/services/mri_probe_runner.py
=================================
Maya Revenue MRI — probe execution (MVP, P1 + P2 only).

Two probe types are supported in this MVP:

  P1_wa_offhours
    Send a single WhatsApp message to the clinic's WA number from a
    Maya-controlled probe sender. Records Twilio SID + status.
    Reply analysis is NOT implemented in this MVP.

  P2_call_peak
    Place an outbound Twilio call to the clinic's voice line and play
    a scripted persona opening via inline TwiML <Say>. Records call
    SID + Twilio status. Recording/transcription is NOT wired here —
    `transcript` stays NULL. A future phase adds the recording
    webhook + LLM scoring.

All other probe types raise ProbeRunnerError.

Inputs come from the loaded mri_probes row + the parent mri_scans row.
Per-scan target numbers must be set on mri_scans.metadata:

    mri_scans.metadata.target_whatsapp  → P1 'to' number (E.164)
    mri_scans.metadata.target_phone     → P2 'to' number (E.164)

Sender numbers come from environment:
    MRI_PROBE_WHATSAPP_FROM   → P1 'from' (E.164, no whatsapp: prefix)
    MRI_PROBE_VOICE_FROM      → P2 'from' (E.164)
    Both fall back to TWILIO_PHONE_NUMBER if unset.

Twilio access matches app/routes/action_api.py — direct twilio.rest.Client
usage wrapped in asyncio.to_thread. No new helper introduced.

Supabase access matches the rest of the backend — service-key + httpx REST.
The service key bypasses RLS by design.

Logging tags:
    [MRI-PROBE] run_start
    [MRI-PROBE] wa_sent
    [MRI-PROBE] call_complete
    [MRI-PROBE] probe_complete
    [MRI-PROBE] probe_error
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_PROBE_WA_FROM = (
    os.getenv("MRI_PROBE_WHATSAPP_FROM", "") or os.getenv("TWILIO_PHONE_NUMBER", "")
).strip()
_PROBE_VOICE_FROM = (
    os.getenv("MRI_PROBE_VOICE_FROM", "") or os.getenv("TWILIO_PHONE_NUMBER", "")
).strip()

_T_PROBES = "mri_probes"
_T_SCANS = "mri_scans"
_REST_TIMEOUT = 10.0


class ProbeRunnerError(Exception):
    """Validation or configuration error preventing probe execution."""


class ProbeAlreadyExecutedError(Exception):
    """Probe has already been executed (executed_at is set) — re-run is blocked."""


# ─────────────────────────────────────────────────────────────
# Persona templates — opening lines used by P1 (WA) and P2 (voice).
# Probes can override per-row via persona_json: either pick a key
# ({"persona_key": "sara_full_arch"}) or supply explicit overrides
# ({"name": "...", "wa_opening": "...", "voice_opening": "..."}).
# ─────────────────────────────────────────────────────────────

PERSONA_TEMPLATES: dict[str, dict[str, str]] = {
    "sara_full_arch": {
        "name": "Sara",
        "wa_opening": (
            "Hi, my name is Sara. I'm 47 and I've been thinking about "
            "full-arch implants for my upper jaw. Could I ask a few "
            "questions and possibly book a consultation?"
        ),
        "voice_opening": (
            "Hello, my name is Sara. I'm calling because I'm interested in "
            "full-arch implants for the upper jaw. I would like to know if "
            "you treat cases like this and how I can book a consultation. "
            "Thank you."
        ),
    },
    "budget_sensitive_implant": {
        "name": "David",
        "wa_opening": (
            "Hello, I'm looking into a dental implant but I want to "
            "understand the cost first. Do you offer financing? What is "
            "a realistic budget for a single implant?"
        ),
        "voice_opening": (
            "Hi, I'm calling about a dental implant. Before I come in I "
            "want to ask about pricing and whether you offer financing. "
            "Could someone get back to me about that?"
        ),
    },
}

DEFAULT_PERSONA_KEY = "sara_full_arch"


def _resolve_persona(persona_json: Optional[dict]) -> dict[str, str]:
    """
    Resolve effective persona for this probe.

    Picks a base template from PERSONA_TEMPLATES (default: sara_full_arch),
    then applies any explicit overrides from persona_json: name,
    wa_opening, voice_opening.
    """
    persona_json = persona_json or {}
    base_key = persona_json.get("persona_key") or DEFAULT_PERSONA_KEY
    base = PERSONA_TEMPLATES.get(base_key, PERSONA_TEMPLATES[DEFAULT_PERSONA_KEY]).copy()
    for k in ("name", "wa_opening", "voice_opening"):
        v = persona_json.get(k)
        if isinstance(v, str) and v.strip():
            base[k] = v
    return base


# ─────────────────────────────────────────────────────────────
# Supabase helpers
# ─────────────────────────────────────────────────────────────

def _sb_headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


async def _load_probe_with_scan(probe_id: str) -> tuple[dict, dict]:
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        raise ProbeRunnerError("Supabase env not configured")

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_PROBES}",
            params={"id": f"eq.{probe_id}", "select": "*"},
            headers=_sb_headers("count=none"),
        )
        if r.status_code >= 400:
            raise ProbeRunnerError(f"probe lookup failed: {r.status_code} {r.text}")
        rows = r.json()
        if not rows:
            raise ProbeRunnerError("probe not found")
        probe = rows[0]

        scan_id = probe["scan_id"]
        r2 = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_SCANS}",
            params={"id": f"eq.{scan_id}", "select": "*"},
            headers=_sb_headers("count=none"),
        )
        if r2.status_code >= 400:
            raise ProbeRunnerError(f"scan lookup failed: {r2.status_code} {r2.text}")
        scans = r2.json()
        if not scans:
            raise ProbeRunnerError("parent scan not found")
        scan = scans[0]

    return probe, scan


async def _persist_probe_result(
    probe_id: str,
    *,
    status: str,
    metadata_json: dict,
    transcript: Optional[str] = None,
) -> dict:
    body: dict = {
        "status": status,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "metadata_json": metadata_json,
    }
    if transcript is not None:
        body["transcript"] = transcript

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        r = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_T_PROBES}",
            params={"id": f"eq.{probe_id}"},
            json=body,
            headers=_sb_headers(),
        )
        if r.status_code >= 400:
            logger.error(
                "[MRI-PROBE] probe_error probe_id=%s persist_failed status=%s body=%s",
                probe_id, r.status_code, r.text,
            )
            raise ProbeRunnerError(f"persist failed: {r.status_code} {r.text}")
        rows = r.json()
        return rows[0] if rows else {}


# ─────────────────────────────────────────────────────────────
# P1 — WhatsApp off-hours
# ─────────────────────────────────────────────────────────────

async def _run_p1_wa_offhours(probe: dict, scan: dict) -> dict:
    if not _TWILIO_SID or not _TWILIO_TOKEN:
        raise ProbeRunnerError("Twilio not configured")
    if not _PROBE_WA_FROM:
        raise ProbeRunnerError(
            "MRI_PROBE_WHATSAPP_FROM (or TWILIO_PHONE_NUMBER) not set"
        )

    target = ((scan.get("metadata") or {}).get("target_whatsapp") or "").strip()
    if not target:
        raise ProbeRunnerError("scan.metadata.target_whatsapp not set")

    persona = _resolve_persona(probe.get("persona_json") or {})
    body = persona["wa_opening"]
    sent_at = datetime.now(timezone.utc).isoformat()

    try:
        from twilio.rest import Client
        client = Client(_TWILIO_SID, _TWILIO_TOKEN)
        msg = await asyncio.to_thread(
            lambda: client.messages.create(
                from_=f"whatsapp:{_PROBE_WA_FROM}",
                to=f"whatsapp:{target}",
                body=body,
            )
        )
    except Exception as exc:
        logger.error(
            "[MRI-PROBE] probe_error probe_id=%s probe_type=P1_wa_offhours error=%s",
            probe.get("id"), exc,
        )
        return await _persist_probe_result(
            probe_id=probe["id"],
            status="error",
            metadata_json={
                "probe_type": "P1_wa_offhours",
                "persona_name": persona["name"],
                "twilio_from": _PROBE_WA_FROM,
                "twilio_to": target,
                "sent_at": sent_at,
                "error": str(exc),
            },
        )

    logger.info(
        "[MRI-PROBE] wa_sent probe_id=%s scan_id=%s to=%s sid=%s persona=%s",
        probe["id"], scan["id"], target,
        getattr(msg, "sid", None), persona["name"],
    )

    return await _persist_probe_result(
        probe_id=probe["id"],
        status="executed",
        metadata_json={
            "probe_type":   "P1_wa_offhours",
            "persona_name": persona["name"],
            "twilio_from":  _PROBE_WA_FROM,
            "twilio_to":    target,
            "twilio_sid":   getattr(msg, "sid", None),
            "twilio_status": getattr(msg, "status", None),
            "outbound_body": body,
            "body_chars":   len(body),
            "sent_at":      sent_at,
        },
    )


# ─────────────────────────────────────────────────────────────
# P2 — outbound voice peak-hour
# ─────────────────────────────────────────────────────────────

def _build_p2_twiml(persona: dict[str, str]) -> str:
    text = (
        persona["voice_opening"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f'<Response><Say voice="alice">{text}</Say></Response>'


async def _run_p2_call_peak(probe: dict, scan: dict) -> dict:
    if not _TWILIO_SID or not _TWILIO_TOKEN:
        raise ProbeRunnerError("Twilio not configured")
    if not _PROBE_VOICE_FROM:
        raise ProbeRunnerError(
            "MRI_PROBE_VOICE_FROM (or TWILIO_PHONE_NUMBER) not set"
        )

    target = ((scan.get("metadata") or {}).get("target_phone") or "").strip()
    if not target:
        raise ProbeRunnerError("scan.metadata.target_phone not set")

    persona = _resolve_persona(probe.get("persona_json") or {})
    twiml = _build_p2_twiml(persona)
    placed_at = datetime.now(timezone.utc).isoformat()

    try:
        from twilio.rest import Client
        client = Client(_TWILIO_SID, _TWILIO_TOKEN)
        call = await asyncio.to_thread(
            lambda: client.calls.create(
                to=target,
                from_=_PROBE_VOICE_FROM,
                twiml=twiml,
            )
        )
    except Exception as exc:
        logger.error(
            "[MRI-PROBE] probe_error probe_id=%s probe_type=P2_call_peak error=%s",
            probe.get("id"), exc,
        )
        return await _persist_probe_result(
            probe_id=probe["id"],
            status="error",
            metadata_json={
                "probe_type":   "P2_call_peak",
                "persona_name": persona["name"],
                "twilio_from":  _PROBE_VOICE_FROM,
                "twilio_to":    target,
                "placed_at":    placed_at,
                "error":        str(exc),
            },
        )

    logger.info(
        "[MRI-PROBE] call_complete probe_id=%s scan_id=%s to=%s sid=%s "
        "persona=%s twilio_status=%s",
        probe["id"], scan["id"], target,
        getattr(call, "sid", None), persona["name"],
        getattr(call, "status", None),
    )

    return await _persist_probe_result(
        probe_id=probe["id"],
        status="executed",
        metadata_json={
            "probe_type":      "P2_call_peak",
            "persona_name":    persona["name"],
            "twilio_from":     _PROBE_VOICE_FROM,
            "twilio_to":       target,
            "twilio_call_sid": getattr(call, "sid", None),
            "twilio_status":   getattr(call, "status", None),
            "twiml_chars":     len(twiml),
            "placed_at":       placed_at,
            "transcript_capture": "deferred_no_recording_webhook",
        },
        transcript=None,
    )


# ─────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────

_DISPATCH = {
    "P1_wa_offhours": _run_p1_wa_offhours,
    "P2_call_peak":   _run_p2_call_peak,
}

SUPPORTED_PROBE_TYPES = tuple(_DISPATCH.keys())


async def run_probe(probe_id: str) -> dict:
    """
    Load probe + scan, dispatch by probe_type, persist result, return updated row.

    Raises ProbeRunnerError on configuration / validation / not-found failures.
    External Twilio errors are caught and recorded as status='error' in
    metadata_json.error rather than raising — so a row always reflects the
    attempt.
    """
    logger.info("[MRI-PROBE] run_start probe_id=%s", probe_id)

    probe, scan = await _load_probe_with_scan(probe_id)

    if probe.get("executed_at"):
        logger.warning(
            "[MRI-PROBE] duplicate_run_blocked probe_id=%s executed_at=%s status=%s",
            probe_id, probe.get("executed_at"), probe.get("status"),
        )
        raise ProbeAlreadyExecutedError(
            f"probe already executed at {probe.get('executed_at')}"
        )

    probe_type = probe.get("probe_type") or ""
    if probe_type not in _DISPATCH:
        raise ProbeRunnerError(
            f"unsupported probe_type: {probe_type!r} "
            f"(MVP supports: {list(_DISPATCH.keys())})"
        )

    runner = _DISPATCH[probe_type]
    result = await runner(probe, scan)

    logger.info(
        "[MRI-PROBE] probe_complete probe_id=%s probe_type=%s status=%s",
        probe_id, probe_type, result.get("status"),
    )
    return result

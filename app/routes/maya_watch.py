"""
Maya Watch route — minimal endpoints for the thin-slice validation flow.

Endpoints:
    POST /maya-watch/inbound                 — webhook (Twilio form OR JSON)
    POST /maya-watch/twilio-status           — Twilio outbound delivery callback
    POST /maya-watch/tick                    — manual scan + act
    GET  /maya-watch/leads                   — list all leads + outcomes
    GET  /maya-watch/leads/{phone}           — single lead
    POST /maya-watch/leads/{phone}/mark-booked — manual booking confirmation
    GET  /maya-watch/health                  — alive

For wiring real Twilio: point your WhatsApp Sandbox / Business webhook at
    POST https://<host>/maya-watch/inbound
Twilio sends application/x-www-form-urlencoded with From / Body / ProfileName.
For testing without Twilio: POST JSON  {"phone": "+9725...", "body": "..."}

Delivery observability: when BASE_URL env is set, outbound messages are sent
with a status_callback pointing at /maya-watch/twilio-status. Twilio then
POSTs delivery state updates (queued → sent → delivered, or failed /
undelivered with an ErrorCode like 63016).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.services import maya_watch as svc

logger = logging.getLogger(__name__)
router = APIRouter()

# Empty TwiML — what Twilio expects from a webhook when there's nothing to
# say back. Returning JSON triggers Twilio warning 12300 "Invalid Content-Type".
_EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _twiml_ok() -> Response:
    return Response(content=_EMPTY_TWIML, media_type="application/xml")


def _is_twilio_form(content_type: str) -> bool:
    return (
        "application/x-www-form-urlencoded" in content_type
        or "multipart/form-data" in content_type
    )


# ── Stage 5 — internal-key gate for private endpoints ────────────────────
# Reads MAYA_WATCH_INTERNAL_KEY from env (set on both Railway and Vercel).
# The Next.js dashboard adds X-Maya-Watch-Key on every server-side fetch;
# the browser never sees the key (server components only).
#
# Apply via `dependencies=[Depends(_require_internal_key)]` on the
# private routes below. The Twilio webhooks (/inbound, /twilio-status)
# and /health are deliberately exempt — Twilio cannot send custom
# headers, and /health is used for uptime probes.

_INTERNAL_KEY = os.getenv("MAYA_WATCH_INTERNAL_KEY", "").strip()


async def _require_internal_key(
    x_maya_watch_key: Optional[str] = Header(default=None, alias="X-Maya-Watch-Key"),
) -> None:
    """Reject any private-endpoint request that doesn't carry the matching key.

    Fail-closed semantics: if the env var isn't configured on the server,
    we raise 500 rather than silently letting requests through. Better to
    notice the misconfiguration loudly than to leak data.
    """
    if not _INTERNAL_KEY:
        logger.error("[MAYA-WATCH] MAYA_WATCH_INTERNAL_KEY not configured — denying private endpoint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MAYA_WATCH_INTERNAL_KEY not configured",
        )
    if not x_maya_watch_key or x_maya_watch_key != _INTERNAL_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Maya-Watch-Key",
        )


# ── Stage 6 — Twilio signature verification (observe-only by default) ────
# Verifies X-Twilio-Signature on the public Twilio webhooks (/inbound +
# /twilio-status). Two modes via MAYA_WATCH_VERIFY_TWILIO_SIGNATURE:
#
#   false / unset → observe-only: log [MAYA-WATCH] sig_check ok=true/false
#                   for every request, never reject. Use this for the first
#                   24-48h to prove URL reconstruction matches what Twilio
#                   actually signs.
#   true          → enforce: reject missing/invalid signature with 403.
#                   If TWILIO_AUTH_TOKEN is missing, return 500 — refuse to
#                   silently fail-open when enforcement is supposed to be on.
#
# URL reconstruction uses BASE_URL (same env we tell Twilio in
# status_callback), so signing key, signing URL, and verifier URL all
# share the same source of truth. No proxy header guesswork in the
# happy path.
#
# Form parsing: parses the form ONCE in the dependency and stashes it on
# request.state.form so the route handler can reuse it without
# consuming the body twice.


def _twilio_url(request: Request) -> str:
    """Reconstruct the URL Twilio signed against, preferring BASE_URL.

    BASE_URL is what we configure Twilio to call (status_callback uses it
    too — see app/services/maya_watch.py:_send_whatsapp). Symmetry: as
    long as the value of BASE_URL on Railway equals the URL configured in
    the Twilio Console, signature URLs match exactly.

    Forwarded-header fallback handles the case where BASE_URL is unset
    (dev / local) — Railway sets x-forwarded-proto and x-forwarded-host
    correctly behind its edge proxy.
    """
    base = os.getenv("BASE_URL", "").strip().rstrip("/")
    if base:
        qs = f"?{request.url.query}" if request.url.query else ""
        return f"{base}{request.url.path}{qs}"
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    qs = f"?{request.url.query}" if request.url.query else ""
    return f"{proto}://{host}{request.url.path}{qs}"


async def _verify_twilio_signature(request: Request) -> None:
    """Verify the X-Twilio-Signature header. Observe-only unless flag is on.

    Side effect: parses the form (when content-type is form-encoded) and
    stashes it on request.state.form for the route handler to reuse —
    Starlette's request body is single-shot, so this avoids double-read.
    """
    enforce = os.getenv("MAYA_WATCH_VERIFY_TWILIO_SIGNATURE", "").strip().lower() == "true"
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    path = request.url.path
    mode = "enforce" if enforce else "observe"

    # Parse form once if this looks like a Twilio request; otherwise store
    # None so the JSON test path isn't surprised by an empty FormData.
    content_type = request.headers.get("content-type", "")
    is_form = (
        "application/x-www-form-urlencoded" in content_type
        or "multipart/form-data" in content_type
    )
    if is_form:
        form = await request.form()
        request.state.form = form
    else:
        request.state.form = None
        # JSON test path — never a Twilio request, no signature to check.
        logger.info("[MAYA-WATCH] sig_check no_form ok=skip path=%s mode=%s", path, mode)
        return

    if not auth_token:
        if enforce:
            logger.error(
                "[MAYA-WATCH] sig_check cannot_verify path=%s mode=enforce — TWILIO_AUTH_TOKEN missing",
                path,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="signature verification unavailable",
            )
        logger.warning(
            "[MAYA-WATCH] sig_check cannot_verify path=%s mode=observe — TWILIO_AUTH_TOKEN missing",
            path,
        )
        return

    signature = request.headers.get("x-twilio-signature", "")
    if not signature:
        if enforce:
            logger.warning("[MAYA-WATCH] sig_check sig=missing ok=false path=%s mode=enforce", path)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="missing X-Twilio-Signature",
            )
        logger.warning("[MAYA-WATCH] sig_check sig=missing ok=false path=%s mode=observe", path)
        return

    url = _twilio_url(request)
    params = {k: str(v) for k, v in (form or {}).items()}

    # Local import to keep the cold-path off the module load.
    from twilio.request_validator import RequestValidator
    validator = RequestValidator(auth_token)
    ok = validator.validate(url, params, signature)

    if ok:
        logger.info("[MAYA-WATCH] sig_check ok=true path=%s mode=%s", path, mode)
        return

    if enforce:
        logger.warning(
            "[MAYA-WATCH] sig_check sig=invalid ok=false path=%s mode=enforce url=%s",
            path, url,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid X-Twilio-Signature",
        )
    logger.warning(
        "[MAYA-WATCH] sig_check sig=invalid ok=false path=%s mode=observe url=%s",
        path, url,
    )


@router.post("/maya-watch/inbound", dependencies=[Depends(_verify_twilio_signature)])
async def inbound(request: Request):
    """Accept Twilio form-encoded WhatsApp webhook OR plain JSON for testing.

    Tenant scoping (Stage 4):
      - Twilio path: extract `To` and resolve to (agent_id, client_id) via
        agents_config (whatsapp_number/phone_number lookup, then
        MAYA_WATCH_DEFAULT_AGENT_ID fallback for the shared sandbox).
      - JSON path: caller may pass `agent_id` and `client_id` directly
        (admin test path); when absent, applies the same resolver to a
        provided `to` field, or falls through to (None, None).

    Twilio callers get an empty TwiML (XML) response — silences the
    Twilio "12300 Invalid Content-Type" warning. JSON callers get JSON
    (preserves the manual / curl test path).

    Stage 6 — `_verify_twilio_signature` runs first. In observe mode it
    only logs; in enforce mode it returns 403 on missing/invalid sig.
    The dependency parses the form once and stashes it on
    request.state.form so we don't double-read the request body.
    """
    content_type = request.headers.get("content-type", "")
    is_twilio = _is_twilio_form(content_type)
    phone = ""
    body = ""
    name: Optional[str] = None
    to_number = ""
    explicit_agent_id: Optional[str] = None
    explicit_client_id: Optional[str] = None

    if is_twilio:
        # Reuse the form parsed in _verify_twilio_signature; fall back if
        # the dep didn't run (e.g. tests bypassing dependencies).
        form = getattr(request.state, "form", None)
        if form is None:
            form = await request.form()
        phone = svc.normalize_phone(str(form.get("From") or ""))
        body = str(form.get("Body") or "").strip()
        n = str(form.get("ProfileName") or "").strip()
        name = n or None
        to_number = str(form.get("To") or "").strip()
    else:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(400, "expected JSON or form-encoded payload")
        phone = svc.normalize_phone(str(data.get("phone", "")))
        body = str(data.get("body", "")).strip()
        n = data.get("name")
        name = str(n).strip() if isinstance(n, str) and n.strip() else None
        to_number = str(data.get("to", "")).strip()
        explicit_agent_id = (str(data.get("agent_id", "")).strip() or None)
        explicit_client_id = (str(data.get("client_id", "")).strip() or None)

    if not phone or not body:
        raise HTTPException(400, "phone and body are required")

    # Resolve tenant. Explicit JSON values win; otherwise route via To-number.
    if explicit_agent_id or explicit_client_id:
        agent_id, client_id = explicit_agent_id, explicit_client_id
    else:
        agent_id, client_id = await svc.resolve_agent_for_to(to_number)

    lead = await svc.register_inbound(
        phone, body, name=name,
        client_id=client_id, agent_id=agent_id,
    )
    if is_twilio:
        # Empty TwiML — content_type=application/xml. Twilio is happy.
        return _twiml_ok()
    return {
        "ok": True,
        "phone": phone,
        "status": svc.derive_status(lead),
        "client_id": client_id,
        "agent_id": agent_id,
    }


@router.post("/maya-watch/twilio-status", dependencies=[Depends(_verify_twilio_signature)])
async def twilio_status(request: Request):
    """Twilio outbound delivery callback.

    Twilio POSTs application/x-www-form-urlencoded with at least:
        MessageSid, MessageStatus, From, To
    and on failure also:
        ErrorCode, ErrorMessage

    We log every callback and update the matching lead's followup_status
    in memory so /maya-watch/leads can surface real delivery state.

    Always returns empty TwiML (Twilio expects an XML response).

    Stage 6 — same `_verify_twilio_signature` dep as /inbound. Form is
    reused from request.state to avoid double-reading the request body.
    """
    form = getattr(request.state, "form", None)
    if form is None:
        form = await request.form()
    sid = str(form.get("MessageSid") or "").strip()
    status = str(form.get("MessageStatus") or "").strip()
    error_code = str(form.get("ErrorCode") or "").strip() or None
    error_message = str(form.get("ErrorMessage") or "").strip() or None
    from_ = str(form.get("From") or "").strip()
    to = str(form.get("To") or "").strip()

    logger.info(
        "[MAYA-WATCH] status_callback sid=%s status=%s error_code=%s error_message=%r from=%s to=%s",
        sid or "-", status or "-", error_code or "-", error_message or "", from_ or "-", to or "-",
    )

    if sid and status:
        await svc.record_delivery_status(sid, status, error_code, error_message)

    return _twiml_ok()


@router.post("/maya-watch/tick", dependencies=[Depends(_require_internal_key)])
async def tick_endpoint(client_id: Optional[str] = Query(default=None)):
    """Manual scan. When client_id is omitted, scans all tenants (admin).
    Internal-key gated (Stage 5)."""
    return await svc.tick(client_id=client_id)


@router.get("/maya-watch/leads", dependencies=[Depends(_require_internal_key)])
async def list_leads(client_id: Optional[str] = Query(default=None)):
    """When client_id is omitted, returns all leads (admin aggregated view).
    Internal-key gated (Stage 5) — only the Next.js dashboard server can
    call this; direct callers without the key get 401."""
    leads = await svc.get_all_leads(client_id=client_id)
    return {"leads": [svc.serialize_lead(l) for l in leads]}


@router.get("/maya-watch/leads/{phone:path}", dependencies=[Depends(_require_internal_key)])
async def get_lead(
    phone: str,
    client_id: Optional[str] = Query(default=None),
):
    norm = svc.normalize_phone(phone)
    for lead in await svc.get_all_leads(client_id=client_id):
        if lead.phone == norm:
            return svc.serialize_lead(lead)
    raise HTTPException(404, "lead not found")


@router.post("/maya-watch/leads/{phone:path}/mark-booked", dependencies=[Depends(_require_internal_key)])
async def mark_booked_endpoint(
    phone: str,
    client_id: Optional[str] = Query(default=None),
):
    lead = await svc.mark_booked(phone, client_id=client_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    return {"ok": True, "phone": lead.phone, "booked_at": lead.booked_at.isoformat()}


@router.get("/maya-watch/briefing", dependencies=[Depends(_require_internal_key)])
async def briefing(client_id: Optional[str] = Query(default=None)):
    return await svc.build_briefing(client_id=client_id)


@router.get("/maya-watch/health")
async def health():
    leads = await svc.get_all_leads()  # admin view — overall count
    return {
        "ok": True,
        "leads_in_memory": len(leads),
        "risk_after_minutes": svc.RISK_AFTER_MINUTES,
        "no_response_after_hours": svc.NO_RESPONSE_AFTER_HOURS,
    }

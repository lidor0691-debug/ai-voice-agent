"""
app/services/maya_action_executor.py
====================================
Phase 3.11C-4 — Backend executor service for `send_followup_message` actions.

Pipeline (Phase A → B → C → D):

  A. Claim       — user_supabase_rpc("claim_action_for_execution")
                   Atomic. suggestion approved → executing OR → failed
                   (Class A pre-send blockers). Returns lead_phone +
                   message_he + agent_id + client_id on success.

  B. Resolve     — resolve_twilio_config(agent_id, client_id, lead_phone)
                   Reads agents_config.whatsapp_number via service-role
                   (the only place service-role is used in this module).
                   Cross-tenant safety enforced in Python regardless of
                   the read auth.

  C. Send        — send_whatsapp(to, from, body, mode)
                   `dryrun` returns fake DRYRUN_<uuid> SID, no SDK call.
                   `live` invokes Twilio. Errors mapped to safe failure
                   codes.

  D. Finalize    — user_supabase_rpc("finalize_action_execution")
                   suggestion executing → executed | failed. Updates
                   the open execution log row in the same RPC.

Security invariants
-------------------
- User-JWT helper for claim and finalize. Never service-role.
- Service-role read is read-only and scoped to one row of agents_config.
- No global from-number env var is ever read. From-number is per-tenant only.
- JWTs are never logged, returned, or written to detail strings.
- Failure detail bounded to 500 chars.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Optional

import httpx

from app.integrations.supabase_user_jwt import user_supabase_rpc

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

_E164_RE = re.compile(r"^\+[1-9][0-9]{7,15}$")
_DETAIL_MAX_LEN = 500
_DRYRUN_PREFIX = "DRYRUN_"

# Safe, user-facing Hebrew messages for post-claim execution failures. The
# finalize RPC returns error_he = NULL on success, so the failure envelope must
# supply its own message keyed by the originating failure code.
_EXECUTION_FAILURE_HE = {
    "config_missing":  "שליחת ההודעה נכשלה: תצורת השליחה אינה זמינה.",
    "twilio_error":    "שליחת ההודעה נכשלה. נסו שוב מאוחר יותר.",
    "session_expired": "חלון 24 השעות של WhatsApp נסגר, לא ניתן לשלוח.",
}

# Twilio error codes that indicate the 24h conversation window has closed.
_SESSION_EXPIRED_TWILIO_CODES = {63016, 63007}


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolveResult:
    ok: bool
    from_number: Optional[str] = None
    mode: Optional[Literal["dryrun", "live"]] = None
    config_missing_detail: Optional[str] = None

    @classmethod
    def success(cls, from_number: str, mode: Literal["dryrun", "live"]) -> "ResolveResult":
        return cls(ok=True, from_number=from_number, mode=mode)

    @classmethod
    def config_missing(cls, detail: str) -> "ResolveResult":
        return cls(ok=False, config_missing_detail=detail[:_DETAIL_MAX_LEN])


@dataclass(frozen=True)
class TwilioResult:
    kind: Literal["success", "session_expired", "twilio_error"]
    sid: Optional[str] = None
    status: Optional[str] = None
    detail: Optional[str] = None

    @classmethod
    def success_(cls, sid: str, status: str) -> "TwilioResult":
        return cls(kind="success", sid=sid, status=status)

    @classmethod
    def session_expired_(cls, detail: str) -> "TwilioResult":
        return cls(kind="session_expired", detail=detail[:_DETAIL_MAX_LEN])

    @classmethod
    def twilio_error_(cls, detail: str, status: Optional[str] = None) -> "TwilioResult":
        return cls(kind="twilio_error", status=status, detail=detail[:_DETAIL_MAX_LEN])


# ── Twilio mode resolution ───────────────────────────────────────────────────


def _resolved_mode() -> Literal["dryrun", "live"]:
    """Fail-safe to dryrun unless env exactly equals 'live'."""
    raw = os.environ.get("MAYA_TWILIO_MODE", "")
    return "live" if raw == "live" else "dryrun"


def _live_allowlist() -> set[str]:
    raw = os.environ.get("MAYA_TWILIO_LIVE_ALLOWLIST", "") or ""
    return {p.strip() for p in raw.split(",") if p.strip()}


# ── agents_config service-role lookup ────────────────────────────────────────
# This is the ONLY service-role read in this module. It is bounded to a single
# row of one table, scoped to a specific agent_id, and the result is validated
# against the suggestion's client_id in Python before any send. Cross-tenant
# safety does not depend on RLS for this lookup; it is enforced in Python.


async def _agents_config_lookup(agent_id: str) -> Optional[dict]:
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not supabase_service_key:
        return None

    url = f"{supabase_url.rstrip('/')}/rest/v1/agents_config"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url,
                params={
                    "id":     f"eq.{agent_id}",
                    "select": "id,client_id,is_active,whatsapp_number",
                    "limit":  "1",
                },
                headers={
                    "apikey":        supabase_service_key,
                    "Authorization": f"Bearer {supabase_service_key}",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("[executor] agents_config lookup network error: %s",
                       type(exc).__name__)
        return None

    if resp.status_code != 200:
        logger.warning("[executor] agents_config lookup non-200: %d", resp.status_code)
        return None

    try:
        rows = resp.json()
    except ValueError:
        return None

    if not isinstance(rows, list) or not rows:
        return None

    return rows[0] if isinstance(rows[0], dict) else None


# ── resolve_twilio_config ────────────────────────────────────────────────────


async def resolve_twilio_config(
    agent_id: Optional[str],
    suggestion_client_id: str,
    lead_phone: str,
) -> ResolveResult:
    """Per-tenant Twilio config resolver. Never reads any FROM_NUMBER env var."""
    if not agent_id or not isinstance(agent_id, str):
        return ResolveResult.config_missing("agent_id_missing")

    row = await _agents_config_lookup(agent_id)
    if row is None:
        return ResolveResult.config_missing("agent_not_found")

    if row.get("id") != agent_id:
        return ResolveResult.config_missing("agent_id_mismatch")

    if row.get("client_id") != suggestion_client_id:
        return ResolveResult.config_missing("cross_tenant_rejection")

    if row.get("is_active") is not True:
        return ResolveResult.config_missing("agent_inactive")

    from_number = row.get("whatsapp_number")
    if not from_number or not isinstance(from_number, str):
        return ResolveResult.config_missing("no_whatsapp_number_for_agent")

    if not _E164_RE.match(from_number):
        return ResolveResult.config_missing("whatsapp_number_invalid_e164")

    mode = _resolved_mode()
    if mode == "live":
        allowlist = _live_allowlist()
        if lead_phone not in allowlist:
            return ResolveResult.config_missing("phone_not_in_live_allowlist")

    return ResolveResult.success(from_number=from_number, mode=mode)


# ── send_whatsapp ────────────────────────────────────────────────────────────


def send_whatsapp(
    to_phone: str,
    from_number: str,
    message_he: str,
    mode: Literal["dryrun", "live"],
) -> TwilioResult:
    """Send (or simulate) a WhatsApp message via Twilio.

    Adds the 'whatsapp:' prefix at SDK call time. Never stores or returns
    secrets.
    """
    if mode == "dryrun":
        return TwilioResult.success_(
            sid=f"{_DRYRUN_PREFIX}{uuid.uuid4()}",
            status="dryrun",
        )

    # mode == "live"
    sid_env = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token_env = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not sid_env or not token_env:
        return TwilioResult.twilio_error_(detail="twilio_credentials_missing")

    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
    except ImportError as exc:
        return TwilioResult.twilio_error_(detail=f"twilio_sdk_unavailable:{type(exc).__name__}")

    try:
        client = Client(sid_env, token_env)
        msg = client.messages.create(
            to=f"whatsapp:{to_phone}",
            from_=f"whatsapp:{from_number}",
            body=message_he,
        )
        return TwilioResult.success_(sid=msg.sid, status=getattr(msg, "status", None) or "")
    except TwilioRestException as exc:  # type: ignore[misc]
        code = getattr(exc, "code", None)
        if code in _SESSION_EXPIRED_TWILIO_CODES:
            return TwilioResult.session_expired_(detail=f"twilio:{code}")
        msg_text = (getattr(exc, "msg", "") or str(exc) or "")[:200]
        return TwilioResult.twilio_error_(detail=f"twilio:{code}:{msg_text}")
    except Exception as exc:
        return TwilioResult.twilio_error_(detail=f"{type(exc).__name__}:{str(exc)[:200]}")


# ── Orchestrator ─────────────────────────────────────────────────────────────


def _invalid_input() -> dict:
    return {
        "ok": False,
        "error_code": "invalid_input",
        "error_he": "קלט לא תקין.",
    }


async def _finalize_failure(
    user_jwt: str,
    suggestion_id: str,
    code: str,
    detail: Optional[str],
    twilio_message_status: Optional[str] = None,
) -> dict:
    """Finalize a claimed suggestion to 'failed' and return a *failure* envelope.

    The action execution did NOT succeed, so the returned envelope carries
    `ok=false` with the originating failure code — even though the finalize
    transaction itself may have committed. The finalized suggestion state is
    preserved; `finalize_ok` reports whether the finalize RPC committed.
    """
    bounded = (detail or "")[:_DETAIL_MAX_LEN] or None
    finalize = await user_supabase_rpc(
        user_jwt,
        "finalize_action_execution",
        {
            "p_suggestion_id":         suggestion_id,
            "p_terminal_status":       "failed",
            "p_twilio_message_sid":    None,
            "p_twilio_message_status": twilio_message_status,
            "p_failure_code":          code,
            "p_failure_detail":        bounded,
        },
    )

    finalize_ok = isinstance(finalize, dict) and finalize.get("ok") is True
    if not finalize_ok:
        # The finalize transaction itself failed (auth/race/network). Surface
        # its envelope but force ok=false and flag that finalize did not commit.
        result = dict(finalize) if isinstance(finalize, dict) else {}
        result["ok"] = False
        result.setdefault("error_code", code)
        result["finalize_ok"] = False
        return result

    return {
        "ok": False,
        "error_code": code,
        "error_he": finalize.get("error_he") or _EXECUTION_FAILURE_HE.get(code),
        "suggestion": finalize.get("suggestion"),
        "current_version": finalize.get("current_version"),
        "execution_log_id": finalize.get("execution_log_id"),
        "finalize_ok": True,
    }


async def _finalize_success(
    user_jwt: str,
    suggestion_id: str,
    sid: str,
    status: Optional[str],
) -> dict:
    return await user_supabase_rpc(
        user_jwt,
        "finalize_action_execution",
        {
            "p_suggestion_id":         suggestion_id,
            "p_terminal_status":       "executed",
            "p_twilio_message_sid":    sid,
            "p_twilio_message_status": status,
            "p_failure_code":          None,
            "p_failure_detail":        None,
        },
    )


async def execute_one(
    suggestion_id: str,
    expected_version: int,
    user_jwt: str,
) -> dict[str, Any]:
    """Run one full claim → resolve → send → finalize cycle for a suggestion.

    Returns the RPC envelope of the last DB transaction (claim or finalize),
    or a safe `invalid_input` envelope on bad input. Never raises.
    """
    # 1. Input validation
    if (
        not isinstance(suggestion_id, str) or not suggestion_id.strip()
        or not isinstance(expected_version, int) or isinstance(expected_version, bool)
        or not isinstance(user_jwt, str) or not user_jwt.strip()
    ):
        return _invalid_input()

    # 2. Claim
    claim = await user_supabase_rpc(
        user_jwt,
        "claim_action_for_execution",
        {
            "p_suggestion_id":    suggestion_id,
            "p_expected_version": expected_version,
        },
    )
    if not isinstance(claim, dict) or claim.get("ok") is not True:
        return claim if isinstance(claim, dict) else {
            "ok": False,
            "error_code": "unknown",
            "error_he": "הפעולה נכשלה. נסו שוב.",
        }

    suggestion_client_id = claim.get("client_id") or ""
    agent_id = claim.get("agent_id")
    lead_phone = claim.get("lead_phone") or ""
    message_he = claim.get("message_he") or ""

    # 3. Resolve Twilio config (per-tenant, never global env)
    resolved = await resolve_twilio_config(
        agent_id=agent_id,
        suggestion_client_id=suggestion_client_id,
        lead_phone=lead_phone,
    )
    if not resolved.ok:
        return await _finalize_failure(
            user_jwt,
            suggestion_id,
            code="config_missing",
            detail=resolved.config_missing_detail,
        )

    # 4. Send
    twilio = send_whatsapp(
        to_phone=lead_phone,
        from_number=resolved.from_number or "",
        message_he=message_he,
        mode=resolved.mode or "dryrun",
    )

    # 5. Finalize
    if twilio.kind == "success":
        return await _finalize_success(
            user_jwt,
            suggestion_id,
            sid=twilio.sid or "",
            status=twilio.status,
        )
    if twilio.kind == "session_expired":
        return await _finalize_failure(
            user_jwt,
            suggestion_id,
            code="session_expired",
            detail=twilio.detail,
            twilio_message_status=twilio.status,
        )
    return await _finalize_failure(
        user_jwt,
        suggestion_id,
        code="twilio_error",
        detail=twilio.detail,
        twilio_message_status=twilio.status,
    )

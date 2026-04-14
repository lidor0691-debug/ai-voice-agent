"""
app/services/agent_config.py
============================
Supabase-backed agent config loader for the Maya AI voice backend.

Public API
----------
fetch_supabase_agent_config(to_number: str) -> dict | None
    Fetch an active agent from Supabase by the Twilio "To" phone number.
    Returns a client_config dict, or None if the number is not found or
    any error occurs — the caller falls back to the safe default agent.

build_supabase_system_prompt(row: dict, knowledge_items: list[dict], caller_phone: str) -> str
    Build the final system prompt from a Supabase agents_config row plus
    its knowledge items.  If system_prompt is set, it is used verbatim
    (with caller_phone injected).  Knowledge items are appended as a
    structured section so the agent can reference them.
"""

import os
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Supabase credentials ──────────────────────────────────────────────────────
# These must be set in .env:
#   SUPABASE_URL=https://xxxx.supabase.co
#   SUPABASE_ANON_KEY=eyJ...
_SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
_SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def _is_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_ANON_KEY)


def _headers() -> dict:
    return {
        "apikey":        _SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {_SUPABASE_ANON_KEY}",
        "Content-Type":  "application/json",
    }


# ── OpenAI Realtime voice names (valid as of 2025) ───────────────────────────
_OPENAI_VOICES = {"alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"}
_DEFAULT_VOICE  = "shimmer"

# ── Safe default config — returned instead of None on any failure ─────────────
# Callers can detect this via cfg["fallback_used"] == True.
_AGENT_SAFE_DEFAULT: dict = {
    "client_name":           "Unassigned",
    "assistant_name":        "Maya",
    "voice":                 _DEFAULT_VOICE,
    "lead_delivery_method":  "",
    "lead_delivery_target":  "",
    "webhook_url":           "",   # legacy alias kept for safety
    "temperature":           0.7,
    "first_message":         "",
    "prompt_override": (
        "You are Maya, an AI voice assistant. "
        "Greet the caller warmly and let them know someone will be with them shortly. "
        "Caller phone: {{caller_phone}}"
    ),
    "_from_supabase": False,
    "fallback_used":  True,
}


def _resolve_voice(row: dict) -> str:
    """
    Return an OpenAI Realtime voice name from the agent config row.

    Rules:
    - If voice_provider is "openai" (or empty) AND voice_id is a valid
      OpenAI voice name, use voice_id directly.
    - Otherwise fall back to _DEFAULT_VOICE.
    """
    provider = (row.get("voice_provider") or "").lower()
    voice_id  = (row.get("voice_id") or "").strip()

    if voice_id in _OPENAI_VOICES:
        return voice_id                # user set a valid OpenAI voice — use it

    if provider in ("", "openai") and voice_id:
        logger.warning(
            "voice_id '%s' is not a recognised OpenAI Realtime voice. "
            "Falling back to '%s'. Valid values: %s",
            voice_id, _DEFAULT_VOICE, sorted(_OPENAI_VOICES),
        )

    return _DEFAULT_VOICE


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_supabase_system_prompt(
    row:            dict,
    knowledge_items: list[dict],
    caller_phone:   str,
) -> str:
    """
    Build the final system prompt for a Supabase-configured agent.

    Priority:
    1. If row['system_prompt'] is set, use it as the full prompt.
    2. Otherwise build a generic prompt from the structured fields.

    Knowledge items (if any) are always appended as a reference section.
    The literal {{caller_phone}} in any prompt is replaced with the
    actual caller number.
    """
    system_prompt = (row.get("system_prompt") or "").strip()

    if not system_prompt:
        agent_name = row.get("agent_name", "Maya")
        tone       = row.get("tone") or "confident, natural"
        language   = row.get("language") or "en"

        system_prompt = f"""You are {agent_name}, an AI voice assistant.
Language: {language}. Tone: {tone}.
Caller phone: {caller_phone}

━━ ROLE ━━
You are a conversation closer — not a consultant, not a questionnaire.
Your job is to lead the caller toward a clear next step in as few turns as possible.

━━ CONVERSATION STRUCTURE (follow this order) ━━

STEP 1 — UNDERSTAND INTENT (max 2 questions)
  Ask only what you need to know to understand why they called.
  Before asking, briefly frame why: "כדי שאוכל לעזור לך הכי טוב — ..."
  Do NOT explore or probe further than necessary.

STEP 2 — GUIDE TOWARD A PATH
  Once you understand their need, reflect it back and propose the next step.
  Don't ask another question — make a statement or offer.
  Example: "אז מה שמחפשים זה X — מעולה, בדיוק בשביל זה אני כאן."

STEP 3 — MOVE TO ACTION
  Capture only what's needed to follow up: name and phone number.
  Frame it naturally: "כדי שנוכל לחזור אליך — על איזה שם ומספר?"
  Then confirm and close warmly.

━━ RULES ━━
- ONE question per turn. Always. Then stop and wait.
- Never ask more than 2 questions in a row without giving something back.
- Never invent names, details, or responses for the caller.
- After every answer, ADVANCE — don't ask a follow-up for the sake of it.
- If the caller's intent is clear, skip Step 1 entirely and go to Step 2.
- Keep sentences short. Pause naturally. Sound like a person.

━━ TONE ━━
Confident and warm — you're leading, not interrogating.
The caller should feel guided, not interviewed.
"""

    # Append knowledge items as a structured reference block
    if knowledge_items:
        kb_lines = ["\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        kb_lines.append("KNOWLEDGE BASE — use this information when answering questions:")
        for item in knowledge_items:
            category = (item.get("category") or "General").strip()
            title    = (item.get("title")    or "").strip()
            content  = (item.get("content")  or "").strip()
            if title or content:
                kb_lines.append(f"\n[{category}] {title}")
                if content:
                    kb_lines.append(content)
        kb_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        system_prompt += "\n".join(kb_lines)

    # Inject actual caller phone number
    system_prompt = system_prompt.replace("{{caller_phone}}", caller_phone)

    return system_prompt


# ── Supabase REST queries ─────────────────────────────────────────────────────

def _strip_phone(phone: str) -> str:
    """Strip all non-digit characters from a phone number (for alternate lookup)."""
    return re.sub(r"\D", "", phone)


async def _fetch_agent_row(to_number: str) -> Optional[dict]:
    """
    Query Supabase for an active agent matching the given phone number.
    Tries multiple formats so dashboard-saved numbers match Twilio's E.164.
    Returns the row dict or None.
    """
    # Build a set of candidates to try, preserving order (most specific first)
    candidates: list[str] = []
    if to_number:
        candidates.append(to_number)
    # Also try without leading +  (e.g. "972543033010" if stored that way)
    stripped = _strip_phone(to_number)
    if stripped and stripped not in candidates:
        candidates.append(stripped)

    base_url = f"{_SUPABASE_URL}/rest/v1/agents_config"

    async with httpx.AsyncClient(timeout=5.0) as client:
        for candidate in candidates:
            # Use params dict so httpx URL-encodes + and other special chars
            resp = await client.get(
                base_url,
                params={"phone_number": f"eq.{candidate}", "is_active": "eq.true", "limit": 1},
                headers=_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                logger.info(
                    "Supabase: matched phone '%s' (tried as '%s')",
                    to_number, candidate,
                )
                return rows[0]

    return None


async def _fetch_agent_row_by_field(field: str, number: str) -> Optional[dict]:
    """
    Query Supabase for an active agent by a specific field (e.g. 'whatsapp_number').
    Tries both the raw value and the digits-only variant.
    """
    candidates: list[str] = [number]
    stripped = _strip_phone(number)
    if stripped and stripped not in candidates:
        candidates.append(stripped)

    base_url = f"{_SUPABASE_URL}/rest/v1/agents_config"

    async with httpx.AsyncClient(timeout=5.0) as client:
        for candidate in candidates:
            resp = await client.get(
                base_url,
                params={field: f"eq.{candidate}", "is_active": "eq.true", "limit": 1},
                headers=_headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                logger.info(
                    "Supabase: matched %s '%s' (tried as '%s')",
                    field, number, candidate,
                )
                return rows[0]

    return None


async def _fetch_knowledge_items(agent_id: str) -> list[dict]:
    """
    Fetch active knowledge items for an agent, ordered by priority descending.
    """
    url = (
        f"{_SUPABASE_URL}/rest/v1/knowledge_items"
        f"?agent_id=eq.{agent_id}&is_active=eq.true&order=priority.desc"
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


# ── WhatsApp inbound lookup ───────────────────────────────────────────────────

async def get_whatsapp_agent_config(raw_to: str) -> Optional[dict]:
    """
    Fetch a minimal agent config for an inbound WhatsApp message.

    Accepts the Twilio 'To' value in any of these formats:
        "whatsapp:+972543033010"   (Twilio webhook format)
        "+972543033010"            (plain E.164)
        "972543033010"             (no-plus variant)

    Returns a dict with exactly:
        {
            # Base business identity — shared across all channels.
            # Make.com uses this as the foundation for the WhatsApp prompt.
            "system_prompt":            str | None,

            # Shared channel-agnostic settings
            "tone":                     str | None,
            "first_message":            str | None,

            # Business availability / operating hours (jsonb)
            "schedule":                 dict | None,

            # WhatsApp-specific behavior controls.
            # Make.com combines these with system_prompt to build
            # the final WhatsApp prompt — no prompt assembly happens here.
            "whatsapp_goal":            str | None,
            "whatsapp_required_fields": list | None,   # always list or None
            "whatsapp_rules":           list | None,   # always list or None
        }

    Returns None if:
        - Supabase is not configured
        - No active agent matches the number
        - Any network/parse error occurs
    Callers must handle None safely — this function never raises.
    """
    print("DEBUG_PHONE_IN:", repr(raw_to), flush=True)

    if not _is_configured():
        logger.warning("[WHATSAPP] Supabase not configured — skipping agent lookup")
        return None

    if not raw_to:
        logger.warning("[WHATSAPP] get_whatsapp_agent_config called with empty raw_to")
        return None

    # Strip the "whatsapp:" scheme Twilio prepends on inbound messages
    to_number = raw_to.removeprefix("whatsapp:")
    print("DEBUG_PHONE_NORMALIZED:", repr(to_number), flush=True)

    try:
        # Primary: match on whatsapp_number (the correct field for WhatsApp channels)
        print("DEBUG_QUERY: whatsapp_number =", repr(to_number), flush=True)
        row = await _fetch_agent_row_by_field("whatsapp_number", to_number)
        print("DEBUG_DB_RESPONSE whatsapp_number:", row, flush=True)
        # Fallback: some agents may still only have phone_number set
        if row is None:
            print("DEBUG_QUERY: phone_number =", repr(to_number), flush=True)
            logger.info("[WHATSAPP] No match on whatsapp_number — trying phone_number for '%s'", to_number)
            row = await _fetch_agent_row_by_field("phone_number", to_number)
            print("DEBUG_DB_RESPONSE phone_number:", row, flush=True)
    except Exception as exc:
        logger.error("[WHATSAPP] Agent lookup failed for '%s': %s", raw_to, exc)
        return None

    if not row:
        logger.info("[WHATSAPP] No active agent found for '%s'", raw_to)
        return None

    print("DEBUG_AGENT_FOUND:", {k: v for k, v in row.items() if k in ("id", "agent_name", "whatsapp_number", "phone_number", "is_active")}, flush=True)
    _safe_name = (row.get("agent_name") or "").encode("ascii", errors="replace").decode("ascii")
    logger.info("[WHATSAPP] Agent matched: '%s' (id=%s) for '%s'", _safe_name, row.get("id"), raw_to)

    # Ensure jsonb array fields are lists or None — never raw strings
    required_fields = row.get("whatsapp_required_fields")
    rules           = row.get("whatsapp_rules")

    return {
        "system_prompt":            row.get("system_prompt") or None,
        "tone":                     row.get("tone") or None,
        "schedule":                 row.get("schedule") or None,
        "first_message":            row.get("first_message") or None,
        "whatsapp_goal":            row.get("whatsapp_goal") or None,
        "whatsapp_required_fields": required_fields if isinstance(required_fields, list) else None,
        "whatsapp_rules":           rules if isinstance(rules, list) else None,
    }


# ── Main public function ──────────────────────────────────────────────────────

async def fetch_supabase_agent_config(to_number: str) -> dict:
    """
    Fetch an agent from Supabase by E.164 "To" phone number.

    Always returns a dict — never None.
    On any failure (Supabase not configured, no match, network error),
    returns _AGENT_SAFE_DEFAULT with fallback_used=True.

    Successful match returns fallback_used=False and _from_supabase=True.
    """
    if not _is_configured():
        logger.warning("Supabase not configured (SUPABASE_URL/SUPABASE_ANON_KEY missing) — using safe default")
        return _AGENT_SAFE_DEFAULT

    if not to_number:
        logger.warning("fetch_supabase_agent_config called with empty to_number — using safe default")
        return _AGENT_SAFE_DEFAULT

    try:
        row = await _fetch_agent_row(to_number)
    except Exception as exc:
        logger.error("Supabase agent lookup failed for %s: %s — using safe default", to_number, exc)
        return _AGENT_SAFE_DEFAULT

    if not row:
        logger.info("No Supabase agent found for %s — using safe default", to_number)
        return _AGENT_SAFE_DEFAULT

    logger.info(
        "Supabase agent found: '%s' (id=%s) for number %s",
        row.get("agent_name"), row.get("id"), to_number,
    )

    # Fetch knowledge items (best-effort — don't fail the call if this errors)
    try:
        knowledge_items = await _fetch_knowledge_items(row["id"])
        logger.info("  knowledge items: %d", len(knowledge_items))
    except Exception as exc:
        logger.warning("Failed to fetch knowledge items for agent %s: %s", row["id"], exc)
        knowledge_items = []

    # Build prompt template with {{caller_phone}} placeholder intact.
    # The WebSocket will inject the real caller number at connection time.
    prompt_template = build_supabase_system_prompt(row, knowledge_items, caller_phone="{{caller_phone}}")

    agent_name    = (row.get("agent_name") or "Maya").strip()
    business_name = (row.get("business_name") or agent_name).strip()
    first_message = (row.get("first_message") or "").strip()
    voice         = _resolve_voice(row)

    # ── Lead delivery: new fields with fallback to legacy post_call_webhook_url ──
    lead_delivery_method = (row.get("lead_delivery_method") or "").strip()
    lead_delivery_target = (row.get("lead_delivery_target") or "").strip()
    legacy_webhook       = (row.get("post_call_webhook_url") or "").strip()

    if not lead_delivery_target and legacy_webhook:
        # Upgrade legacy config transparently
        lead_delivery_method = "webhook"
        lead_delivery_target = legacy_webhook
        logger.info("  lead delivery: using legacy post_call_webhook_url as webhook target")

    return {
        # Identity
        "agent_id":              row.get("id", ""),
        "client_id":             row.get("client_id", ""),
        "business_name":         business_name,
        "client_name":           agent_name,
        "assistant_name":        agent_name,
        # Voice / model
        "voice":                 voice,
        "temperature":           float(row.get("temperature") or 0.7),
        # Conversation
        "prompt_override":       prompt_template,
        "first_message":         first_message,
        # Lead delivery
        "lead_delivery_method":  lead_delivery_method,
        "lead_delivery_target":  lead_delivery_target,
        "webhook_url":           lead_delivery_target if lead_delivery_method == "webhook" else "",  # legacy alias
        # WhatsApp channel
        "whatsapp_enabled":          bool(row.get("whatsapp_enabled") or False),
        "whatsapp_number":           (row.get("whatsapp_number") or "").strip(),
        "whatsapp_followup_enabled": bool(row.get("whatsapp_followup_enabled") or False),
        "whatsapp_followup_type":    (row.get("whatsapp_followup_type") or "none").strip(),
        "whatsapp_followup_template":(row.get("whatsapp_followup_template") or "").strip(),
        # Meta
        "_from_supabase":        True,
        "fallback_used":         False,
    }

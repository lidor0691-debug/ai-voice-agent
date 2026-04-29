"""
app/services/whatsapp_reply.py
================================
Backend WhatsApp reply generation.

Assembles context (agent config + conversation history) and calls
OpenAI Chat Completions to produce the assistant reply.
Memory is persisted to whatsapp_conversations so Make never needs to
compose or pass history — it only sends the current user message.

Public API
----------
generate_whatsapp_reply(phone, user_message) -> dict
    Returns {"reply": str, "messages": list[dict]}
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.services.agent_config import get_whatsapp_agent_config
from app.services.lead_capture import save_lead, update_lead_name
from app.services.whatsapp_history import append_whatsapp_messages, _load_row, _normalize_messages

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


async def _fetch_recent_call_context(phone: str, max_age_minutes: int = 60) -> Optional[str]:
    """
    Fetch last_call_summary from leads table if last_call_at is within max_age_minutes.
    Returns a context string or None.
    """
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY or not phone:
        return None
    try:
        headers = {
            "apikey": _SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/leads",
                params={"phone": f"eq.{phone}", "select": "last_call_summary,last_call_at,name"},
                headers=headers,
            )
            resp.raise_for_status()
            rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        last_call_at = row.get("last_call_at")
        summary = row.get("last_call_summary")
        if not last_call_at or not summary:
            return None
        # Parse timestamp and check age
        call_time = datetime.fromisoformat(last_call_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_minutes = (now - call_time).total_seconds() / 60
        if age_minutes > max_age_minutes:
            return None
        name = row.get("name") or ""
        ctx = f"לפני {int(age_minutes)} דקות התקיימה שיחה טלפונית"
        if name:
            ctx += f" עם {name}"
        ctx += f". מה שנאמר בשיחה: {summary}"
        return ctx
    except Exception as exc:
        logger.warning("[WHATSAPP] Failed to fetch recent call context: %s", exc)
        return None

logger = logging.getLogger(__name__)

_raw_key = os.getenv("OPENAI_API_KEY", "")
_OPENAI_API_KEY = (
    _raw_key.strip()
    .replace("\u2028", "")
    .replace("\u2029", "")
    .replace("\r", "")
    .replace("\n", "")
)
logger.info("[KEY DIAG] raw_key[:5]=%r clean_key[:5]=%r", _raw_key[:5], _OPENAI_API_KEY[:5])
_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = "gpt-4o"


def _build_system_message(agent: dict) -> str:
    parts: list[str] = []

    system_prompt = (agent.get("system_prompt") or "").strip()
    if system_prompt:
        parts.append(system_prompt)

    tone = (agent.get("tone") or "").strip()
    if tone:
        parts.append(f"Tone: {tone}")

    goal = (agent.get("whatsapp_goal") or "").strip()
    if goal:
        parts.append(f"\nGoal for this conversation:\n{goal}")

    required_fields = agent.get("whatsapp_required_fields")
    if isinstance(required_fields, list) and required_fields:
        fields_str = "\n".join(f"- {f}" for f in required_fields)
        parts.append(f"\nYou must collect the following information from the user:\n{fields_str}")

    rules = agent.get("whatsapp_rules")
    if isinstance(rules, list) and rules:
        rules_str = "\n".join(f"- {r}" for r in rules)
        parts.append(f"\nRules to follow throughout the conversation:\n{rules_str}")

    return "\n\n".join(parts) if parts else "You are a helpful assistant."


def _sanitize(text: str) -> str:
    """Replace Unicode line/paragraph separators that break ASCII encoding."""
    return text.replace("\u2028", "\n").replace("\u2029", "\n")


def _sanitize_output(text: str) -> str:
    if not isinstance(text, str):
        return text
    return text.replace("\u2028", " ").replace("\u2029", " ")


def strict_sanitize(text: str) -> str:
    """Guarantee no \\u2028/\\u2029 leaves the API — applied to every outbound string."""
    if not text:
        return ""
    return (
        str(text)
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
        .encode("utf-8", errors="replace")
        .decode("utf-8")
    )


async def _call_openai(messages: list[dict]) -> str:
    # STEP5A: build clean_messages
    try:
        clean_messages = [
            {**msg, "content": _sanitize(msg["content"])} if isinstance(msg.get("content"), str) else msg
            for msg in messages
        ]
    except Exception as exc:
        raise RuntimeError(f"DIAG_STEP5A_FAIL: {exc}") from exc

    # STEP5B: build headers
    try:
        headers = {
            "Authorization": f"Bearer {_OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
    except Exception as exc:
        raise RuntimeError(f"DIAG_STEP5B_FAIL: {exc}") from exc

    # STEP5C: build payload dict
    try:
        payload = {"model": _MODEL, "messages": clean_messages}
    except Exception as exc:
        raise RuntimeError(f"DIAG_STEP5C_FAIL: {exc}") from exc

    # STEP5D: serialize to ASCII-safe JSON string
    try:
        body = json.dumps(payload, ensure_ascii=True)
    except Exception as exc:
        raise RuntimeError(f"DIAG_STEP5D_FAIL: {exc}") from exc

    # STEP5E: HTTP request — stdlib urllib (no httpx) to isolate transport
    try:
        import urllib.request as _urllib
        body_bytes = body.encode("ascii", errors="ignore")
        req = _urllib.Request(
            _OPENAI_CHAT_URL,
            data=body_bytes,
            headers={
                "Authorization": headers["Authorization"],
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with _urllib.urlopen(req, timeout=30) as _resp:
            raw_response = _resp.read()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"DIAG_STEP5E_FAIL: {exc}") from exc

    # STEP5F: parse response JSON
    try:
        data = json.loads(raw_response)
    except Exception as exc:
        raise RuntimeError(f"DIAG_STEP5F_FAIL: {exc}") from exc

    # STEP5G: extract assistant content
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"DIAG_STEP5G_FAIL: {exc}") from exc


# ---------------------------------------------------------------------------
# Lead Intelligence — sentence injection helper
# ---------------------------------------------------------------------------
# Rules loaded from shared/lead-intelligence-rules.json (single source of truth
# shared with the dashboard preview card).
import json as _json
from pathlib import Path as _Path

_RULES_PATH = _Path(__file__).parent.parent.parent / "dashboard" / "lib" / "lead-intelligence-rules.json"
try:
    _INJECTION_RULES: list[dict] = _json.loads(_RULES_PATH.read_text(encoding="utf-8"))
except Exception as _e:
    logger.warning("[LEAD INTELLIGENCE] could not load rules from %s: %s — using empty rules", _RULES_PATH, _e)
    _INJECTION_RULES = []


async def _maybe_inject_sentence(reply: str, client_id: str, history: list[dict]) -> str:
    """
    Appends at most ONE short sentence to `reply` when a strong pattern is
    detected in recent lead_intelligence_insights for this client.

    Guards:
    - Requires ≥ 2 matching insight rows (by summed frequency_count).
    - Skips if any injection sentence already appears in the last 3 assistant
      turns (best-effort once-per-window suppression, no new state infra).
    - Never raises — returns original reply on any error.
    """
    print("[INJECTION-FUNCTION HIT]", flush=True)
    # Globally disabled: post-processing was appending canned sales sentences
    # (e.g., a price-options line) to BPM/other agent replies, which is not
    # business-appropriate. Rules file and logic kept intact for future use.
    print("[INJECTION DISABLED RETURN]", flush=True)
    return reply

    if not client_id or not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        return reply

    # Fetch recent insights for this client
    try:
        headers = {
            "apikey": _SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        }
        async with httpx.AsyncClient(timeout=4.0) as _c:
            _r = await _c.get(
                f"{_SUPABASE_URL}/rest/v1/lead_intelligence_insights",
                params={
                    "client_id": f"eq.{client_id}",
                    "select":    "insight_type,title,frequency_count",
                    "order":     "created_at.desc",
                    "limit":     "20",
                },
                headers=headers,
            )
        insights = _r.json() if _r.status_code == 200 else []
    except Exception as exc:
        logger.warning("[INJECTION] fetch failed: %s", exc)
        return reply

    if not isinstance(insights, list) or not insights:
        return reply

    # Clean bad rows (same filter as dashboard)
    def _clean(t: str) -> bool:
        t = (t or "").strip()
        if not t or t.lower() == "insight":
            return False
        import re
        if re.match(r'^[?\s\W]+$', t):
            return False
        return True

    insights = [r for r in insights if _clean(r.get("title", ""))]

    # Score each rule: sum of frequency_count for matching rows
    best_sentence = None
    best_weight = 0
    for rule in _INJECTION_RULES:
        weight = sum(
            r.get("frequency_count", 0)
            for r in insights
            if r.get("insight_type") in rule["types"]
            and any(kw in (r.get("title") or "") for kw in rule["keywords"])
        )
        if weight >= 2 and weight > best_weight:
            best_weight = weight
            best_sentence = rule["sentence"]

    if not best_sentence:
        return reply

    # Best-effort once-per-window: skip if sentence already in last 3 assistant turns
    recent_assistant = [
        m.get("content", "")
        for m in history[-6:]
        if m.get("role") == "assistant"
    ][-3:]
    if any(best_sentence in turn for turn in recent_assistant):
        logger.info("[INJECTION] suppressed — already injected recently")
        return reply

    logger.info("[INJECTION] appending sentence (weight=%d)", best_weight)

    # Fire-and-forget audit record — never blocks reply
    try:
        _rule_key = next(
            (r["keywords"][0] for r in _INJECTION_RULES if r["sentence"] == best_sentence),
            "unknown",
        )
        async with httpx.AsyncClient(timeout=3.0) as _ac:
            await _ac.post(
                f"{_SUPABASE_URL}/rest/v1/audit_logs",
                headers={
                    "apikey": _SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={
                    "table_name": "lead_intelligence_injection",
                    "action":     "inject",
                    "new_data": {
                        "client_id": client_id,
                        "rule_key":  _rule_key,
                        "sentence":  best_sentence,
                        "weight":    best_weight,
                    },
                },
            )
    except Exception as _ae:
        logger.warning("[INJECTION] audit write failed: %s", _ae)

    return reply.rstrip() + "\n\n" + best_sentence


async def generate_whatsapp_reply(customer_phone: str, business_phone: str, user_message: str) -> dict:
    try:
        return await _generate_whatsapp_reply_inner(customer_phone, business_phone, user_message)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {
            "reply": strict_sanitize(f"ERROR: {exc}"),
            "messages": [],
        }


async def _generate_whatsapp_reply_inner(customer_phone: str, business_phone: str, user_message: str) -> dict:
    # Normalize both phones — strip "whatsapp:" prefix Twilio may prepend
    customer_phone = customer_phone.replace("whatsapp:", "").strip()
    business_phone = business_phone.replace("whatsapp:", "").strip()

    print("DEBUG customer_phone:", repr(customer_phone), flush=True)
    print("DEBUG business_phone:", repr(business_phone), flush=True)

    user_message = _sanitize(user_message)

    # ── 1. Load agent config via business_phone ───────────────────────────────
    try:
        print("DEBUG agent lookup using business_phone:", repr(business_phone), flush=True)
        agent = await get_whatsapp_agent_config(business_phone)
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP1_FAIL: {exc}"), "messages": []}

    # Fail closed: unknown business_phone / no active agent → refuse to reply.
    # Returning a generic Maya prompt (or any other tenant's prompt) to an
    # unknown number is forbidden by multi-tenant isolation rules.
    if agent is None or not agent.get("system_prompt"):
        print(
            f"[ROUTE-AUDIT] route=whatsapp_reply business_phone={business_phone} "
            f"resolved_agent_id=None resolved_client_id=None "
            f"fallback_used=true knowledge_items_count=0"
        )
        logger.warning("[WHATSAPP] No active agent for business_phone=%s — refusing (fail closed)", business_phone)
        return {"reply": "", "messages": []}

    agent = {k: _sanitize(v) if isinstance(v, str) else v for k, v in agent.items()}
    print(
        f"[ROUTE-AUDIT] route=whatsapp_reply business_phone={business_phone} "
        f"resolved_agent_id={agent.get('agent_id')} "
        f"resolved_client_id={agent.get('client_id')} "
        f"fallback_used=false knowledge_items_count=N/A"
    )

    # ── 2. Build system message ───────────────────────────────────────────────
    try:
        system_content = _build_system_message(agent)
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP2_FAIL: {exc}"), "messages": []}

    # ── 2b. Recent phone-call context injection — DISABLED for tenant isolation
    # _fetch_recent_call_context queries leads by phone alone, which leaks
    # context across clients (e.g., a Roi summary into a BPM session).
    # Re-enable only after the leads query is scoped by (phone, client_id).
    print(f"[WHATSAPP] phone-context injection skipped (disabled for tenant isolation)")

    # ── 3. Load history via customer_phone ────────────────────────────────────
    try:
        print("DEBUG history lookup using customer_phone:", repr(customer_phone), flush=True)
        row = await _load_row(customer_phone)
        history = _normalize_messages(row.get("messages_json") if row else None)
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP3_FAIL: {exc}"), "messages": []}

    # First message from this phone — save as a new lead (independent of history loading)
    if row is None:
        await save_lead({
            "phone":     customer_phone,
            "source":    "whatsapp",
            "status":    "new",
            "client_id": agent.get("client_id") or None,
        })

    # ── Update last_whatsapp_inbound_at for 24h window tracking ──────────
    try:
        async with httpx.AsyncClient(timeout=3.0) as _wc:
            await _wc.patch(
                f"{_SUPABASE_URL}/rest/v1/leads?phone=eq.{customer_phone}",
                json={"last_whatsapp_inbound_at": datetime.utcnow().isoformat()},
                headers={**_headers(), "Prefer": "return=minimal"},
            )
    except Exception as _exc:
        logger.warning("[WHATSAPP] Failed to update last_whatsapp_inbound_at: %s", _exc)

    # ── 3b. First-WhatsApp-after-call summary injection — DISABLED for tenant isolation
    # Previously injected leads.last_call_summary by phone alone, which leaks
    # across clients. Re-enable only after the leads query is scoped by
    # (phone, client_id) and the leads upsert uses a (phone, client_id) key.
    # No-op for now — first WhatsApp turn starts with an empty assistant history.

    # ── 4+5. Call OpenAI ──────────────────────────────────────────────────────
    openai_messages = (
        [{"role": "system", "content": system_content}]
        + history
        + [{"role": "user", "content": user_message}]
    )
    try:
        reply = _sanitize(await _call_openai(openai_messages))
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP5_FAIL: {exc}"), "messages": []}

    # ── 6. Persist history via customer_phone ────────────────────────────────
    try:
        updated_messages = await append_whatsapp_messages(customer_phone, user_message, reply)
    except Exception as exc:
        updated_messages = history + [
            {"role": "user",      "content": user_message},
            {"role": "assistant", "content": reply},
        ]

    # ── 6a. Attribution Ledger v0 — record outbound WhatsApp action ─────────────
    # Fire-and-forget. Never raises. See app/services/attribution.py.
    try:
        from app.services.attribution import record_whatsapp_action
        await record_whatsapp_action(
            client_id=agent.get("client_id") or "",
            lead_phone=customer_phone,
        )
    except Exception as _exc:
        logger.warning("[ATTRIBUTION] action record skipped: %s", _exc)

    # ── 6b. Lead Intelligence — extract insights from current user message ──────
    try:
        from app.services.lead_intelligence import extract_insights, save_insights as _save_insights
        _insights = extract_insights(user_message)
        if _insights:
            await _save_insights(
                insights=_insights,
                client_id=agent.get("client_id") or "",
                agent_id=str(agent.get("agent_id") or agent.get("id") or "") or None,
                source_type="whatsapp",
                source_record_id=None,
            )
    except Exception as _exc:
        logger.warning("[LEAD INTELLIGENCE] extraction skipped: %s", _exc)

    # ── 7. Extract name from conversation and update lead if not yet set ────────
    # Heuristic: if the previous assistant message asked for a name and the
    # current user message is short (1-4 words), treat it as the caller's name.
    try:
        _NAME_TRIGGERS = ("איך קוראים", "מה שמך", "מה השם", "על איזה שם", "שם שלך", "שמך")
        _last_assistant = next(
            (m["content"] for m in reversed(history) if m.get("role") == "assistant"),
            "",
        )
        _words = user_message.strip().split()
        if (
            any(t in _last_assistant for t in _NAME_TRIGGERS)
            and 1 <= len(_words) <= 4
            and not any(ch.isdigit() for ch in user_message)
        ):
            await update_lead_name(customer_phone, user_message.strip())
            print(f"[LEAD] name updated: {user_message.strip()!r} for {customer_phone}", flush=True)
    except Exception as exc:
        logger.warning("[LEAD] name extraction failed: %s", exc)

    # ── 6c. Lead Intelligence — sentence injection (guarded) ────────────────────
    try:
        reply = await _maybe_inject_sentence(reply, agent.get("client_id") or "", updated_messages)
    except Exception as _exc:
        logger.warning("[LEAD INTELLIGENCE] injection skipped: %s", _exc)

    reply = _sanitize_output(reply)
    messages = [
        {**m, "content": _sanitize_output(m.get("content", ""))}
        for m in updated_messages
    ]

    return {"reply": reply, "messages": messages}

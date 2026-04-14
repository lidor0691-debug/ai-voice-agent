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
from typing import Optional

import httpx

from app.services.agent_config import get_whatsapp_agent_config
from app.services.whatsapp_history import append_whatsapp_messages, _load_row, _normalize_messages

logger = logging.getLogger(__name__)

_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = "gpt-4o"


def _build_system_message(agent: dict) -> str:
    """
    Build the system message from the agent config fields.
    Combines system_prompt (base business identity) with WhatsApp-specific
    behavior controls (goal, required_fields, rules).
    """
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


def strict_sanitize(text: str) -> str:
    """Guarantee no \u2028/\u2029 leaves the API — applied to every outbound string."""
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
    """
    Call OpenAI Chat Completions and return the assistant reply text.
    Raises on HTTP or API error.
    """
    # Sanitize all message content before sending
    clean_messages = [
        {**msg, "content": _sanitize(msg["content"])} if isinstance(msg.get("content"), str) else msg
        for msg in messages
    ]
    headers = {
        "Authorization": f"Bearer {_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _MODEL,
        "messages": clean_messages,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_OPENAI_CHAT_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def generate_whatsapp_reply(phone: str, user_message: str) -> dict:
    return {"reply": "WA_BACKEND_OK_TEST", "messages": []}  # TEMP DIAGNOSTIC — remove after test
    # fmt: skip
    """
    Full pipeline:
    1. Load agent config by whatsapp_number (falls back to phone_number)
    2. Build system message from config
    3. Load + normalize conversation history
    4. Call OpenAI with [system, ...history, user_message]
    5. Persist updated history (user + assistant turns)
    6. Return {"reply": str, "messages": list}

    Never raises — returns an error reply string on failure so Make
    always gets a usable response.
    """
    try:
        return await _generate_whatsapp_reply_inner(phone, user_message)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {
            "reply": strict_sanitize(f"ERROR: {exc}"),
            "messages": [],
        }


async def _generate_whatsapp_reply_inner(phone: str, user_message: str) -> dict:
    # Sanitize input — WhatsApp messages can contain Unicode line separators
    user_message = _sanitize(user_message)

    # ── 1. Load agent config ──────────────────────────────────────────────────
    agent = await get_whatsapp_agent_config(phone)
    if agent is None:
        logger.warning("[WA REPLY] No agent config found for %s", phone)
        agent = {}
    else:
        # Sanitize all string fields in agent config at the source so nothing
        # downstream (logging, OpenAI, httpx) sees raw \u2028/\u2029 chars.
        agent = {
            k: _sanitize(v) if isinstance(v, str) else v
            for k, v in agent.items()
        }

    # ── 2. Build system message ───────────────────────────────────────────────
    system_content = _build_system_message(agent)

    # ── 3. Load history ───────────────────────────────────────────────────────
    try:
        row = await _load_row(phone)
        history = _normalize_messages(row.get("messages_json") if row else None)
    except Exception as exc:
        logger.error("[WA REPLY] Failed to load history for %s: %s", phone, exc)
        history = []

    # ── 4. Assemble OpenAI messages array ────────────────────────────────────
    openai_messages = (
        [{"role": "system", "content": system_content}]
        + history
        + [{"role": "user", "content": user_message}]
    )

    # ── 5. Call OpenAI ────────────────────────────────────────────────────────
    reply = _sanitize(await _call_openai(openai_messages))

    # ── 6. Persist updated history ────────────────────────────────────────────
    try:
        updated_messages = await append_whatsapp_messages(phone, user_message, reply)
    except Exception as exc:
        logger.error("[WA REPLY] Failed to persist history for %s: %s", phone, exc)
        updated_messages = history + [
            {"role": "user",      "content": user_message},
            {"role": "assistant", "content": reply},
        ]

    return {
        "reply": strict_sanitize(reply),
        "messages": [
            {"role": m["role"], "content": strict_sanitize(m.get("content") or "")}
            for m in updated_messages
        ],
    }

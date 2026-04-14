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


async def generate_whatsapp_reply(phone: str, user_message: str) -> dict:
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
    user_message = _sanitize(user_message)

    # ── 1. Load agent config ──────────────────────────────────────────────────
    try:
        agent = await get_whatsapp_agent_config(phone)
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP1_FAIL: {exc}"), "messages": []}

    if agent is None:
        agent = {}
    else:
        agent = {k: _sanitize(v) if isinstance(v, str) else v for k, v in agent.items()}

    # ── 2. Build system message ───────────────────────────────────────────────
    try:
        system_content = _build_system_message(agent)
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP2_FAIL: {exc}"), "messages": []}

    # ── 3. Load history ───────────────────────────────────────────────────────
    try:
        row = await _load_row(phone)
        history = _normalize_messages(row.get("messages_json") if row else None)
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP3_FAIL: {exc}"), "messages": []}

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

    # ── 6. Persist updated history ────────────────────────────────────────────
    try:
        updated_messages = await append_whatsapp_messages(phone, user_message, reply)
    except Exception as exc:
        updated_messages = history + [
            {"role": "user",      "content": user_message},
            {"role": "assistant", "content": reply},
        ]

    reply = _sanitize_output(reply)
    messages = [
        {**m, "content": _sanitize_output(m.get("content", ""))}
        for m in updated_messages
    ]

    return {"reply": reply, "messages": messages}

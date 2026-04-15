"""
Maya AI — Agent Config Loader
=============================
Fetches agent configuration from Supabase by phone number.
Used by the FastAPI voice backend to configure each call dynamically.

Usage:
    from app.maya_config import get_agent_config, build_system_prompt

    config = await get_agent_config(to_number="+15550001234")
    system_prompt = build_system_prompt(config)
"""

import os
import logging
from typing import Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]           # https://xxxx.supabase.co
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]  # anon key (kept for reference)
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]  # service role — bypasses RLS


# ──────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    id: str
    agent_name: str
    phone_number: Optional[str] = None
    is_active: bool = True

    # Conversation
    first_message: str = "Hello! How can I help you today?"
    system_prompt: str = "You are a helpful AI assistant."
    tone: str = "professional"
    language: str = "en"

    # Voice
    voice_provider: str = "elevenlabs"
    voice_id: Optional[str] = None
    speaking_rate: float = 1.0
    style_prompt: Optional[str] = None

    # Model
    model_provider: str = "openai"
    model_name: str = "gpt-4o"
    temperature: float = 0.7

    # Tools
    transfer_number: Optional[str] = None
    post_call_webhook_url: Optional[str] = None

    # Knowledge (populated separately)
    knowledge_items: list[dict] = field(default_factory=list)


# ──────────────────────────────────────────────────────
# Fetch helpers
# ──────────────────────────────────────────────────────

def _supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


async def get_agent_config(to_number: str) -> Optional[AgentConfig]:
    """
    Look up an agent by the Twilio 'To' phone number.
    Returns None if not found or not active.
    """
    url = (
        f"{SUPABASE_URL}/rest/v1/agents_config"
        f"?phone_number=eq.{to_number}&is_active=eq.true&limit=1"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_supabase_headers())
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        logger.warning("No active agent found for number: %s", to_number)
        return None

    row = rows[0]
    config = AgentConfig(
        id=row["id"],
        agent_name=row.get("agent_name", "Maya"),
        phone_number=row.get("phone_number"),
        is_active=row.get("is_active", True),
        first_message=row.get("first_message") or "Hello! How can I help you today?",
        system_prompt=row.get("system_prompt") or "You are a helpful AI assistant.",
        tone=row.get("tone") or "professional",
        language=row.get("language") or "en",
        voice_provider=row.get("voice_provider") or "elevenlabs",
        voice_id=row.get("voice_id"),
        speaking_rate=float(row.get("speaking_rate") or 1.0),
        style_prompt=row.get("style_prompt"),
        model_provider=row.get("model_provider") or "openai",
        model_name=row.get("model_name") or "gpt-4o",
        temperature=float(row.get("temperature") or 0.7),
        transfer_number=row.get("transfer_number"),
        post_call_webhook_url=row.get("post_call_webhook_url"),
    )

    # Optionally load knowledge items
    config.knowledge_items = await get_knowledge_items(config.id)
    return config


async def get_knowledge_items(agent_id: str) -> list[dict]:
    """Fetch active knowledge items for an agent, ordered by priority."""
    url = (
        f"{SUPABASE_URL}/rest/v1/knowledge_items"
        f"?agent_id=eq.{agent_id}&is_active=eq.true&order=priority.desc"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_supabase_headers())
        resp.raise_for_status()
        return resp.json()


# ──────────────────────────────────────────────────────
# Prompt builder
# ──────────────────────────────────────────────────────

def build_system_prompt(config: AgentConfig) -> str:
    """
    Merge the agent's system_prompt with its knowledge base entries.
    Returns the final prompt string to send to the LLM.
    """
    prompt = config.system_prompt.strip()

    if config.knowledge_items:
        kb_lines = ["\n\n## Knowledge Base\n"]
        for item in config.knowledge_items:
            category = item.get("category") or "General"
            title = item.get("title", "")
            content = item.get("content", "")
            kb_lines.append(f"### [{category}] {title}\n{content}")
        prompt += "\n".join(kb_lines)

    return prompt


# ──────────────────────────────────────────────────────
# Fallback config
# ──────────────────────────────────────────────────────

DEFAULT_CONFIG = AgentConfig(
    id="default",
    agent_name="Maya",
    first_message="Hello! You've reached Maya AI. How can I help you today?",
    system_prompt="You are Maya, a helpful and professional AI voice assistant.",
)


async def get_agent_config_or_default(to_number: str) -> AgentConfig:
    """Always returns a config — falls back to DEFAULT_CONFIG if none found."""
    try:
        config = await get_agent_config(to_number)
        return config or DEFAULT_CONFIG
    except Exception as exc:
        logger.error("Failed to fetch agent config: %s", exc)
        return DEFAULT_CONFIG

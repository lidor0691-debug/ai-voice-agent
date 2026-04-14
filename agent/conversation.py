# agent/conversation.py
import os
import time
import uuid
from typing import Optional

from supabase import Client, create_client

HISTORY_LIMIT = int(os.getenv("AGENT_CONVERSATION_HISTORY_LIMIT", "20"))


def _get_client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


class ConversationStore:
    def __init__(self, sb: Optional[Client] = None):
        self._sb = sb or _get_client()

    def save(self, role: str, content: str) -> str:
        msg_id = str(uuid.uuid4())
        self._sb.table("agent_conversations").insert({
            "id": msg_id,
            "role": role,
            "content": content,
            "created_at": time.time(),
        }).execute()
        return msg_id

    def get_history(self, limit: int = HISTORY_LIMIT) -> list[dict]:
        res = (
            self._sb.table("agent_conversations")
            .select("*")
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return res.data or []


def format_history(messages: list[dict]) -> str:
    if not messages:
        return ""
    lines = [f"[{m['role']}]: {m['content']}" for m in messages]
    return "\n".join(lines)

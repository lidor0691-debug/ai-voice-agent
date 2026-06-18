"""Assistant data-access layer.

DORMANT as of PR2: nothing in the running service imports this package. It is
the only layer that talks to Supabase for the assistant; the Stage-2 resolver
(`app/assistant/nlp/resolver.py`) stays pure and receives injected data via the
``resolve_with_data`` seam here.

No Telegram, Twilio, Make, scheduler, or route wiring. Backend writes use the
Supabase service role (same env + httpx pattern as app/services/maya_watch_store.py).
"""
from app.assistant.data.supabase_adapter import (
    env_ready,
    get_contact_by_name,
    insert_scheduled_message,
    list_active_templates,
    log_activity,
    resolve_with_data,
    update_scheduled_status,
    within_24h_window,
)

__all__ = [
    "env_ready",
    "get_contact_by_name",
    "insert_scheduled_message",
    "list_active_templates",
    "log_activity",
    "resolve_with_data",
    "update_scheduled_status",
    "within_24h_window",
]

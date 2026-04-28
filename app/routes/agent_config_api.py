"""
app/routes/agent_config_api.py
===============================
POST /agent-config — fetch agent configuration by phone number.

Make.com calls this endpoint to retrieve the agent config for an
inbound WhatsApp message before constructing the OpenAI prompt.
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.agent_config import get_whatsapp_agent_config

router = APIRouter()


class AgentConfigRequest(BaseModel):
    to: str


@router.post("/agent-config")
async def get_agent_config(req: AgentConfigRequest):
    """
    Returns agent config for the given 'to' phone number.
    If no active agent is found, returns {"agent": null}.
    """
    agent = await get_whatsapp_agent_config(req.to)
    if agent is None:
        print(
            f"[ROUTE-AUDIT] route=agent_config_api to={req.to!r} "
            f"resolved_agent_id=None resolved_client_id=None "
            f"fallback_used=true knowledge_items_count=0"
        )
        return {"agent": None}
    print(
        f"[ROUTE-AUDIT] route=agent_config_api to={req.to!r} "
        f"resolved_agent_id={agent.get('agent_id')} "
        f"resolved_client_id={agent.get('client_id')} "
        f"fallback_used=false knowledge_items_count=N/A"
    )
    return agent

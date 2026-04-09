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
        return {"agent": None}
    return agent

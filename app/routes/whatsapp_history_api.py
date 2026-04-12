"""
app/routes/whatsapp_history_api.py
===================================
POST /whatsapp/history — append a user+assistant turn to a WhatsApp
conversation and return the full clean messages array.

Make.com calls this after each OpenAI response to persist the exchange
and receive a clean history array for the next OpenAI call.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.whatsapp_history import append_whatsapp_messages

router = APIRouter()


class HistoryRequest(BaseModel):
    phone: str
    user_message: str
    assistant_message: str


@router.post("/whatsapp/history")
async def update_whatsapp_history(req: HistoryRequest):
    """
    Append one user+assistant turn to the conversation history for `phone`.

    - Loads existing messages_json from whatsapp_conversations
    - Normalizes it (handles null, escaped strings, invalid values)
    - Appends {"role":"user",...} and {"role":"assistant",...}
    - Saves the clean array back to Supabase
    - Returns {"messages": [...]} — the full updated array

    Make.com uses the returned array as the messages input for the next
    OpenAI call, avoiding any JSON composition on the Make side.
    """
    messages = await append_whatsapp_messages(
        phone=req.phone,
        user_message=req.user_message,
        assistant_message=req.assistant_message,
    )
    return {"messages": messages}

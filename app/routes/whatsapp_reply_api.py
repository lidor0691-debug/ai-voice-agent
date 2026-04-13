"""
app/routes/whatsapp_reply_api.py
==================================
POST /whatsapp/reply — full WhatsApp reply pipeline.

Make.com calls this with the incoming user message and phone number.
Backend handles everything: context assembly, OpenAI call, memory persistence.
Make receives the final reply text and does nothing else.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.whatsapp_reply import generate_whatsapp_reply

router = APIRouter()


class ReplyRequest(BaseModel):
    phone: str
    user_message: str


@router.post("/whatsapp/reply")
async def whatsapp_reply(req: ReplyRequest):
    """
    Full WhatsApp reply pipeline — backend owns memory and context.

    Request:
        { "phone": "+972...", "user_message": "..." }

    Response:
        {
            "reply": "...",          <- send this to the user
            "messages": [...]        <- full updated history (optional, for debugging)
        }

    Make.com usage:
        1. Receive inbound WhatsApp message
        2. POST to this endpoint with phone + user_message
        3. Send response["reply"] back to the user via WhatsApp
        Done. No history management, no prompt assembly, no OpenAI in Make.
    """
    result = await generate_whatsapp_reply(
        phone=req.phone,
        user_message=req.user_message,
    )
    return result

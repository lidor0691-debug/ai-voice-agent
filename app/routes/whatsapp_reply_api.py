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
    customer_phone: str   # Twilio From — used for conversation history
    business_phone: str   # Twilio To  — used for agent config lookup
    user_message: str


@router.post("/whatsapp/reply")
async def whatsapp_reply(req: ReplyRequest):
    """
    Full WhatsApp reply pipeline — backend owns memory and context.

    Request:
        {
            "customer_phone": "+972...",   <- Twilio From
            "business_phone": "+972...",   <- Twilio To
            "user_message": "..."
        }

    Response:
        {
            "reply": "...",          <- send this to the user
            "messages": [...]        <- full updated history (optional, for debugging)
        }
    """
    result = await generate_whatsapp_reply(
        customer_phone=req.customer_phone,
        business_phone=req.business_phone,
        user_message=req.user_message,
    )
    return result

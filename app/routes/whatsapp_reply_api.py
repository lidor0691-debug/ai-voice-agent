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

from app.services.mri_reply_capture import try_capture_probe_reply
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
    # MRI probe-reply hook — if this inbound matches a recent P1 probe,
    # capture it onto the mri_probes row and short-circuit so we do NOT
    # generate a normal customer-style reply to the clinic.
    # Never raises; on any internal failure returns None and we fall
    # through to the existing pipeline unchanged.
    captured = await try_capture_probe_reply(
        customer_phone=req.customer_phone,
        business_phone=req.business_phone,
        user_message=req.user_message,
    )
    if captured is not None:
        return {"reply": "", "messages": []}

    result = await generate_whatsapp_reply(
        customer_phone=req.customer_phone,
        business_phone=req.business_phone,
        user_message=req.user_message,
    )
    return result

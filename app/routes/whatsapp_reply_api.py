"""
app/routes/whatsapp_reply_api.py
==================================
POST /whatsapp/reply — full WhatsApp reply pipeline.

Make.com calls this with the incoming user message and phone number.
Backend handles everything: context assembly, OpenAI call, memory persistence.
Make receives the final reply text and does nothing else.
"""

import logging

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.services.mri_reply_capture import try_capture_probe_reply
from app.services.whatsapp_reply import generate_whatsapp_reply

logger = logging.getLogger(__name__)
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


def _twiml_empty() -> Response:
    return Response(content="<Response></Response>", media_type="application/xml")


def _twiml_message(text: str) -> Response:
    esc = (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return Response(
        content=f"<Response><Message>{esc}</Message></Response>",
        media_type="application/xml",
    )


@router.post("/whatsapp/twilio-inbound")
async def twilio_inbound(request: Request):
    """
    Twilio WhatsApp inbound webhook (form-encoded direct from Twilio).

    Translates Twilio's From / To / Body form fields to our internal
    customer_phone / business_phone / user_message shape, then runs the
    same MRI probe-reply hook and (on no-match) the same
    generate_whatsapp_reply pipeline used by /whatsapp/reply.

    Always returns TwiML XML so Twilio is happy:
      - probe match → empty <Response></Response> (clinic gets no auto-reply)
      - no match + no agent-config for the receiver → empty <Response></Response>
      - no match + agent reply → <Response><Message>...</Message></Response>

    Logs:
      [WA-TWILIO] inbound from=<From> to=<To> chars=<n>
    """
    form = await request.form()
    customer_phone = (form.get("From") or "").strip()
    business_phone = (form.get("To")   or "").strip()
    user_message   = form.get("Body")  or ""

    logger.info(
        "[WA-TWILIO] inbound from=%s to=%s chars=%d",
        customer_phone, business_phone, len(user_message),
    )

    captured = await try_capture_probe_reply(
        customer_phone=customer_phone,
        business_phone=business_phone,
        user_message=user_message,
    )
    if captured is not None:
        return _twiml_empty()

    result = await generate_whatsapp_reply(
        customer_phone=customer_phone,
        business_phone=business_phone,
        user_message=user_message,
    )
    reply_text = (result or {}).get("reply") or ""
    if not reply_text:
        return _twiml_empty()
    return _twiml_message(reply_text)

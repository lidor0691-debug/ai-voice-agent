# agent/whatsapp.py
import logging
from twilio.rest import Client

from agent.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    OWNER_PHONE,
)

logger = logging.getLogger(__name__)
_MAX_MSG_LEN = 1600


def send_to_owner(message: str) -> None:
    """Send a WhatsApp message to the owner via Twilio."""
    if len(message) > _MAX_MSG_LEN:
        message = message[: _MAX_MSG_LEN - 15] + "... [truncated]"
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
            to=f"whatsapp:{OWNER_PHONE}",
            body=message,
        )
        logger.info("WhatsApp sent sid=%s", msg.sid)
    except Exception as exc:
        logger.error("Failed to send WhatsApp: %s", exc)

"""
Twilio client helpers — outbound SMS and any shared Voice utilities.
"""
import logging

from twilio.rest import Client

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _get_client() -> Client:
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


async def send_sms(to: str, body: str) -> bool:
    """
    Send an outbound SMS via Twilio.
    Returns True on success, False on any error.
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured — skipping SMS.")
        return False

    try:
        client = _get_client()
        message = client.messages.create(
            to=to,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=body,
        )
        logger.info("SMS sent | to=%s | sid=%s", to, message.sid)
        return True

    except Exception as exc:
        logger.error("Failed to send SMS to %s: %s", to, exc)
        return False

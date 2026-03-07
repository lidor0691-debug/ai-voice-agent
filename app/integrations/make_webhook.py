"""
Make.com webhook integration.
Sends collected lead data as a JSON POST to the configured webhook URL.
"""
import logging

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


async def send_lead_to_make(lead_data: dict) -> bool:
    """
    POST lead_data to the Make.com webhook.
    Returns True on success, False on any error.
    """
    if not settings.MAKE_WEBHOOK_URL:
        logger.warning("MAKE_WEBHOOK_URL is not configured — skipping webhook.")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.MAKE_WEBHOOK_URL,
                json=lead_data,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info(
                "Lead forwarded to Make.com | call_sid=%s | status=%s",
                lead_data.get("call_sid"),
                response.status_code,
            )
            return True

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Make.com returned HTTP error %s: %s",
            exc.response.status_code,
            exc.response.text,
        )
    except Exception as exc:
        logger.error("Failed to send lead to Make.com: %s", exc)

    return False

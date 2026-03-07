"""
Voice webhook routes — handles all Twilio Voice callbacks.

Flow:
  POST /voice/incoming  — Twilio calls this when a new call arrives
  POST /voice/gather    — Twilio posts speech results here after each <Gather>
"""
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.config.settings import settings
from app.integrations.make_webhook import send_lead_to_make
from app.integrations.twilio_client import send_sms
from app.services.conversation import (
    CLOSING_MESSAGE,
    NO_INPUT_MESSAGE,
    QUESTIONS,
    STEPS,
    clear_session,
    get_or_create_session,
)
from app.services.lead import enrich_lead, format_sms_confirmation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["Voice"])

# AWS Polly Hebrew voice — supported by Twilio
HEBREW_VOICE = "alice"
HEBREW_LANG = "he-IL"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xml_response(twiml: VoiceResponse) -> Response:
    return Response(content=str(twiml), media_type="application/xml")


def _build_gather(question: str, action_url: str) -> VoiceResponse:
    """Return a TwiML response that speaks a question and listens for speech."""
    response = VoiceResponse()

    gather = Gather(
        input="speech",
        action=action_url,
        method="POST",
        language=HEBREW_LANG,
        speech_timeout="auto",
        timeout=6,
    )
    gather.say(question, language=HEBREW_LANG, voice=HEBREW_VOICE)
    response.append(gather)

    # Fallback: if no speech detected, repeat the question
    response.say(NO_INPUT_MESSAGE, language=HEBREW_LANG, voice=HEBREW_VOICE)
    response.redirect(action_url, method="POST")

    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/incoming")
async def incoming_call(
    CallSid: str = Form(...),
    From: str = Form(...),
):
    """Entry point - Twilio hits this when a call is received."""
    logger.info("Incoming call | sid=%s | from=%s", CallSid, From)

    lead = get_or_create_session(CallSid, From)
    question = QUESTIONS[STEPS[0]]
    action_url = f"{settings.BASE_URL}/voice/gather"

    twiml = _build_gather(question, action_url)
    return _xml_response(twiml)
@router.post("/gather")
async def gather_input(
    CallSid: str = Form(...),
    From: str = Form(...),
    SpeechResult: str = Form(default=""),
):
    """Receives speech input, advances the conversation, or closes the lead."""
    lead = get_or_create_session(CallSid, From)
    logger.info(
        "Gather | sid=%s | step=%s | speech=%r",
        CallSid,
        lead.current_step_name,
        SpeechResult,
    )

    if SpeechResult:
        lead.advance(SpeechResult)

    # All questions answered — wrap up
    if lead.is_complete:
        enriched = enrich_lead(lead.to_dict())

        # Fire-and-forget integrations (errors are logged, not raised)
        await send_lead_to_make(enriched)
        await send_sms(
            to=lead.phone_number,
            body=format_sms_confirmation(lead.name, lead.phone_number),
        )

        clear_session(CallSid)
        logger.info("Lead completed | sid=%s | phone=%s", CallSid, From)

        response = VoiceResponse()
        response.say(CLOSING_MESSAGE, language=HEBREW_LANG, voice=HEBREW_VOICE)
        response.hangup()
        return _xml_response(response)

    # Ask the next question
    question = QUESTIONS[lead.current_step_name]
    action_url = f"{settings.BASE_URL}/voice/gather"
    twiml = _build_gather(question, action_url)
    return _xml_response(twiml)

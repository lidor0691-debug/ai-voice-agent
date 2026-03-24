import os
from elevenlabs.client import ElevenLabs

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"

_client: ElevenLabs | None = None


def _get_client() -> ElevenLabs:
    global _client
    if _client is None:
        if not ELEVENLABS_API_KEY:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")
        _client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    return _client


def text_to_speech_bytes(text: str, voice_id: str = VOICE_ID) -> bytes:
    client = _get_client()
    chunks = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )
    return b"".join(chunks)

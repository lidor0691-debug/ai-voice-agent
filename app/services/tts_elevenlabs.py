import os
from elevenlabs.client import ElevenLabs

VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
MODEL_ID = "eleven_flash_v2_5"


class ElevenLabsService:
    def __init__(self) -> None:
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")
        self._client = ElevenLabs(api_key=api_key)

    def text_to_speech_bytes(self, text: str, voice_id: str = VOICE_ID) -> bytes:
        chunks = self._client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=MODEL_ID,
            output_format="mp3_44100_128",
        )
        return b"".join(chunks)

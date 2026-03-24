import sys
import os

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.services.tts_elevenlabs import ElevenLabsService

GREETING = (
    "שלום! הגעת למאיה BPM. "
    "אני כאן כדי לעזור לך עם כל מה שקשור לסטודיו לריקוד שלנו. "
    "את מתעניינת לגבי ריקוד בת מצווה, או שיעורים בסטודיו?"
)

OUTPUT_FILE = "test_output.mp3"


def main() -> None:
    print("Initializing ElevenLabs service...")
    service = ElevenLabsService()

    print(f"Generating audio for: {GREETING[:60]}...")
    audio = service.text_to_speech_bytes(GREETING)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(audio)

    print(f"Saved {len(audio):,} bytes → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

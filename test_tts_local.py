from dotenv import load_dotenv
load_dotenv()

from app.services.tts_elevenlabs import text_to_speech_bytes

audio = text_to_speech_bytes(
    "שלום! הגעת למאיה BPM. את מתעניינת לגבי ריקוד בת מצווה או סטודיו לריקוד?"
)

with open("test_output.mp3", "wb") as f:
    f.write(audio)

print(f"Saved {len(audio)} bytes → test_output.mp3")

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Maya AI"
    BASE_URL: str = "https://your-domain.ngrok.io"
    DEBUG: bool = False

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # Make.com
    MAKE_WEBHOOK_URL: str = ""
     
    OPENAI_API_KEY:str = ""
    CALENDAR_ID: str = ""

    # Supabase
    SUPABASE_URL:      str = ""
    SUPABASE_ANON_KEY: str = ""

    # Gemini Live POC
    GEMINI_API_KEY: str = ""

    # Google Sheets
    # Path to the service account JSON key file downloaded from Google Cloud Console
    GOOGLE_SERVICE_ACCOUNT_JSON: str = "service_account.json"
    # The long ID from the Google Sheet URL:
    # https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit
    GOOGLE_SHEET_ID: str = ""
    # Worksheet tab name (default "Sheet1" / "גיליון1")
    GOOGLE_SHEET_NAME: str = "Sheet1"
    # How long to cache sheet data in seconds (0 = no cache)
    GOOGLE_SHEETS_CACHE_TTL: int = 60

    # Assistant Telegram intake (owner-only). Default OFF + dry-run ON.
    # Persist requires BOTH enabled=true AND dry_run=false.
    ASSISTANT_TELEGRAM_INTAKE_ENABLED: bool = False
    ASSISTANT_TELEGRAM_DRY_RUN: bool = True
    ASSISTANT_TELEGRAM_BOT_TOKEN: str = ""
    ASSISTANT_TELEGRAM_WEBHOOK_SECRET: str = ""
    ASSISTANT_TELEGRAM_ALLOWED_USER_IDS: str = ""   # CSV of numeric ids
    ASSISTANT_TELEGRAM_OWNER_MAP: str = ""          # CSV of "<tg_id>:<owner_uuid>"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

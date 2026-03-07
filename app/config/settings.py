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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

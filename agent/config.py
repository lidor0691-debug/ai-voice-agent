# agent/config.py
import os

# Owner's WhatsApp phone (E.164 format, e.g. "+972501234567")
# The agent ONLY accepts commands from this number.
OWNER_PHONE: str = os.environ["OWNER_PHONE"]

# Twilio credentials (already in .env)
TWILIO_ACCOUNT_SID: str = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN: str = os.environ["TWILIO_AUTH_TOKEN"]
# The Twilio number used to SEND messages back to the owner
TWILIO_PHONE_NUMBER: str = os.environ["TWILIO_PHONE_NUMBER"]

# Anthropic API key (for claude CLI)
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]

# Absolute path to the project root (this repo)
PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Path to the SQLite queue DB file
QUEUE_DB_PATH: str = os.path.join(PROJECT_ROOT, "agent", "agent_queue.db")

# How long (seconds) to wait for owner approval before aborting
APPROVAL_TIMEOUT_SECONDS: int = int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "600"))  # 10 min

# Max retries before giving up on a task
MAX_TASK_RETRIES: int = 2

# Branch where agent does all work
AGENT_BRANCH: str = "agent/work"

# Railway project name (used in CLI commands)
RAILWAY_PROJECT: str = os.getenv("RAILWAY_PROJECT", "maya-ai")

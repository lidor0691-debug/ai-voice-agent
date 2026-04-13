import sys
import io

# Force UTF-8 on stdout/stderr — Railway defaults to ASCII which crashes
# on any Unicode character outside range(128) (e.g. \u2028 from Supabase text).
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import logging

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

from dotenv import load_dotenv
load_dotenv()  # must run before any os.getenv() calls in imported modules

from fastapi import FastAPI
from app.routes.voice_realtime import router as voice_ai_router
from app.routes.assets import router as assets_router
from app.routes.agent_config_api import router as agent_config_router
from app.routes.whatsapp_history_api import router as whatsapp_history_router
from app.routes.whatsapp_reply_api import router as whatsapp_reply_router

app = FastAPI()

# כאן היה חסר ה-prefix! עכשיו הוספנו אותו
app.include_router(voice_ai_router, prefix="/voice-ai")
app.include_router(assets_router, prefix="/assets")
app.include_router(agent_config_router)
app.include_router(whatsapp_history_router)
app.include_router(whatsapp_reply_router)

@app.get("/")
def root():
    return {"status": "Maya AI Realtime is RUNNING"}

@app.get("/health")
def health():
    return {"ok": True}
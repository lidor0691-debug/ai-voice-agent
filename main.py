import sys
import io
import logging

# ── UTF-8 stdout/stderr (Railway defaults to ASCII) ───────────────────────────
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Logging: force UTF-8 handler, replace any pre-existing handlers ───────────
# force=True ensures uvicorn's default ASCII handler is removed first.

class _UnicodeSafeFilter(logging.Filter):
    """Strip \u2028 / \u2029 from log messages before the handler writes them."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = record.msg.replace("\u2028", " ").replace("\u2029", " ")
        record.args = tuple(
            a.replace("\u2028", " ").replace("\u2029", " ") if isinstance(a, str) else a
            for a in (record.args or ())
        )
        return True

_utf8_handler = logging.StreamHandler(sys.stdout)
_utf8_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s"))
_utf8_handler.addFilter(_UnicodeSafeFilter())
logging.basicConfig(
    level=logging.INFO,
    handlers=[_utf8_handler],
    force=True,   # removes any handler already registered (including uvicorn's)
)

# Silence httpx INFO logs — they can contain \u2028 from OpenAI response content
# and uvicorn sets propagate=False on its own loggers so our root filter won't reach them.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Force our UTF-8 filter onto uvicorn's loggers (they use propagate=False + own handlers)
for _uv_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    _uv_logger = logging.getLogger(_uv_logger_name)
    for _h in _uv_logger.handlers:
        _h.addFilter(_UnicodeSafeFilter())
        if hasattr(_h, "stream"):
            _h.stream = sys.stdout

print("WHATSAPP_REPLY_ASCII_FIX_5079D2B", flush=True)

from dotenv import load_dotenv
load_dotenv()  # must run before any os.getenv() calls in imported modules

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.voice_realtime import router as voice_ai_router
from app.routes.assets import router as assets_router
from app.routes.agent_config_api import router as agent_config_router
from app.routes.whatsapp_history_api import router as whatsapp_history_router
from app.routes.whatsapp_reply_api import router as whatsapp_reply_router
from app.routes.dev_agent import router as dev_agent_router
from app.routes.voice_preview import router as voice_preview_router
from app.routes.test_call import router as test_call_router
from app.routes.voice_gemini import router as voice_gemini_router
from app.routes.lead_intelligence_api import router as lead_intelligence_router
from app.routes.appointment_followup_api import router as appointment_followup_router
from app.routes.maya_tts import router as maya_tts_router
from app.routes.maya_nlu import router as maya_nlu_router
from app.routes.maya_insight import router as maya_insight_router
from app.routes.maya_stt import router as maya_stt_router
from app.routes.voice_browser import router as voice_browser_router
from app.routes.action_api import router as action_api_router
from app.routes.action_queue_api import router as action_queue_router
from app.routes.mri_api import router as mri_router
from app.routes.maya_watch import router as maya_watch_router
from app.routes.attribution_api import router as attribution_router
from app.routes.admin_maya_actions import router as admin_maya_actions_router
from app.routes.maya_actions_execute import router as maya_actions_execute_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# כאן היה חסר ה-prefix! עכשיו הוספנו אותו
app.include_router(voice_ai_router, prefix="/voice-ai")
app.include_router(assets_router, prefix="/assets")
app.include_router(agent_config_router)
app.include_router(whatsapp_history_router)
app.include_router(whatsapp_reply_router)
app.include_router(dev_agent_router)
app.include_router(voice_preview_router)
app.include_router(test_call_router)
app.include_router(voice_gemini_router, prefix="/voice-ai")  # Gemini Live POC
app.include_router(lead_intelligence_router)
app.include_router(appointment_followup_router)
app.include_router(maya_tts_router)
app.include_router(maya_nlu_router)
app.include_router(maya_insight_router)
app.include_router(maya_stt_router)
app.include_router(voice_browser_router)
app.include_router(action_api_router)
app.include_router(action_queue_router)
app.include_router(mri_router)
app.include_router(maya_watch_router)
app.include_router(attribution_router)
app.include_router(admin_maya_actions_router)
app.include_router(maya_actions_execute_router)

# Serve mockup files for development (skip if directory doesn't exist, e.g. Railway)
import pathlib
_mockup_dir = ".superpowers/brainstorm/142-1776577129/content"
if pathlib.Path(_mockup_dir).is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/mockup", StaticFiles(directory=_mockup_dir, html=True), name="mockup")

@app.get("/")
def root():
    return {"status": "Maya AI Realtime is RUNNING"}

@app.get("/health")
def health():
    return {"ok": True}
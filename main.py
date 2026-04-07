from dotenv import load_dotenv
load_dotenv()  # must run before any os.getenv() calls in imported modules

from fastapi import FastAPI
from app.routes.voice_realtime import router as voice_ai_router
from app.routes.assets import router as assets_router

app = FastAPI()

# כאן היה חסר ה-prefix! עכשיו הוספנו אותו
app.include_router(voice_ai_router, prefix="/voice-ai")
app.include_router(assets_router, prefix="/assets")

@app.get("/")
def root():
    return {"status": "Maya AI Realtime is RUNNING"}

@app.get("/health")
def health():
    return {"ok": True}
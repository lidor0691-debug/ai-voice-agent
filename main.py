from fastapi import FastAPI
from app.routes.voice_realtime import router as voice_ai_router

app = FastAPI()

# כאן היה חסר ה-prefix! עכשיו הוספנו אותו
app.include_router(voice_ai_router, prefix="/voice-ai")

@app.get("/")
def root():
    return {"status": "Maya AI Realtime is RUNNING"}

@app.get("/health")
def health():
    return {"ok": True}
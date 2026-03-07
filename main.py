from fastapi import FastAPI

from app.routes.voice import router as voice_router
from app.routes.leads import router as leads_router
from app.routes.voice_realtime import router as voice_ai_router

app = FastAPI()

app.include_router(voice_router)
app.include_router(leads_router)
app.include_router(voice_ai_router)


@app.get("/")
def root():
    return {"status": "Maya AI running"}


@app.get("/health")
def health():
    return {"ok": True}
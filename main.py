import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.routes.voice import router as voice_router
from app.routes.leads import router as leads_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    description="AI Voice Assistant for Businesses — Hebrew Speaking",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(voice_router)
app.include_router(leads_router)

# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}

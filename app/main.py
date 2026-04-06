from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.core.config import settings
from app.modules.api.router import router as api_router
from app.modules.ui.router import router as ui_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application startup / shutdown hooks."""
    logger.info("%s starting", settings.APP_NAME)
    logger.info("GicaGen port: %s", settings.GICAGEN_PORT)
    logger.info("GicaTesis base URL: %s", settings.GICATESIS_BASE_URL)
    logger.info("GicaTesis timeout: %ss", settings.GICATESIS_TIMEOUT)
    yield
    logger.info("%s shutting down", settings.APP_NAME)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def no_cache_static_js(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static/js/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ---------------------------------------------------------------------------
# Static files & routers
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(ui_router)
app.include_router(api_router, prefix="/api")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    """Health check endpoint."""
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "gicatesis_url": settings.GICATESIS_BASE_URL,
        "port": settings.GICAGEN_PORT,
    }

from __future__ import annotations

import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.core.config import settings
from app.modules.ui.router import router as ui_router
from app.modules.api.router import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME)


@app.middleware("http")
async def no_cache_static_js(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static/js/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(ui_router)
app.include_router(api_router, prefix="/api")


@app.on_event("startup")
async def startup():
    """Log configuration on startup."""
    logger.info(f"{settings.APP_NAME} starting")
    logger.info(f"GicaGen port: {settings.GICAGEN_PORT}")
    logger.info(f"GicaTesis base URL: {settings.GICATESIS_BASE_URL}")
    logger.info(f"GicaTesis timeout: {settings.GICATESIS_TIMEOUT}s")


@app.get("/healthz")
def healthz():
    """Health check endpoint."""
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "gicatesis_url": settings.GICATESIS_BASE_URL,
        "port": settings.GICAGEN_PORT
    }


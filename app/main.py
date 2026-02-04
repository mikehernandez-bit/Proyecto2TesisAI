from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.modules.ui.router import router as ui_router
from app.modules.api.router import router as api_router

app = FastAPI(title=settings.APP_NAME)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(ui_router)
app.include_router(api_router, prefix="/api")

@app.get("/healthz")
def healthz():
    return {"ok": True, "app": settings.APP_NAME, "env": settings.APP_ENV}

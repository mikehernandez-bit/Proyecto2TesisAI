from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.core.config import settings
from app.core.templates import templates

router = APIRouter()
_APP_JS_PATH = Path("app/static/js/app.js")


def _asset_version() -> str:
    try:
        return str(_APP_JS_PATH.stat().st_mtime_ns)
    except OSError:
        return "dev"


@router.get("/")
def home(request: Request):
    response: Response = templates.TemplateResponse(
        "pages/app.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "asset_version": _asset_version(),
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

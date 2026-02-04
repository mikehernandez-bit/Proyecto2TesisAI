from __future__ import annotations
from fastapi import APIRouter, Request
from app.core.templates import templates
from app.core.config import settings

router = APIRouter()

@router.get("/")
def home(request: Request):
    return templates.TemplateResponse("pages/app.html", {"request": request, "app_name": settings.APP_NAME})

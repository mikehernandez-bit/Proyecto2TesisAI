from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()  # Load .env file if present


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _get_bool(key: str, default: bool = False) -> bool:
    raw = _get(key, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    APP_NAME: str = _get("APP_NAME", "TesisAI Gen")
    APP_ENV: str = _get("APP_ENV", "dev")

    # Legacy format API (deprecated, use GICATESIS_* instead)
    FORMAT_API_BASE_URL: str = _get("FORMAT_API_BASE_URL", "")
    FORMAT_API_KEY: str = _get("FORMAT_API_KEY", "")
    
    # GicaTesis Integration
    GICATESIS_BASE_URL: str = _get("GICATESIS_BASE_URL", "http://localhost:8000/api/v1")
    GICATESIS_API_KEY: str = _get("GICATESIS_API_KEY", "")
    GICAGEN_PORT: int = int(_get("GICAGEN_PORT", "8001"))
    GICAGEN_BASE_URL: str = _get("GICAGEN_BASE_URL", "http://localhost:8001")
    GICATESIS_TIMEOUT: int = int(_get("GICATESIS_TIMEOUT", "8"))
    GICAGEN_DEMO_MODE: bool = _get_bool("GICAGEN_DEMO_MODE", False)
    
    # n8n Integration
    N8N_WEBHOOK_URL: str = _get("N8N_WEBHOOK_URL", "")
    N8N_SHARED_SECRET: str = _get("N8N_SHARED_SECRET", "")


    # Gemini AI
    GEMINI_API_KEY: str = _get("GEMINI_API_KEY", "")

settings = Settings()

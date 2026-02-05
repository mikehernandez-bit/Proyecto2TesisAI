from __future__ import annotations

import os
from dataclasses import dataclass

def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)

@dataclass(frozen=True)
class Settings:
    APP_NAME: str = _get("APP_NAME", "TesisAI Gen")
    APP_ENV: str = _get("APP_ENV", "dev")

    # Legacy format API (deprecated, use GICATESIS_* instead)
    FORMAT_API_BASE_URL: str = _get("FORMAT_API_BASE_URL", "")
    FORMAT_API_KEY: str = _get("FORMAT_API_KEY", "")
    
    # GicaTesis Integration
    GICATESIS_BASE_URL: str = _get("GICATESIS_BASE_URL", "http://localhost:8000/api/v1")
    GICAGEN_PORT: int = int(_get("GICAGEN_PORT", "8001"))
    GICATESIS_TIMEOUT: int = int(_get("GICATESIS_TIMEOUT", "8"))
    
    # n8n Integration
    N8N_WEBHOOK_URL: str = _get("N8N_WEBHOOK_URL", "")

settings = Settings()


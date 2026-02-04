from __future__ import annotations

import os
from dataclasses import dataclass

def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)

@dataclass(frozen=True)
class Settings:
    APP_NAME: str = _get("APP_NAME", "TesisAI Gen")
    APP_ENV: str = _get("APP_ENV", "dev")

    FORMAT_API_BASE_URL: str = _get("FORMAT_API_BASE_URL", "")
    FORMAT_API_KEY: str = _get("FORMAT_API_KEY", "")
    N8N_WEBHOOK_URL: str = _get("N8N_WEBHOOK_URL", "")

settings = Settings()

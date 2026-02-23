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

    # GicaTesis integration
    GICATESIS_BASE_URL: str = _get("GICATESIS_BASE_URL", "http://localhost:8000/api/v1")
    GICATESIS_API_KEY: str = _get("GICATESIS_API_KEY", "")
    GICAGEN_PORT: int = int(_get("GICAGEN_PORT", "8001"))
    GICAGEN_BASE_URL: str = _get("GICAGEN_BASE_URL", "http://localhost:8001")
    GICATESIS_TIMEOUT: int = int(_get("GICATESIS_TIMEOUT", "8"))
    GICAGEN_DEMO_MODE: bool = _get_bool("GICAGEN_DEMO_MODE", False)
    GICAGEN_STRICT_GICATESIS: bool = _get_bool("GICAGEN_STRICT_GICATESIS", False)

    # n8n integration (deprecated)
    N8N_WEBHOOK_URL: str = _get("N8N_WEBHOOK_URL", "")
    N8N_SHARED_SECRET: str = _get("N8N_SHARED_SECRET", "")

    # AI provider selection
    AI_PRIMARY_PROVIDER: str = _get("AI_PRIMARY_PROVIDER", "gemini").lower()
    AI_FALLBACK_ON_QUOTA: bool = _get_bool("AI_FALLBACK_ON_QUOTA", True)
    AI_FORCE_FALLBACK_ON_TRANSIENT: bool = _get_bool("AI_FORCE_FALLBACK_ON_TRANSIENT", True)
    AI_CORRECTION_ENABLED: bool = _get_bool("AI_CORRECTION_ENABLED", True)
    AI_LOCAL_RATE_LIMIT_PER_MINUTE: int = int(_get("AI_LOCAL_RATE_LIMIT_PER_MINUTE", "60"))
    AI_LOCAL_QUOTA_LIMIT_TOKENS_MONTH: int = int(_get("AI_LOCAL_QUOTA_LIMIT_TOKENS_MONTH", "0"))

    # LLM resilience controls
    MAX_INFLIGHT_MISTRAL: int = int(_get("MAX_INFLIGHT_MISTRAL", "3"))
    MAX_INFLIGHT_GEMINI: int = int(_get("MAX_INFLIGHT_GEMINI", "3"))
    MAX_INFLIGHT_PER_TENANT: int = int(_get("MAX_INFLIGHT_PER_TENANT", "2"))
    MISTRAL_RPM: int = int(_get("MISTRAL_RPM", "60"))
    GEMINI_RPM: int = int(_get("GEMINI_RPM", "60"))
    RETRY_JITTER: float = float(_get("RETRY_JITTER", "0.3"))
    RETRY_CAP_SECONDS: float = float(_get("RETRY_CAP_SECONDS", "30"))
    CB_FAILURES: int = int(_get("CB_FAILURES", "5"))
    CB_WINDOW_SEC: int = int(_get("CB_WINDOW_SEC", "60"))
    CB_OPEN_SEC: int = int(_get("CB_OPEN_SEC", "120"))
    CB_HALF_OPEN_MAX_TRIALS: int = int(_get("CB_HALF_OPEN_MAX_TRIALS", "2"))
    FALLBACK_CHAIN_GENERATE: str = _get("FALLBACK_CHAIN_GENERATE", "mistral,provider_b,provider_c")
    FALLBACK_CHAIN_CLEANUP: str = _get("FALLBACK_CHAIN_CLEANUP", "mistral,cheap_model,DEGRADED")
    LLM_MAX_INPUT_TOKENS_GENERATE: int = int(_get("LLM_MAX_INPUT_TOKENS_GENERATE", "6000"))
    LLM_MAX_OUTPUT_TOKENS_GENERATE: int = int(_get("LLM_MAX_OUTPUT_TOKENS_GENERATE", "1400"))
    LLM_MAX_INPUT_TOKENS_CLEANUP: int = int(_get("LLM_MAX_INPUT_TOKENS_CLEANUP", "3500"))
    LLM_MAX_OUTPUT_TOKENS_CLEANUP: int = int(_get("LLM_MAX_OUTPUT_TOKENS_CLEANUP", "900"))

    # Gemini integration
    GEMINI_API_KEY: str = _get("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = _get("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_TEMPERATURE: float = float(_get("GEMINI_TEMPERATURE", "0.7"))
    GEMINI_MAX_OUTPUT_TOKENS: int = int(_get("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
    GEMINI_TOP_P: float = float(_get("GEMINI_TOP_P", "0.95"))
    GEMINI_RETRY_MAX: int = int(_get("GEMINI_RETRY_MAX", "3"))
    GEMINI_RETRY_BACKOFF: float = float(_get("GEMINI_RETRY_BACKOFF", "2.0"))

    # Mistral integration
    MISTRAL_API_KEY: str = _get("MISTRAL_API_KEY", "")
    MISTRAL_BASE_URL: str = _get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
    MISTRAL_MODEL: str = _get("MISTRAL_MODEL", "mistral-medium-2505")
    MISTRAL_TEMPERATURE: float = float(_get("MISTRAL_TEMPERATURE", "0.7"))
    MISTRAL_MAX_TOKENS: int = int(_get("MISTRAL_MAX_TOKENS", "4096"))
    MISTRAL_RETRY_MAX: int = int(_get("MISTRAL_RETRY_MAX", "5"))
    MISTRAL_RETRY_BACKOFF: float = float(_get("MISTRAL_RETRY_BACKOFF", "3.0"))


settings = Settings()

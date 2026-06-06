"""Persistence for provider/model selection used by AI generation."""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings

_PROVIDER_ORDER = ("mistral",)
_PROVIDERS = set(_PROVIDER_ORDER)


def _default_model(provider: str) -> str:
    if provider == "mistral":
        return str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))
    return str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))


def _fallback_for(provider: str) -> str:
    return ""


def _matches_provider_model(provider: str, model: str) -> bool:
    normalized = str(model or "").strip().lower()
    if not normalized:
        return False
    if provider == "mistral":
        return "mistral" in normalized
    return False


def _default_selection() -> Dict[str, str]:
    primary = "mistral"
    if primary not in _PROVIDERS:
        primary = _PROVIDER_ORDER[0]
    return {
        "provider": primary,
        "model": _default_model(primary),
        "fallback_provider": "",
        "fallback_model": "",
        "mode": "fixed",
    }


class ProviderSelectionService:
    """Stores global provider selection in a small JSON file."""

    def __init__(self, path: str = "data/provider_selection.json") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read_raw(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_raw(self, payload: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _normalize(payload: Dict[str, Any]) -> Dict[str, str]:
        provider = "mistral"
        fallback_provider = ""

        model = str(payload.get("model") or "").strip()
        if not model or not _matches_provider_model(provider, model):
            model = _default_model(provider)

        fallback_model = ""
        mode = "fixed"

        return {
            "provider": provider,
            "model": model,
            "fallback_provider": fallback_provider,
            "fallback_model": fallback_model,
            "mode": mode,
        }

    def get_selection(self) -> Dict[str, str]:
        with self._lock:
            normalized = self._normalize(self._read_raw())
            return dict(normalized)

    def normalize(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """Normalize selection payload without persisting it."""
        with self._lock:
            return dict(self._normalize(payload))

    def set_selection(self, payload: Dict[str, Any]) -> Dict[str, str]:
        with self._lock:
            normalized = self._normalize(payload)
            persisted = dict(normalized)
            persisted["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            self._write_raw(persisted)
            return dict(normalized)

"""Persistence for provider/model selection used by AI generation."""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings

_PROVIDERS = {"gemini", "mistral"}
_MODES = {"fixed", "auto"}


def _default_selection() -> Dict[str, str]:
    primary = str(getattr(settings, "AI_PRIMARY_PROVIDER", "gemini") or "gemini").lower().strip()
    if primary not in _PROVIDERS:
        primary = "gemini"
    fallback = "mistral" if primary == "gemini" else "gemini"
    return {
        "provider": primary,
        "model": (
            str(getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"))
            if primary == "gemini"
            else str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))
        ),
        "fallback_provider": fallback,
        "fallback_model": (
            str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))
            if fallback == "mistral"
            else str(getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"))
        ),
        "mode": "auto",
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
        base = _default_selection()
        provider = str(payload.get("provider") or base["provider"]).lower().strip()
        if provider not in _PROVIDERS:
            provider = base["provider"]

        fallback_provider = str(payload.get("fallback_provider") or base["fallback_provider"]).lower().strip()
        if fallback_provider not in _PROVIDERS or fallback_provider == provider:
            fallback_provider = "mistral" if provider == "gemini" else "gemini"

        model = str(payload.get("model") or "").strip()
        if not model:
            model = (
                str(getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"))
                if provider == "gemini"
                else str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))
            )

        fallback_model = str(payload.get("fallback_model") or "").strip()
        if not fallback_model:
            fallback_model = (
                str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))
                if fallback_provider == "mistral"
                else str(getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"))
            )

        mode = str(payload.get("mode") or base["mode"]).lower().strip()
        if mode not in _MODES:
            mode = "auto"

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

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_LOCKS: Dict[str, threading.Lock] = {}
_STALE_TEMP_SECONDS = 60.0
_ATOMIC_REPLACE_ATTEMPTS = 80
_DIRECT_WRITE_ATTEMPTS = 60


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    if key not in _LOCKS:
        _LOCKS[key] = threading.Lock()
    return _LOCKS[key]


class JsonStore:
    """Simple JSON file store (list-based). Good for MVP/demo."""

    def __init__(self, path: str):
        candidate = Path(path)
        if candidate.is_absolute():
            self.path = candidate
        else:
            # Resolve repository-relative paths (e.g. data/projects.json)
            # so behavior is stable even when process CWD changes (uvicorn reload).
            repo_root = Path(__file__).resolve().parents[3]
            self.path = (repo_root / candidate).resolve()

    @staticmethod
    def _cleanup_temp_files(path: Path, *, min_age_seconds: float = _STALE_TEMP_SECONDS) -> None:
        parent = path.parent
        if not parent.exists():
            return
        cutoff = time.time() - min_age_seconds
        pattern = f".{path.name}.*.tmp"
        for temp_path in parent.glob(pattern):
            try:
                if min_age_seconds > 0 and temp_path.stat().st_mtime > cutoff:
                    continue
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove stale temp file %s", temp_path, exc_info=True)

    @staticmethod
    def _write_text_direct_with_retries(path: Path, text: str) -> None:
        last_error: OSError | None = None
        for attempt in range(_DIRECT_WRITE_ATTEMPTS):
            try:
                path.write_text(text, encoding="utf-8")
                return
            except OSError as exc:
                last_error = exc
                time.sleep(min(0.05 + (attempt * 0.01), 0.35))
        if last_error is not None:
            raise last_error

    @classmethod
    def _write_text_atomic(cls, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        cls._cleanup_temp_files(path)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(text, encoding="utf-8")
        except OSError:
            logger.exception("Could not write temp file for %s", path)
            temp_path.unlink(missing_ok=True)
            raise
        last_error: OSError | None = None
        for attempt in range(_ATOMIC_REPLACE_ATTEMPTS):
            try:
                os.replace(temp_path, path)
                cls._cleanup_temp_files(path)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(min(0.05 + (attempt * 0.01), 0.35))
        logger.warning(
            "Atomic replace failed for %s; falling back to direct write",
            path,
        )
        try:
            cls._write_text_direct_with_retries(path, text)
        except OSError as exc:
            if last_error is not None:
                raise exc from last_error
            raise
        finally:
            temp_path.unlink(missing_ok=True)
            cls._cleanup_temp_files(path)

    def read_list(self) -> List[Dict[str, Any]]:
        lock = _lock_for(self.path)
        with lock:
            if not self.path.exists():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._write_text_atomic(self.path, "[]")
            raw = self.path.read_text(encoding="utf-8").strip() or "[]"
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # Attempt to recover the first valid JSON array.
                logger.warning("Corrupted JSON in %s — attempting recovery", self.path)
                try:
                    obj, _ = json.JSONDecoder().raw_decode(raw)
                    if isinstance(obj, list):
                        # Auto-heal: rewrite the file with the valid portion.
                        self._write_text_atomic(self.path, json.dumps(obj, indent=2, ensure_ascii=False))
                        logger.info("Recovered %d items from %s", len(obj), self.path)
                        return obj
                except (json.JSONDecodeError, ValueError):
                    pass
                # Unrecoverable — reset to empty list to unblock the app.
                logger.error(
                    "Unrecoverable JSON in %s — resetting to empty list",
                    self.path,
                )
                self._write_text_atomic(self.path, "[]")
                return []

    def write_list(self, items: List[Dict[str, Any]]) -> None:
        lock = _lock_for(self.path)
        with lock:
            self._write_text_atomic(self.path, json.dumps(items, indent=2, ensure_ascii=False))

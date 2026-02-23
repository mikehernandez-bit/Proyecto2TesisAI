from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_LOCKS: Dict[str, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    if key not in _LOCKS:
        _LOCKS[key] = threading.Lock()
    return _LOCKS[key]


class JsonStore:
    """Simple JSON file store (list-based). Good for MVP/demo."""

    def __init__(self, path: str):
        self.path = Path(path)

    def read_list(self) -> List[Dict[str, Any]]:
        lock = _lock_for(self.path)
        with lock:
            if not self.path.exists():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text("[]", encoding="utf-8")
            raw = self.path.read_text(encoding="utf-8").strip() or "[]"
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # Attempt to recover the first valid JSON array.
                logger.warning(
                    "Corrupted JSON in %s — attempting recovery", self.path
                )
                try:
                    obj, _ = json.JSONDecoder().raw_decode(raw)
                    if isinstance(obj, list):
                        # Auto-heal: rewrite the file with the valid portion.
                        self.path.write_text(
                            json.dumps(obj, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        logger.info(
                            "Recovered %d items from %s", len(obj), self.path
                        )
                        return obj
                except (json.JSONDecodeError, ValueError):
                    pass
                # Unrecoverable — reset to empty list to unblock the app.
                logger.error(
                    "Unrecoverable JSON in %s — resetting to empty list",
                    self.path,
                )
                self.path.write_text("[]", encoding="utf-8")
                return []

    def write_list(self, items: List[Dict[str, Any]]) -> None:
        lock = _lock_for(self.path)
        with lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(items, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

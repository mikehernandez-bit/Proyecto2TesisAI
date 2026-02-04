from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

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
            return json.loads(raw)

    def write_list(self, items: List[Dict[str, Any]]) -> None:
        lock = _lock_for(self.path)
        with lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

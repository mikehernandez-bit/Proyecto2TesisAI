from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.storage.json_store import JsonStore
from app.core.utils.id import new_id

class ProjectService:
    """Stores generation projects (history + status)."""

    def __init__(self, path: str = "data/projects.json"):
        self.store = JsonStore(path)

    def list_projects(self) -> List[Dict[str, Any]]:
        return self.store.read_list()

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        for p in self.store.read_list():
            if p.get("id") == project_id:
                return p
        return None

    def create_project(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        items = self.store.read_list()
        project = {
            "id": new_id("proj"),
            "title": payload.get("title") or payload.get("tema") or "Proyecto sin título",
            "prompt_id": payload.get("prompt_id"),
            "prompt_name": payload.get("prompt_name"),
            "format_id": payload.get("format_id"),
            "format_name": payload.get("format_name"),
            "status": "processing",
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "output_file": None,
            "error": None,
        }
        items.insert(0, project)
        self.store.write_list(items)
        return project

    def mark_completed(self, project_id: str, output_file: str) -> Optional[Dict[str, Any]]:
        items = self.store.read_list()
        for i, p in enumerate(items):
            if p.get("id") == project_id:
                p["status"] = "completed"
                p["output_file"] = output_file
                p["error"] = None
                items[i] = p
                self.store.write_list(items)
                return p
        return None

    def mark_failed(self, project_id: str, error: str) -> Optional[Dict[str, Any]]:
        items = self.store.read_list()
        for i, p in enumerate(items):
            if p.get("id") == project_id:
                p["status"] = "failed"
                p["error"] = error
                items[i] = p
                self.store.write_list(items)
                return p
        return None

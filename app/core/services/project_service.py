from __future__ import annotations

import datetime as dt
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
        now = dt.datetime.now().isoformat(timespec="seconds")
        values = payload.get("variables")
        if values is None:
            values = payload.get("values", {})
        project = {
            "id": new_id("proj"),
            "title": payload.get("title") or payload.get("tema") or "Proyecto sin titulo",
            "prompt_id": payload.get("prompt_id"),
            "prompt_name": payload.get("prompt_name"),
            "prompt_template": payload.get("prompt_template"),
            "format_id": payload.get("format_id"),
            "format_name": payload.get("format_name"),
            "format_version": payload.get("format_version"),
            "variables": values or {},
            # Keep both keys for backward compatibility in UI and contracts.
            "values": values or {},
            "status": payload.get("status") or "processing",
            "created_at": now,
            "updated_at": now,
            "output_file": None,
            "error": None,
            "ai_result": None,
            "run_id": None,
            "artifacts": [],
        }
        items.insert(0, project)
        self.store.write_list(items)
        return project

    def update_project(self, project_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        items = self.store.read_list()
        for i, p in enumerate(items):
            if p.get("id") != project_id:
                continue

            if "title" in payload and payload.get("title") is not None:
                p["title"] = payload.get("title") or p.get("title")
            if "prompt_id" in payload and payload.get("prompt_id") is not None:
                p["prompt_id"] = payload.get("prompt_id")
            if "prompt_name" in payload and payload.get("prompt_name") is not None:
                p["prompt_name"] = payload.get("prompt_name")
            if "prompt_template" in payload and payload.get("prompt_template") is not None:
                p["prompt_template"] = payload.get("prompt_template")
            if "format_id" in payload and payload.get("format_id") is not None:
                p["format_id"] = payload.get("format_id")
            if "format_name" in payload and payload.get("format_name") is not None:
                p["format_name"] = payload.get("format_name")
            if "format_version" in payload and payload.get("format_version") is not None:
                p["format_version"] = payload.get("format_version")
            if "status" in payload and payload.get("status") is not None:
                p["status"] = payload.get("status")

            if "variables" in payload or "values" in payload:
                values = payload.get("variables")
                if values is None:
                    values = payload.get("values", {})
                p["variables"] = values or {}
                p["values"] = values or {}

            p["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
            items[i] = p
            self.store.write_list(items)
            return p
        return None

    def mark_completed(self, project_id: str, output_file: str) -> Optional[Dict[str, Any]]:
        items = self.store.read_list()
        for i, p in enumerate(items):
            if p.get("id") == project_id:
                p["status"] = "completed"
                p["output_file"] = output_file
                p["error"] = None
                p["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
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
                p["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
                items[i] = p
                self.store.write_list(items)
                return p
        return None

    def mark_ai_received(
        self,
        project_id: str,
        ai_result: Dict[str, Any],
        run_id: Optional[str] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Persist AI payload received from n8n callback."""
        items = self.store.read_list()
        for i, p in enumerate(items):
            if p.get("id") == project_id:
                p["status"] = "ai_received"
                p["ai_result"] = ai_result
                p["run_id"] = run_id
                p["artifacts"] = artifacts or []
                p["error"] = None
                p["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
                items[i] = p
                self.store.write_list(items)
                return p
        return None

    def mark_simulated(
        self,
        project_id: str,
        ai_result: Dict[str, Any],
        run_id: str,
        artifacts: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Persist latest simulation run output for n8n guide/demo downloads."""
        items = self.store.read_list()
        for i, p in enumerate(items):
            if p.get("id") != project_id:
                continue

            p["status"] = "simulated"
            p["ai_result"] = ai_result
            p["run_id"] = run_id
            p["artifacts"] = artifacts
            p["error"] = None
            p["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
            items[i] = p
            self.store.write_list(items)
            return p
        return None

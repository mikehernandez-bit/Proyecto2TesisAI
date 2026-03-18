from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, List, Optional

from app.core.services.ai.token_usage import (
    empty_token_usage_report,
    empty_token_usage_summary,
    normalize_token_usage_report,
    normalize_token_usage_snapshot,
)
from app.core.storage.json_store import JsonStore
from app.core.utils.id import new_id

_TRACE_MAX_EVENTS = 200


class ProjectService:
    """Stores generation projects (history + status)."""

    def __init__(self, path: str = "data/projects.json"):
        self.store = JsonStore(path)

    @staticmethod
    def _default_progress(*, provider: str = "") -> Dict[str, Any]:
        return {
            "current": 0,
            "total": 0,
            "currentPath": "",
            "provider": provider,
            "tokenUsage": empty_token_usage_summary(),
            "updatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def _empty_generation_snapshot() -> Dict[str, Any]:
        return {
            "saved_sections_count": 0,
            "total_sections": 0,
            "current_path": "",
            "completed_sections": [],
            "tokenUsage": empty_token_usage_summary(),
            "source_run_id": "",
            "status": "idle",
            "updated_at": "",
        }

    @staticmethod
    def _empty_generation_phase() -> Dict[str, Any]:
        return {
            "status": "idle",
            "base_prompt": "",
            "current_section_id": "",
            "current_section_path": "",
            "total_sections": 0,
            "completed_sections": 0,
            "planned_sections": [],
            "sections": [],
            "started_at": "",
            "updated_at": "",
            "finished_at": "",
        }

    @staticmethod
    def _empty_construction_phase() -> Dict[str, Any]:
        return {
            "status": "idle",
            "current_task": "",
            "tasks": [],
            "started_at": "",
            "updated_at": "",
            "finished_at": "",
        }

    @staticmethod
    def _empty_resume(*, format_version: str = "") -> Dict[str, Any]:
        return {
            "eligible": False,
            "saved_sections_count": 0,
            "resume_from_index": 0,
            "last_failed_section_path": "",
            "format_version": str(format_version or ""),
            "base_run_id": "",
            "retry_count": 0,
            "reason": "",
            "updated_at": "",
        }

    @staticmethod
    def _empty_wizard_state() -> Dict[str, Any]:
        return {
            "current_step": 1,
            "last_completed_step": 1,
            "last_open_mode": "new",
            "updated_at": "",
        }

    @classmethod
    def _normalize_resume(
        cls,
        resume_raw: Any,
        *,
        format_version: str = "",
    ) -> Dict[str, Any]:
        base = cls._empty_resume(format_version=format_version)
        if not isinstance(resume_raw, dict):
            return base
        base.update(
            {
                "eligible": bool(resume_raw.get("eligible")),
                "saved_sections_count": max(0, int(resume_raw.get("saved_sections_count") or 0)),
                "resume_from_index": max(0, int(resume_raw.get("resume_from_index") or 0)),
                "last_failed_section_path": str(resume_raw.get("last_failed_section_path") or ""),
                "format_version": str(resume_raw.get("format_version") or format_version or ""),
                "base_run_id": str(resume_raw.get("base_run_id") or ""),
                "retry_count": max(0, int(resume_raw.get("retry_count") or 0)),
                "reason": str(resume_raw.get("reason") or ""),
                "updated_at": str(resume_raw.get("updated_at") or ""),
            }
        )
        return base

    @classmethod
    def _normalize_wizard_state(cls, raw: Any) -> Dict[str, Any]:
        base = cls._empty_wizard_state()
        if not isinstance(raw, dict):
            return base
        current_step_raw = raw["current_step"] if "current_step" in raw else raw.get("currentStep")
        last_completed_raw = (
            raw["last_completed_step"] if "last_completed_step" in raw else raw.get("lastCompletedStep")
        )
        last_open_mode_raw = raw["last_open_mode"] if "last_open_mode" in raw else raw.get("lastOpenMode")
        updated_at_raw = raw["updated_at"] if "updated_at" in raw else raw.get("updatedAt")
        base.update(
            {
                "current_step": min(7, max(1, int(current_step_raw or 1))),
                "last_completed_step": min(
                    7,
                    max(1, int(last_completed_raw or 1)),
                ),
                "last_open_mode": str(last_open_mode_raw or "new"),
                "updated_at": str(updated_at_raw or ""),
            }
        )
        if base["last_completed_step"] < base["current_step"]:
            base["last_completed_step"] = base["current_step"]
        return base

    @classmethod
    def _merge_wizard_state(cls, current_raw: Any, incoming_raw: Any) -> Dict[str, Any]:
        current = cls._normalize_wizard_state(current_raw)
        if not isinstance(incoming_raw, dict):
            return current

        if "current_step" in incoming_raw or "currentStep" in incoming_raw:
            current["current_step"] = cls._normalize_wizard_state(incoming_raw)["current_step"]
        if "last_completed_step" in incoming_raw or "lastCompletedStep" in incoming_raw:
            current["last_completed_step"] = cls._normalize_wizard_state(incoming_raw)["last_completed_step"]
        if "last_open_mode" in incoming_raw or "lastOpenMode" in incoming_raw:
            current["last_open_mode"] = cls._normalize_wizard_state(incoming_raw)["last_open_mode"]
        if "updated_at" in incoming_raw or "updatedAt" in incoming_raw:
            current["updated_at"] = cls._normalize_wizard_state(incoming_raw)["updated_at"]
        return cls._normalize_wizard_state(current)

    @classmethod
    def _normalize_generation_phase(cls, raw: Any) -> Dict[str, Any]:
        base = cls._empty_generation_phase()
        if not isinstance(raw, dict):
            return base

        normalized_sections: List[Dict[str, Any]] = []
        planned_sections: List[Dict[str, Any]] = []
        raw_planned_sections = raw.get("planned_sections")
        if isinstance(raw_planned_sections, list):
            for item in raw_planned_sections:
                if not isinstance(item, dict):
                    continue
                section_id = str(item.get("section_id") or item.get("sectionId") or "").strip()
                section_path = str(
                    item.get("section_path") or item.get("sectionPath") or item.get("path") or ""
                ).strip()
                section_title = str(item.get("section_title") or item.get("sectionTitle") or "").strip() or (
                    section_path.split("/")[-1].strip() if section_path else ""
                )
                if not section_id and not section_path:
                    continue
                planned_sections.append(
                    {
                        "section_id": section_id,
                        "section_path": section_path,
                        "section_title": section_title,
                        "parent_section_path": str(
                            item.get("parent_section_path") or item.get("sectionParentPath") or ""
                        ),
                        "section_level": max(1, int(item.get("section_level") or item.get("sectionLevel") or 1)),
                    }
                )
        raw_sections = raw.get("sections")
        if isinstance(raw_sections, list):
            for item in raw_sections:
                if not isinstance(item, dict):
                    continue
                section_id = str(item.get("section_id") or item.get("sectionId") or "").strip()
                section_path = str(item.get("section_path") or item.get("path") or "").strip()
                section_title = str(item.get("section_title") or "").strip() or (
                    section_path.split("/")[-1].strip() if section_path else ""
                )
                if not section_id and not section_path:
                    continue
                attempts = item.get("attempts")
                normalized_attempts = (
                    [entry for entry in attempts if isinstance(entry, dict)] if isinstance(attempts, list) else []
                )
                normalized_sections.append(
                    {
                        "section_id": section_id,
                        "section_path": section_path,
                        "section_title": section_title,
                        "parent_section_path": str(
                            item.get("parent_section_path") or item.get("sectionParentPath") or ""
                        ),
                        "section_level": max(1, int(item.get("section_level") or item.get("sectionLevel") or 1)),
                        "prompt_sent": str(item.get("prompt_sent") or ""),
                        "ai_output": str(item.get("ai_output") or ""),
                        "input_tokens": max(0, int(item.get("input_tokens") or 0)),
                        "output_tokens": max(0, int(item.get("output_tokens") or 0)),
                        "total_tokens": max(0, int(item.get("total_tokens") or 0)),
                        "model": str(item.get("model") or ""),
                        "provider": str(item.get("provider") or ""),
                        "status": str(item.get("status") or "pending"),
                        "duration_ms": max(0, int(item.get("duration_ms") or 0)),
                        "estimated": bool(item.get("estimated")),
                        "source": str(item.get("source") or ""),
                        "attempt_count": max(0, int(item.get("attempt_count") or len(normalized_attempts) or 0)),
                        "attempts": normalized_attempts,
                        "error": str(item.get("error") or ""),
                        "started_at": str(item.get("started_at") or ""),
                        "completed_at": str(item.get("completed_at") or ""),
                        "updated_at": str(item.get("updated_at") or ""),
                    }
                )

        base.update(
            {
                "status": str(raw.get("status") or "idle"),
                "base_prompt": str(raw.get("base_prompt") or ""),
                "current_section_id": str(raw.get("current_section_id") or ""),
                "current_section_path": str(raw.get("current_section_path") or ""),
                "total_sections": max(0, int(raw.get("total_sections") or 0)),
                "completed_sections": max(0, int(raw.get("completed_sections") or 0)),
                "planned_sections": planned_sections,
                "sections": normalized_sections,
                "started_at": str(raw.get("started_at") or ""),
                "updated_at": str(raw.get("updated_at") or ""),
                "finished_at": str(raw.get("finished_at") or ""),
            }
        )
        return base

    @classmethod
    def _normalize_construction_phase(cls, raw: Any) -> Dict[str, Any]:
        base = cls._empty_construction_phase()
        if not isinstance(raw, dict):
            return base

        tasks_raw = raw.get("tasks")
        normalized_tasks: List[Dict[str, Any]] = []
        if isinstance(tasks_raw, list):
            for item in tasks_raw:
                if not isinstance(item, dict):
                    continue
                task_id = str(item.get("id") or "").strip()
                label = str(item.get("label") or "").strip()
                if not task_id and not label:
                    continue
                normalized_tasks.append(
                    {
                        "id": task_id,
                        "label": label,
                        "status": str(item.get("status") or "pending"),
                        "detail": str(item.get("detail") or ""),
                        "updated_at": str(item.get("updated_at") or ""),
                    }
                )

        base.update(
            {
                "status": str(raw.get("status") or "idle"),
                "current_task": str(raw.get("current_task") or ""),
                "tasks": normalized_tasks,
                "started_at": str(raw.get("started_at") or ""),
                "updated_at": str(raw.get("updated_at") or ""),
                "finished_at": str(raw.get("finished_at") or ""),
            }
        )
        return base

    @classmethod
    def _normalize_generation_snapshot(cls, raw: Any) -> Dict[str, Any]:
        base = cls._empty_generation_snapshot()
        if not isinstance(raw, dict):
            return base
        completed_sections_raw = raw.get("completed_sections")
        completed_sections: List[Dict[str, str]] = []
        if isinstance(completed_sections_raw, list):
            for item in completed_sections_raw:
                if not isinstance(item, dict):
                    continue
                section_id = str(item.get("sectionId") or item.get("section_id") or "").strip()
                path = str(item.get("path") or item.get("section_path") or "").strip()
                if not section_id and not path:
                    continue
                completed_sections.append(
                    {
                        "sectionId": section_id,
                        "path": path,
                    }
                )
        base.update(
            {
                "saved_sections_count": max(0, int(raw.get("saved_sections_count") or len(completed_sections) or 0)),
                "total_sections": max(0, int(raw.get("total_sections") or 0)),
                "current_path": str(raw.get("current_path") or ""),
                "completed_sections": completed_sections,
                "tokenUsage": normalize_token_usage_snapshot(raw.get("tokenUsage")),
                "source_run_id": str(raw.get("source_run_id") or ""),
                "status": str(raw.get("status") or "idle"),
                "updated_at": str(raw.get("updated_at") or ""),
            }
        )
        return base

    @classmethod
    def _normalize_project(cls, project: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(project)
        ai_selection = normalized.get("ai_selection")
        normalized["ai_selection"] = ai_selection if isinstance(ai_selection, dict) else None

        events = normalized.get("events")
        trace = normalized.get("trace")
        if isinstance(events, list):
            event_list = [item for item in events if isinstance(item, dict)]
        elif isinstance(trace, list):
            event_list = [item for item in trace if isinstance(item, dict)]
        else:
            event_list = []
        normalized["events"] = event_list
        normalized["trace"] = event_list

        progress = normalized.get("progress")
        if not isinstance(progress, dict):
            progress = cls._default_progress()
        else:
            progress = {
                "current": int(progress.get("current") or 0),
                "total": int(progress.get("total") or 0),
                "currentPath": str(progress.get("currentPath") or ""),
                "provider": str(progress.get("provider") or ""),
                "tokenUsage": normalize_token_usage_snapshot(progress.get("tokenUsage")),
                "updatedAt": str(progress.get("updatedAt") or dt.datetime.now().isoformat(timespec="seconds")),
            }
        normalized["progress"] = progress
        normalized["token_usage"] = normalize_token_usage_report(normalized.get("token_usage"))
        normalized["generation_snapshot"] = cls._normalize_generation_snapshot(normalized.get("generation_snapshot"))
        normalized["generation_phase"] = cls._normalize_generation_phase(normalized.get("generation_phase"))
        normalized["construction_phase"] = cls._normalize_construction_phase(normalized.get("construction_phase"))

        incidents_raw = normalized.get("incidents")
        if isinstance(incidents_raw, list):
            incidents = [item for item in incidents_raw if isinstance(item, dict)]
        else:
            incidents = []
        normalized["incidents"] = incidents
        warnings_count = normalized.get("warnings_count")
        if warnings_count is None:
            warnings_count = sum(1 for item in incidents if str(item.get("severity") or "").lower() == "warning")
        normalized["warnings_count"] = max(0, int(warnings_count or 0))

        resume_raw = normalized.get("resume")
        normalized["resume"] = cls._normalize_resume(
            resume_raw,
            format_version=str(normalized.get("format_version") or ""),
        )
        normalized["wizard_state"] = cls._normalize_wizard_state(normalized.get("wizard_state"))
        return normalized

    def list_projects(self) -> List[Dict[str, Any]]:
        normalized = [self._normalize_project(item) for item in self.store.read_list()]

        def _dt_key(project: Dict[str, Any]) -> dt.datetime:
            raw = (
                str(project.get("updated_at") or "").strip()
                or str(project.get("created_at") or "").strip()
                or "1970-01-01T00:00:00"
            )
            try:
                return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return dt.datetime.min

        status_priority = {
            "generating": 6,
            "rendering": 5,
            "ai_received": 5,
            "draft": 4,
            "render_failed": 3,
            "failed": 3,
            "blocked": 3,
            "cancel_requested": 3,
            "completed_with_incidents": 2,
            "completed": 2,
            "simulated": 2,
        }
        normalized.sort(
            key=lambda item: (
                _dt_key(item),
                status_priority.get(str(item.get("status") or "").lower().strip(), 0),
            ),
            reverse=True,
        )
        return normalized

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        for p in self.store.read_list():
            if p.get("id") == project_id:
                return self._normalize_project(p)
        return None

    def _mutate_project(
        self,
        project_id: str,
        mutator: Callable[[Dict[str, Any]], None],
    ) -> Optional[Dict[str, Any]]:
        items = self.store.read_list()
        for i, p in enumerate(items):
            if p.get("id") != project_id:
                continue
            p = self._normalize_project(p)
            mutator(p)
            p["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
            items[i] = p
            self.store.write_list(items)
            return p
        return None

    @staticmethod
    def _ensure_trace_list(project: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = project.get("events")
        if isinstance(events, list):
            return [item for item in events if isinstance(item, dict)]
        trace = project.get("trace")
        if isinstance(trace, list):
            return [item for item in trace if isinstance(item, dict)]
        return []

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
            "pdf_file": None,
            "error": None,
            "ai_result": None,
            "run_id": None,
            "artifacts": [],
            "events": [],
            "trace": [],
            "progress": self._default_progress(),
            "token_usage": empty_token_usage_report(),
            "generation_snapshot": self._empty_generation_snapshot(),
            "generation_phase": self._empty_generation_phase(),
            "construction_phase": self._empty_construction_phase(),
            "cancel_requested": False,
            "ai_selection": payload.get("ai_selection") if isinstance(payload.get("ai_selection"), dict) else None,
            "incidents": [],
            "warnings_count": 0,
            "resume": {
                **self._empty_resume(format_version=str(payload.get("format_version") or "")),
                "updated_at": now,
            },
            "wizard_state": self._merge_wizard_state(
                {
                    **self._empty_wizard_state(),
                    "updated_at": now,
                },
                payload.get("wizard_state"),
            ),
        }
        items.insert(0, project)
        self.store.write_list(items)
        return self._normalize_project(project)

    def update_project(self, project_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
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
            if "cancel_requested" in payload and payload.get("cancel_requested") is not None:
                p["cancel_requested"] = bool(payload.get("cancel_requested"))
            if "run_id" in payload and payload.get("run_id") is not None:
                p["run_id"] = payload.get("run_id")
            if "output_file" in payload:
                p["output_file"] = payload.get("output_file")
            if "pdf_file" in payload:
                p["pdf_file"] = payload.get("pdf_file")
            if "error" in payload:
                p["error"] = payload.get("error")
            if "ai_result" in payload:
                ai_result = payload.get("ai_result")
                p["ai_result"] = ai_result if isinstance(ai_result, dict) else None
            if "artifacts" in payload:
                artifacts = payload.get("artifacts")
                p["artifacts"] = (
                    [item for item in artifacts if isinstance(item, dict)] if isinstance(artifacts, list) else []
                )
            if "ai_selection" in payload:
                selection = payload.get("ai_selection")
                p["ai_selection"] = selection if isinstance(selection, dict) else None
            if "token_usage" in payload:
                p["token_usage"] = normalize_token_usage_report(payload.get("token_usage"))
            if "generation_snapshot" in payload:
                p["generation_snapshot"] = self._normalize_generation_snapshot(payload.get("generation_snapshot"))
            if "generation_phase" in payload:
                p["generation_phase"] = self._normalize_generation_phase(payload.get("generation_phase"))
            if "construction_phase" in payload:
                p["construction_phase"] = self._normalize_construction_phase(payload.get("construction_phase"))
            if "incidents" in payload:
                incidents = payload.get("incidents")
                if isinstance(incidents, list):
                    p["incidents"] = [item for item in incidents if isinstance(item, dict)]
                else:
                    p["incidents"] = []
            if "warnings_count" in payload:
                try:
                    p["warnings_count"] = max(0, int(payload.get("warnings_count") or 0))
                except Exception:
                    p["warnings_count"] = 0
            if "resume" in payload:
                resume_payload = payload.get("resume")
                if isinstance(resume_payload, dict):
                    current = self._normalize_resume(
                        p.get("resume"),
                        format_version=str(p.get("format_version") or ""),
                    )
                    merged = dict(current)
                    merged.update(resume_payload)
                    p["resume"] = self._normalize_resume(
                        merged,
                        format_version=str(p.get("format_version") or ""),
                    )
                else:
                    p["resume"] = {
                        **self._empty_resume(format_version=str(p.get("format_version") or "")),
                        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
                    }
            if "wizard_state" in payload:
                wizard_payload = payload.get("wizard_state")
                if isinstance(wizard_payload, dict):
                    p["wizard_state"] = self._merge_wizard_state(p.get("wizard_state"), wizard_payload)
                else:
                    p["wizard_state"] = {
                        **self._empty_wizard_state(),
                        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
                    }
            if "progress" in payload and isinstance(payload.get("progress"), dict):
                progress = self._default_progress(provider=str(payload["progress"].get("provider") or ""))
                progress.update(
                    {
                        "current": int(payload["progress"].get("current") or 0),
                        "total": int(payload["progress"].get("total") or 0),
                        "currentPath": str(payload["progress"].get("currentPath") or ""),
                        "provider": str(payload["progress"].get("provider") or ""),
                        "tokenUsage": normalize_token_usage_snapshot(payload["progress"].get("tokenUsage")),
                        "updatedAt": str(
                            payload["progress"].get("updatedAt") or dt.datetime.now().isoformat(timespec="seconds")
                        ),
                    }
                )
                p["progress"] = progress

            if "variables" in payload or "values" in payload:
                values = payload.get("variables")
                if values is None:
                    values = payload.get("values", {})
                p["variables"] = values or {}
                p["values"] = values or {}

        return self._mutate_project(project_id, _mutate)

    def clear_trace(self, project_id: str) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            p["events"] = []
            p["trace"] = []

        return self._mutate_project(project_id, _mutate)

    def clear_incidents(self, project_id: str) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            p["incidents"] = []
            p["warnings_count"] = 0

        return self._mutate_project(project_id, _mutate)

    def clear_resume(self, project_id: str) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            p["resume"] = {
                **self._empty_resume(format_version=str(p.get("format_version") or "")),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }

        return self._mutate_project(project_id, _mutate)

    def clear_generation_snapshot(self, project_id: str) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            p["generation_snapshot"] = {
                **self._empty_generation_snapshot(),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }

        return self._mutate_project(project_id, _mutate)

    def mark_resume_checkpoint(
        self,
        project_id: str,
        *,
        saved_sections_count: int,
        last_failed_section_path: str,
        reason: str,
        base_run_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            current_resume = self._normalize_resume(
                p.get("resume"),
                format_version=str(p.get("format_version") or ""),
            )
            current_retry_count = int(current_resume.get("retry_count") or 0)
            p["resume"] = {
                **current_resume,
                "eligible": saved_sections_count > 0,
                "saved_sections_count": max(0, int(saved_sections_count)),
                "resume_from_index": max(0, int(saved_sections_count)),
                "last_failed_section_path": str(last_failed_section_path or ""),
                "base_run_id": str(base_run_id or current_resume.get("base_run_id") or ""),
                "retry_count": current_retry_count + 1,
                "reason": str(reason or ""),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }

        return self._mutate_project(project_id, _mutate)

    def append_incident(self, project_id: str, incident: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            incidents = p.get("incidents")
            if not isinstance(incidents, list):
                incidents = []
            item = dict(incident)
            incidents.append(item)
            p["incidents"] = incidents[-200:]
            severity = str(item.get("severity") or "").lower()
            current_warnings = int(p.get("warnings_count") or 0)
            if severity == "warning":
                current_warnings += 1
            p["warnings_count"] = max(0, current_warnings)

        return self._mutate_project(project_id, _mutate)

    def list_trace(self, project_id: str) -> List[Dict[str, Any]]:
        project = self.get_project(project_id)
        if not project:
            return []
        return self._ensure_trace_list(project)

    def append_event(self, project_id: str, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            trace = self._ensure_trace_list(p)
            item = dict(event)
            trace.append(item)
            if len(trace) > _TRACE_MAX_EVENTS:
                trace = trace[-_TRACE_MAX_EVENTS:]
            p["events"] = trace
            p["trace"] = trace

        return self._mutate_project(project_id, _mutate)

    def update_progress(
        self,
        project_id: str,
        *,
        current: Optional[int] = None,
        total: Optional[int] = None,
        current_path: Optional[str] = None,
        provider: Optional[str] = None,
        token_usage_snapshot_data: Optional[Dict[str, Any]] = None,
        token_usage_report_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            progress = p.get("progress")
            if not isinstance(progress, dict):
                progress = self._default_progress(provider=str(provider or ""))

            if current is not None:
                progress["current"] = max(0, int(current))
            if total is not None:
                progress["total"] = max(0, int(total))
            if current_path is not None:
                progress["currentPath"] = str(current_path)
            if provider is not None:
                progress["provider"] = str(provider)
            if token_usage_snapshot_data is not None:
                progress["tokenUsage"] = normalize_token_usage_snapshot(token_usage_snapshot_data)
            if token_usage_report_data is not None:
                p["token_usage"] = normalize_token_usage_report(token_usage_report_data)
            progress["updatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
            p["progress"] = progress

        return self._mutate_project(project_id, _mutate)

    def request_cancel(self, project_id: str) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            p["cancel_requested"] = True
            current_status = str(p.get("status") or "")
            if current_status in {"generating", "processing", "sending"}:
                p["status"] = "cancel_requested"

        return self._mutate_project(project_id, _mutate)

    def is_cancel_requested(self, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False
        return bool(project.get("cancel_requested"))

    def mark_completed(
        self,
        project_id: str,
        output_file: str,
        *,
        pdf_file: Optional[str] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        with_incidents: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            warnings_count = int(p.get("warnings_count") or 0)
            has_incidents = warnings_count > 0
            if with_incidents is not None:
                has_incidents = bool(with_incidents)
            p["status"] = "completed_with_incidents" if has_incidents else "completed"
            p["output_file"] = output_file
            if pdf_file is not None:
                p["pdf_file"] = pdf_file
            if artifacts is not None:
                p["artifacts"] = artifacts
            p["cancel_requested"] = False
            p["error"] = None
            p["resume"] = {
                **self._empty_resume(format_version=str(p.get("format_version") or "")),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
            p["generation_snapshot"] = {
                **self._empty_generation_snapshot(),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
            progress = p.get("progress")
            if isinstance(progress, dict):
                total = int(progress.get("total") or 0)
                if total > 0:
                    progress["current"] = total
                progress["updatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
                p["progress"] = progress

        return self._mutate_project(project_id, _mutate)

    def mark_failed(
        self,
        project_id: str,
        error: str,
        *,
        keep_ai_result: bool = False,
    ) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            p["status"] = "failed"
            p["error"] = error
            if not keep_ai_result:
                # Ensure stale successful payloads are not shown after failures.
                p["ai_result"] = None
                p["run_id"] = None
                p["resume"] = {
                    **self._empty_resume(format_version=str(p.get("format_version") or "")),
                    "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
                }
                p["generation_snapshot"] = {
                    **self._empty_generation_snapshot(),
                    "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
                }
            p["artifacts"] = []
            p["output_file"] = None
            p["pdf_file"] = None
            p["cancel_requested"] = False
            progress = p.get("progress")
            if isinstance(progress, dict):
                progress["updatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
                p["progress"] = progress

        return self._mutate_project(project_id, _mutate)

    def mark_blocked(
        self,
        project_id: str,
        error: str,
        *,
        keep_ai_result: bool = True,
    ) -> Optional[Dict[str, Any]]:
        def _mutate(p: Dict[str, Any]) -> None:
            p["status"] = "blocked"
            p["error"] = error
            p["cancel_requested"] = False
            if not keep_ai_result:
                p["ai_result"] = None
                p["run_id"] = None
                p["artifacts"] = []
                p["generation_snapshot"] = {
                    **self._empty_generation_snapshot(),
                    "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
                }
            p["output_file"] = None
            p["pdf_file"] = None
            progress = p.get("progress")
            if isinstance(progress, dict):
                progress["updatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
                p["progress"] = progress

        return self._mutate_project(project_id, _mutate)

    def mark_ai_received(
        self,
        project_id: str,
        ai_result: Dict[str, Any],
        run_id: Optional[str] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Persist AI payload received from n8n callback."""

        def _mutate(p: Dict[str, Any]) -> None:
            p["status"] = "ai_received"
            p["ai_result"] = ai_result
            p["token_usage"] = normalize_token_usage_report(ai_result.get("tokenUsage"))
            p["run_id"] = run_id
            p["artifacts"] = artifacts or []
            p["error"] = None
            p["cancel_requested"] = False
            p["resume"] = {
                **self._empty_resume(format_version=str(p.get("format_version") or "")),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
            p["generation_snapshot"] = {
                **self._empty_generation_snapshot(),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
            progress = p.get("progress")
            if isinstance(progress, dict):
                total = int(progress.get("total") or 0)
                if total > 0:
                    progress["current"] = total
                progress["updatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
                p["progress"] = progress

        return self._mutate_project(project_id, _mutate)

    def mark_render_failed(
        self,
        project_id: str,
        error: str,
    ) -> Optional[Dict[str, Any]]:
        """Persist a render-stage failure without discarding validated AI output."""

        def _mutate(p: Dict[str, Any]) -> None:
            p["status"] = "render_failed"
            p["error"] = error
            p["artifacts"] = []
            p["output_file"] = None
            p["pdf_file"] = None
            p["cancel_requested"] = False
            p["resume"] = {
                **self._empty_resume(format_version=str(p.get("format_version") or "")),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
            progress = p.get("progress")
            if isinstance(progress, dict):
                total = int(progress.get("total") or 0)
                if total > 0:
                    progress["current"] = total
                progress["updatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
                p["progress"] = progress

        return self._mutate_project(project_id, _mutate)

    def mark_simulated(
        self,
        project_id: str,
        ai_result: Dict[str, Any],
        run_id: str,
        artifacts: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Persist latest simulation run output for n8n guide/demo downloads."""

        def _mutate(p: Dict[str, Any]) -> None:
            p["status"] = "simulated"
            p["ai_result"] = ai_result
            p["run_id"] = run_id
            p["artifacts"] = artifacts
            p["error"] = None
            p["cancel_requested"] = False
            p["resume"] = {
                **self._empty_resume(format_version=str(p.get("format_version") or "")),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
            p["generation_snapshot"] = {
                **self._empty_generation_snapshot(),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
            progress = p.get("progress")
            if isinstance(progress, dict):
                progress["updatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
                p["progress"] = progress

        return self._mutate_project(project_id, _mutate)

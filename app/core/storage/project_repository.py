from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from app.core.services.ai.unac_quality_profile import extract_semantic_unit_content, section_key_from_path
from app.core.storage.json_store import JsonStore


class ProjectRepository(Protocol):
    def list(self, *, include_events: bool = False) -> List[Dict[str, Any]]: ...

    def get(self, project_id: str, *, hydrate: bool = True) -> Optional[Dict[str, Any]]: ...

    def insert(self, project: Dict[str, Any]) -> None: ...

    def upsert(self, project: Dict[str, Any], *, sync_derived: bool = True) -> None: ...

    def delete(self, project_id: str) -> bool: ...

    def append_event(self, project_id: str, event: Dict[str, Any], *, limit: int = 200) -> bool: ...

    def replace_events(self, project_id: str, events: List[Dict[str, Any]], *, limit: int = 200) -> bool: ...


class JsonProjectRepository:
    """Compatibility backend used by tests and as an explicit rollback option."""

    def __init__(self, path: str):
        self.store = JsonStore(path)

    def list(self, *, include_events: bool = False) -> List[Dict[str, Any]]:
        del include_events
        return self.store.read_list()

    def get(self, project_id: str, *, hydrate: bool = True) -> Optional[Dict[str, Any]]:
        del hydrate
        return next((item for item in self.store.read_list() if item.get("id") == project_id), None)

    def insert(self, project: Dict[str, Any]) -> None:
        items = self.store.read_list()
        items.insert(0, project)
        self.store.write_list(items)

    def upsert(self, project: Dict[str, Any], *, sync_derived: bool = True) -> None:
        del sync_derived
        items = self.store.read_list()
        for index, item in enumerate(items):
            if item.get("id") == project.get("id"):
                items[index] = project
                self.store.write_list(items)
                return
        items.insert(0, project)
        self.store.write_list(items)

    def delete(self, project_id: str) -> bool:
        items = self.store.read_list()
        remaining = [item for item in items if item.get("id") != project_id]
        if len(remaining) == len(items):
            return False
        self.store.write_list(remaining)
        return True

    def append_event(self, project_id: str, event: Dict[str, Any], *, limit: int = 200) -> bool:
        project = self.get(project_id)
        if project is None:
            return False
        events = project.get("events") if isinstance(project.get("events"), list) else project.get("trace")
        events = [item for item in events or [] if isinstance(item, dict)]
        events.append(dict(event))
        project["events"] = events[-limit:]
        project["trace"] = events[-limit:]
        self.upsert(project)
        return True

    def replace_events(self, project_id: str, events: List[Dict[str, Any]], *, limit: int = 200) -> bool:
        project = self.get(project_id)
        if project is None:
            return False
        clean = [dict(item) for item in events if isinstance(item, dict)][-limit:]
        project["events"] = clean
        project["trace"] = clean
        self.upsert(project)
        return True


class SQLiteProjectRepository:
    """Row-oriented project persistence; large diagnostics are queried on demand."""

    SCHEMA_VERSION = 2

    def __init__(self, path: str):
        candidate = Path(path)
        if not candidate.is_absolute():
            repo_root = Path(__file__).resolve().parents[3]
            candidate = (repo_root / candidate).resolve()
        self.path = candidate
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    format_id TEXT,
                    format_version TEXT,
                    status TEXT NOT NULL,
                    run_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
                CREATE TABLE IF NOT EXISTS project_sections (
                    project_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    order_index INTEGER NOT NULL,
                    content_json TEXT NOT NULL,
                    generation_status TEXT NOT NULL DEFAULT 'generated',
                    validation_status TEXT NOT NULL DEFAULT 'pending',
                    quality_audit_json TEXT,
                    content_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, section_id),
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS generation_runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    profile_version TEXT,
                    resume_mode TEXT,
                    input_fingerprint TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    started_at TEXT,
                    updated_at TEXT,
                    finished_at TEXT,
                    metrics_json TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS generation_checkpoints (
                    project_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    failed_section_id TEXT,
                    failed_stage TEXT,
                    completed_sections_count INTEGER NOT NULL DEFAULT 0,
                    profile_version TEXT,
                    input_fingerprint TEXT,
                    checkpoint_status TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS generation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT,
                    created_at TEXT NOT NULL,
                    step TEXT,
                    status TEXT,
                    event_json TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_events_project_id ON generation_events(project_id, id DESC);
                CREATE TABLE IF NOT EXISTS ai_calls (
                    call_key TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    run_id TEXT,
                    section_id TEXT,
                    phase TEXT,
                    provider TEXT,
                    model TEXT,
                    prompt_text TEXT,
                    response_text TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    success INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS construction_tasks (
                    project_id TEXT NOT NULL,
                    task_key TEXT NOT NULL,
                    status TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, task_key),
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    project_id TEXT NOT NULL,
                    artifact_key TEXT NOT NULL,
                    artifact_type TEXT,
                    path TEXT,
                    sha256 TEXT,
                    size_bytes INTEGER,
                    status TEXT,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(project_id, artifact_key),
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                """
            )
            project_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "detail_json" not in project_columns:
                connection.execute(
                    "ALTER TABLE projects ADD COLUMN detail_json TEXT NOT NULL DEFAULT '{}'"
                )
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(self.SCHEMA_VERSION),),
            )

    @staticmethod
    def backup_legacy_json(path: str) -> Optional[Path]:
        source = Path(path)
        if not source.is_absolute():
            repo_root = Path(__file__).resolve().parents[3]
            source = (repo_root / source).resolve()
        if not source.exists() or source.stat().st_size == 0:
            return None
        raw = source.read_bytes()
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, list):
            raise ValueError("projects.json no contiene una lista valida")
        backup_dir = source.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(raw).hexdigest()
        existing = sorted(backup_dir.glob("projects-*.json"))
        for candidate in reversed(existing):
            checksum = candidate.with_suffix(".sha256")
            if checksum.exists() and checksum.read_text(encoding="utf-8").split(maxsplit=1)[0] == digest:
                # Parse the backup too: a checksum match alone is not enough
                # acceptance evidence if the file was truncated in transit.
                backup_value = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(backup_value, list):
                    return candidate
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = backup_dir / f"projects-{stamp}.json"
        shutil.copy2(source, target)
        copied_value = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(copied_value, list):
            target.unlink(missing_ok=True)
            raise ValueError("el respaldo de projects.json no se puede analizar")
        target.with_suffix(".sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
        return target

    @staticmethod
    def _split_project_payload(project: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        payload = copy.deepcopy(project)
        payload.pop("events", None)
        payload.pop("trace", None)
        detail: Dict[str, Any] = {}
        for key in ("prompt_template", "system_instruction", "prompt_snapshot"):
            if key in payload:
                detail[key] = payload.pop(key)
        ai_result = payload.get("ai_result")
        if isinstance(ai_result, dict) and isinstance(ai_result.get("sections"), list):
            compact_result = dict(ai_result)
            compact_result["sections"] = []
            compact_result["sectionsStoredSeparately"] = True
            payload["ai_result"] = compact_result
        phase = payload.get("generation_phase")
        if isinstance(phase, dict) and isinstance(phase.get("sections"), list):
            compact_phase = dict(phase)
            if "base_prompt" in compact_phase:
                detail["generation_phase_base_prompt"] = compact_phase.pop("base_prompt")
            compact_sections: List[Dict[str, Any]] = []
            for item in phase["sections"]:
                if not isinstance(item, dict):
                    continue
                summary = dict(item)
                summary.pop("prompt_sent", None)
                summary.pop("ai_output", None)
                summary.pop("attempts", None)
                compact_sections.append(summary)
            compact_phase["sections"] = compact_sections
            compact_phase["detailsStoredSeparately"] = True
            payload["generation_phase"] = compact_phase
        return payload, detail

    @staticmethod
    def _loads(raw: str) -> Dict[str, Any]:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}

    def _events(self, connection: sqlite3.Connection, project_id: str) -> List[Dict[str, Any]]:
        rows = connection.execute(
            "SELECT event_json FROM generation_events WHERE project_id=? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        return [self._loads(str(row["event_json"])) for row in rows]

    def list(self, *, include_events: bool = False) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT id, payload_json FROM projects ORDER BY updated_at DESC").fetchall()
            projects = [self._loads(str(row["payload_json"])) for row in rows]
            if include_events:
                for project in projects:
                    events = self._events(connection, str(project.get("id") or ""))
                    project["events"] = events
                    project["trace"] = events
            return projects

    def get(self, project_id: str, *, hydrate: bool = True) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json,detail_json FROM projects WHERE id=?",
                (project_id,),
            ).fetchone()
            if row is None:
                return None
            project = self._loads(str(row["payload_json"]))
            if not hydrate:
                return project
            detail = self._loads(str(row["detail_json"]))
            project.update({key: value for key, value in detail.items() if key != "generation_phase_base_prompt"})
            if "generation_phase_base_prompt" in detail:
                phase = project.get("generation_phase") if isinstance(project.get("generation_phase"), dict) else {}
                project["generation_phase"] = {
                    **phase,
                    "base_prompt": str(detail.get("generation_phase_base_prompt") or ""),
                }
            events = self._events(connection, project_id)
            project["events"] = events
            project["trace"] = events
            self._hydrate_derived(connection, project)
            return project

    def _hydrate_derived(self, connection: sqlite3.Connection, project: Dict[str, Any]) -> None:
        project_id = str(project.get("id") or "")
        ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {}
        if ai_result.get("sectionsStoredSeparately"):
            rows = connection.execute(
                "SELECT content_json FROM project_sections WHERE project_id=? AND generation_status!='semantic_unit' ORDER BY order_index ASC",
                (project_id,),
            ).fetchall()
            restored = dict(ai_result)
            restored["sections"] = [self._loads(str(row["content_json"])) for row in rows]
            restored.pop("sectionsStoredSeparately", None)
            project["ai_result"] = restored

        phase = project.get("generation_phase") if isinstance(project.get("generation_phase"), dict) else {}
        if phase.get("detailsStoredSeparately"):
            run_id = str(project.get("run_id") or "")
            params: tuple[Any, ...]
            sql = "SELECT section_id,payload_json FROM ai_calls WHERE project_id=?"
            params = (project_id,)
            if run_id:
                sql += " AND run_id=?"
                params = (project_id, run_id)
            rows = connection.execute(sql + " ORDER BY created_at ASC, call_key ASC", params).fetchall()
            details = {str(row["section_id"]): self._loads(str(row["payload_json"])) for row in rows}
            restored_phase = dict(phase)
            restored_sections: List[Dict[str, Any]] = []
            for summary in phase.get("sections") or []:
                if not isinstance(summary, dict):
                    continue
                section_id = str(summary.get("section_id") or summary.get("section_path") or "")
                restored_sections.append({**summary, **details.get(section_id, {})})
            restored_phase["sections"] = restored_sections
            restored_phase.pop("detailsStoredSeparately", None)
            project["generation_phase"] = restored_phase
            phase = restored_phase
        run_id = str(project.get("run_id") or "")
        if run_id:
            metrics_row = connection.execute(
                "SELECT metrics_json FROM generation_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if metrics_row is not None:
                stored_metrics = self._loads(str(metrics_row["metrics_json"]))
                phase = project.get("generation_phase") if isinstance(project.get("generation_phase"), dict) else {}
                public_metrics = (
                    stored_metrics.get("generationMetrics")
                    if isinstance(stored_metrics.get("generationMetrics"), dict)
                    else {}
                )
                public_metrics = {
                    **public_metrics,
                    "persistence_ms": int(stored_metrics.get("persistence_ms") or public_metrics.get("persistence_ms") or 0),
                    "bytes_written": int(stored_metrics.get("bytes_written") or 0),
                    "write_operations": int(stored_metrics.get("write_operations") or 0),
                }
                if phase:
                    project["generation_phase"] = {**phase, "metrics": public_metrics}

    def insert(self, project: Dict[str, Any]) -> None:
        self.upsert(project)

    def upsert(self, project: Dict[str, Any], *, sync_derived: bool = True) -> None:
        project_id = str(project.get("id") or "")
        if not project_id:
            raise ValueError("project.id es obligatorio")
        payload, detail = self._split_project_payload(project)
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        detail_json = json.dumps(detail, ensure_ascii=False, separators=(",", ":"), default=str)
        now = str(project.get("updated_at") or dt.datetime.now().isoformat(timespec="seconds"))
        started = time.perf_counter()
        with self._lock, self._connect() as connection:
            if sync_derived:
                connection.execute(
                    """
                    INSERT INTO projects(id,title,format_id,format_version,status,run_id,created_at,updated_at,payload_json,detail_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title, format_id=excluded.format_id, format_version=excluded.format_version,
                        status=excluded.status, run_id=excluded.run_id, updated_at=excluded.updated_at,
                        payload_json=excluded.payload_json,detail_json=excluded.detail_json, version=projects.version+1
                    """,
                    (
                        project_id,
                        str(project.get("title") or "Proyecto sin titulo"),
                        str(project.get("format_id") or ""),
                        str(project.get("format_version") or ""),
                        str(project.get("status") or "draft"),
                        str(project.get("run_id") or ""),
                        str(project.get("created_at") or now),
                        now,
                        payload_json,
                        detail_json,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE projects SET title=?,format_id=?,format_version=?,status=?,run_id=?,updated_at=?,
                        payload_json=?,version=version+1 WHERE id=?
                    """,
                    (
                        str(project.get("title") or "Proyecto sin titulo"),
                        str(project.get("format_id") or ""),
                        str(project.get("format_version") or ""),
                        str(project.get("status") or "draft"),
                        str(project.get("run_id") or ""),
                        now,
                        payload_json,
                        project_id,
                    ),
                )
            if sync_derived:
                self._sync_derived(connection, project)
        elapsed_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
        self._record_persistence_metric(
            project_id,
            str(project.get("run_id") or ""),
            elapsed_ms=elapsed_ms,
            bytes_written=len(payload_json.encode("utf-8")) + len(detail_json.encode("utf-8")),
        )

    def _record_persistence_metric(
        self,
        project_id: str,
        run_id: str,
        *,
        elapsed_ms: int,
        bytes_written: int,
    ) -> None:
        if not run_id:
            return
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT metrics_json FROM generation_runs WHERE run_id=? AND project_id=?",
                (run_id, project_id),
            ).fetchone()
            if row is None:
                return
            metrics = self._loads(str(row["metrics_json"]))
            metrics["persistence_ms"] = int(metrics.get("persistence_ms") or 0) + max(0, int(elapsed_ms))
            metrics["bytes_written"] = int(metrics.get("bytes_written") or 0) + max(0, int(bytes_written))
            metrics["write_operations"] = int(metrics.get("write_operations") or 0) + 1
            connection.execute(
                "UPDATE generation_runs SET metrics_json=? WHERE run_id=?",
                (json.dumps(metrics, ensure_ascii=False, separators=(",", ":"), default=str), run_id),
            )

    def _sync_derived(self, connection: sqlite3.Connection, project: Dict[str, Any]) -> None:
        project_id = str(project.get("id") or "")
        now = str(project.get("updated_at") or dt.datetime.now().isoformat(timespec="seconds"))
        ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {}
        sections = ai_result.get("sections") if isinstance(ai_result.get("sections"), list) else []
        connection.execute(
            "DELETE FROM project_sections WHERE project_id=? AND generation_status='semantic_unit'",
            (project_id,),
        )
        for order_index, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("sectionId") or section.get("section_id") or f"section-{order_index}")
            encoded = json.dumps(section, ensure_ascii=False, separators=(",", ":"), default=str)
            audit = section.get("qualityAudit") if isinstance(section.get("qualityAudit"), dict) else None
            failed_quality_keys = {
                str(item)
                for item in ((project.get("resume") or {}).get("failed_quality_keys") or [])
                if str(item).strip()
            }
            section_path = str(section.get("path") or section.get("sectionPath") or "")
            validation_status = str(section.get("validationStatus") or "")
            if audit and audit.get("status") == "ok":
                validation_status = "validated"
            elif section_id in failed_quality_keys or section_path in failed_quality_keys:
                validation_status = "pending"
            elif not validation_status:
                validation_status = "generated"
            connection.execute(
                """
                INSERT INTO project_sections(project_id,section_id,path,order_index,content_json,generation_status,
                    validation_status,quality_audit_json,content_sha256,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,section_id) DO UPDATE SET path=excluded.path,order_index=excluded.order_index,
                    content_json=excluded.content_json,generation_status=excluded.generation_status,
                    validation_status=excluded.validation_status,quality_audit_json=excluded.quality_audit_json,
                    content_sha256=excluded.content_sha256,updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    section_id,
                    section_path,
                    order_index,
                    encoded,
                    str(section.get("status") or "generated"),
                    validation_status,
                    json.dumps(audit, ensure_ascii=False, default=str) if audit else None,
                    hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                    now,
                ),
            )
            owner_key = section_key_from_path(section_path)
            unit_audits = audit.get("units") if isinstance(audit, dict) and isinstance(audit.get("units"), list) else []
            for unit_offset, unit_audit in enumerate(unit_audits, start=1):
                if not isinstance(unit_audit, dict):
                    continue
                unit_key = str(unit_audit.get("key") or "").strip()
                if not unit_key or unit_key == owner_key:
                    continue
                unit_heading = str(unit_audit.get("heading") or unit_key)
                unit_content = extract_semantic_unit_content(section.get("content"), unit_key)
                unit_payload = {
                    "sectionId": f"{section_id}:{unit_key}",
                    "path": f"{section_path}/{unit_heading}",
                    "content": unit_content,
                    "qualityAudit": unit_audit,
                }
                unit_encoded = json.dumps(
                    unit_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                )
                connection.execute(
                    """
                    INSERT INTO project_sections(project_id,section_id,path,order_index,content_json,generation_status,
                        validation_status,quality_audit_json,content_sha256,updated_at)
                    VALUES(?,?,?,?,?,'semantic_unit',?,?,?,?)
                    ON CONFLICT(project_id,section_id) DO UPDATE SET path=excluded.path,order_index=excluded.order_index,
                        content_json=excluded.content_json,generation_status='semantic_unit',
                        validation_status=excluded.validation_status,quality_audit_json=excluded.quality_audit_json,
                        content_sha256=excluded.content_sha256,updated_at=excluded.updated_at
                    """,
                    (
                        project_id,
                        f"{section_id}:{unit_key}",
                        f"{section_path}/{unit_heading}",
                        order_index * 100 + unit_offset,
                        unit_encoded,
                        "validated" if unit_audit.get("status") == "ok" else "pending",
                        json.dumps(unit_audit, ensure_ascii=False, separators=(",", ":"), default=str),
                        hashlib.sha256(unit_encoded.encode("utf-8")).hexdigest(),
                        now,
                    ),
                )
        phase = project.get("generation_phase") if isinstance(project.get("generation_phase"), dict) else {}
        phase_sections = phase.get("sections") if isinstance(phase.get("sections"), list) else []
        run_id = str(project.get("run_id") or "")
        for order_index, section in enumerate(phase_sections):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("section_id") or section.get("section_path") or f"section-{order_index}")
            call_key = f"{project_id}:{run_id or 'no-run'}:{section_id}"
            connection.execute(
                """
                INSERT INTO ai_calls(call_key,project_id,run_id,section_id,phase,provider,model,prompt_text,
                    response_text,input_tokens,output_tokens,duration_ms,success,created_at,payload_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(call_key) DO UPDATE SET provider=excluded.provider,model=excluded.model,
                    prompt_text=excluded.prompt_text,response_text=excluded.response_text,input_tokens=excluded.input_tokens,
                    output_tokens=excluded.output_tokens,duration_ms=excluded.duration_ms,success=excluded.success,
                    created_at=excluded.created_at,payload_json=excluded.payload_json
                """,
                (
                    call_key,
                    project_id,
                    run_id,
                    section_id,
                    str(section.get("phase") or "generation"),
                    str(section.get("provider") or ""),
                    str(section.get("model") or ""),
                    str(section.get("prompt_sent") or ""),
                    str(section.get("ai_output") or ""),
                    int(section.get("input_tokens") or 0),
                    int(section.get("output_tokens") or 0),
                    int(section.get("duration_ms") or 0),
                    0 if str(section.get("status") or "").lower() in {"error", "failed"} else 1,
                    str(section.get("started_at") or section.get("completed_at") or now),
                    json.dumps(section, ensure_ascii=False, separators=(",", ":"), default=str),
                ),
            )
        resume = project.get("resume") if isinstance(project.get("resume"), dict) else {}
        if resume:
            connection.execute(
                """
                INSERT INTO generation_checkpoints(project_id,run_id,failed_section_id,failed_stage,
                    completed_sections_count,profile_version,input_fingerprint,checkpoint_status,payload_json,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id) DO UPDATE SET run_id=excluded.run_id,failed_section_id=excluded.failed_section_id,
                    failed_stage=excluded.failed_stage,completed_sections_count=excluded.completed_sections_count,
                    profile_version=excluded.profile_version,input_fingerprint=excluded.input_fingerprint,
                    checkpoint_status=excluded.checkpoint_status,payload_json=excluded.payload_json,updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    str(project.get("run_id") or resume.get("base_run_id") or ""),
                    str(resume.get("failed_section_id") or ""),
                    str(resume.get("failed_stage") or ""),
                    int(resume.get("completed_sections_count") or resume.get("saved_sections_count") or 0),
                    str(resume.get("profile_version") or ""),
                    str(resume.get("input_fingerprint") or ""),
                    str(resume.get("checkpoint_status") or "idle"),
                    json.dumps(resume, ensure_ascii=False, separators=(",", ":"), default=str),
                    now,
                ),
            )
        run_id = str(project.get("run_id") or "")
        if run_id:
            selection = project.get("ai_selection") if isinstance(project.get("ai_selection"), dict) else {}
            existing_run = connection.execute(
                "SELECT metrics_json FROM generation_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            existing_metrics = self._loads(str(existing_run["metrics_json"])) if existing_run is not None else {}
            generation_phase = project.get("generation_phase") if isinstance(project.get("generation_phase"), dict) else {}
            metrics_payload = {
                **existing_metrics,
                "tokenUsage": project.get("token_usage"),
                "cost": project.get("generation_cost"),
                "generationMetrics": generation_phase.get("metrics") if isinstance(generation_phase.get("metrics"), dict) else {},
            }
            connection.execute(
                """
                INSERT INTO generation_runs(run_id,project_id,provider,model,profile_version,resume_mode,input_fingerprint,
                    status,error,started_at,updated_at,finished_at,metrics_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,error=excluded.error,
                    updated_at=excluded.updated_at,finished_at=excluded.finished_at,metrics_json=excluded.metrics_json
                """,
                (
                    run_id,
                    project_id,
                    str(selection.get("provider") or ""),
                    str(selection.get("model") or ""),
                    str(resume.get("profile_version") or ai_result.get("qualityProfile") or ""),
                    str(selection.get("resumeMode") or ""),
                    str(resume.get("input_fingerprint") or ""),
                    str(project.get("status") or "draft"),
                    str(project.get("error") or ""),
                    str((project.get("generation_phase") or {}).get("started_at") or project.get("created_at") or now),
                    now,
                    str((project.get("generation_phase") or {}).get("finished_at") or ""),
                    json.dumps(metrics_payload, ensure_ascii=False, separators=(",", ":"), default=str),
                ),
            )

        construction = project.get("construction_phase") if isinstance(project.get("construction_phase"), dict) else {}
        tasks = construction.get("tasks") if isinstance(construction.get("tasks"), list) else []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_key = str(task.get("id") or task.get("label") or "").strip()
            if not task_key:
                continue
            connection.execute(
                """
                INSERT INTO construction_tasks(project_id,task_key,status,payload_json,updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(project_id,task_key) DO UPDATE SET status=excluded.status,
                    payload_json=excluded.payload_json,updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    task_key,
                    str(task.get("status") or "pending"),
                    json.dumps(task, ensure_ascii=False, separators=(",", ":"), default=str),
                    str(task.get("updated_at") or now),
                ),
            )

        artifacts = project.get("artifacts") if isinstance(project.get("artifacts"), list) else []
        for order_index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                continue
            artifact_type = str(artifact.get("type") or artifact.get("artifact_type") or "artifact")
            artifact_key = str(artifact.get("id") or artifact.get("key") or f"{artifact_type}-{order_index}")
            connection.execute(
                """
                INSERT INTO artifacts(project_id,artifact_key,artifact_type,path,sha256,size_bytes,status,payload_json)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,artifact_key) DO UPDATE SET artifact_type=excluded.artifact_type,
                    path=excluded.path,sha256=excluded.sha256,size_bytes=excluded.size_bytes,
                    status=excluded.status,payload_json=excluded.payload_json
                """,
                (
                    project_id,
                    artifact_key,
                    artifact_type,
                    str(artifact.get("path") or artifact.get("downloadUrl") or ""),
                    str(artifact.get("sha256") or ""),
                    int(artifact.get("size") or artifact.get("size_bytes") or 0),
                    str(artifact.get("status") or "ready"),
                    json.dumps(artifact, ensure_ascii=False, separators=(",", ":"), default=str),
                ),
            )

    def delete(self, project_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM projects WHERE id=?", (project_id,))
            return cursor.rowcount > 0

    def append_event(self, project_id: str, event: Dict[str, Any], *, limit: int = 200) -> bool:
        with self._lock, self._connect() as connection:
            exists = connection.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone()
            if exists is None:
                return False
            connection.execute(
                "INSERT INTO generation_events(project_id,run_id,created_at,step,status,event_json) VALUES(?,?,?,?,?,?)",
                (
                    project_id,
                    str(event.get("runId") or event.get("run_id") or ""),
                    str(event.get("ts") or dt.datetime.now(dt.timezone.utc).isoformat()),
                    str(event.get("step") or event.get("stage") or ""),
                    str(event.get("status") or ""),
                    json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str),
                ),
            )
            connection.execute(
                """
                DELETE FROM generation_events WHERE project_id=? AND id NOT IN (
                    SELECT id FROM generation_events WHERE project_id=? ORDER BY id DESC LIMIT ?
                )
                """,
                (project_id, project_id, limit),
            )
            return True

    def replace_events(self, project_id: str, events: List[Dict[str, Any]], *, limit: int = 200) -> bool:
        with self._lock, self._connect() as connection:
            exists = connection.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone()
            if exists is None:
                return False
            connection.execute("DELETE FROM generation_events WHERE project_id=?", (project_id,))
            for event in [item for item in events if isinstance(item, dict)][-limit:]:
                connection.execute(
                    "INSERT INTO generation_events(project_id,run_id,created_at,step,status,event_json) VALUES(?,?,?,?,?,?)",
                    (
                        project_id,
                        str(event.get("runId") or event.get("run_id") or ""),
                        str(event.get("ts") or dt.datetime.now(dt.timezone.utc).isoformat()),
                        str(event.get("step") or event.get("stage") or ""),
                        str(event.get("status") or ""),
                        json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str),
                    ),
                )
            return True

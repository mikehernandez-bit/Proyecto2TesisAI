from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.services.project_service import ProjectService
from app.core.storage.project_repository import SQLiteProjectRepository


def test_legacy_json_backup_is_valid_and_has_sha256(tmp_path):
    source = tmp_path / "data" / "projects.json"
    source.parent.mkdir(parents=True)
    payload = [{"id": "legacy-1", "title": "Proyecto anterior"}]
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    source.write_bytes(raw)

    backup = SQLiteProjectRepository.backup_legacy_json(str(source))

    assert backup is not None
    assert json.loads(backup.read_text(encoding="utf-8")) == payload
    checksum = backup.with_suffix(".sha256").read_text(encoding="utf-8")
    assert checksum.startswith(hashlib.sha256(raw).hexdigest())
    assert SQLiteProjectRepository.backup_legacy_json(str(source)) == backup


def test_sqlite_stores_heavy_details_separately_and_rehydrates_detail(tmp_path):
    db_path = tmp_path / "runtime" / "gicagen.db"
    service = ProjectService(str(db_path), backend="sqlite")
    project = service.create_project(
        {
            "title": "Proyecto SQLite",
            "format_id": "unac-proyecto-cuant",
            "format_version": "UNAC_MAINTENANCE_V2",
            "prompt_template": "PLANTILLA COMPLETA DEL PROYECTO",
        }
    )
    project_id = project["id"]
    service.update_project(
        project_id,
        {
            "run_id": "run-sqlite-1",
            "status": "generating",
            "ai_result": {
                "qualityProfile": "UNAC_MAINTENANCE_V2",
                "sections": [
                    {
                        "sectionId": "intro",
                        "path": "INTRODUCCIÓN",
                        "content": [{"tipo": "parrafo", "texto": "Contenido validado"}],
                        "qualityAudit": {
                            "status": "ok",
                            "words": 694,
                            "units": [
                                {
                                    "key": "introduccion",
                                    "heading": "Introducción",
                                    "status": "ok",
                                    "words": 694,
                                },
                                {
                                    "key": "introduccion.auxiliar",
                                    "heading": "Unidad auxiliar",
                                    "status": "ok",
                                    "words": 10,
                                },
                            ],
                        },
                    }
                ],
            },
            "generation_phase": {
                "status": "running",
                "sections": [
                    {
                        "section_id": "intro",
                        "section_path": "INTRODUCCIÓN",
                        "prompt_sent": "PROMPT COMPLETO",
                        "ai_output": "RESPUESTA COMPLETA",
                        "provider": "mistral",
                        "model": "mistral-medium-2505",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "duration_ms": 1200,
                        "status": "ok",
                    }
                ],
            },
        },
    )

    compact = service.repository.list(include_events=False)[0]
    assert compact["ai_result"]["sections"] == []
    assert "prompt_template" not in compact
    assert compact["generation_phase"]["sections"][0].get("prompt_sent") is None
    assert compact["generation_phase"]["sections"][0].get("ai_output") is None

    restored = service.get_project(project_id)
    assert restored is not None
    assert restored["prompt_template"] == "PLANTILLA COMPLETA DEL PROYECTO"
    assert restored["ai_result"]["sections"][0]["content"][0]["texto"] == "Contenido validado"
    assert restored["generation_phase"]["sections"][0]["prompt_sent"] == "PROMPT COMPLETO"
    assert restored["generation_phase"]["sections"][0]["ai_output"] == "RESPUESTA COMPLETA"

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT count(*) FROM project_sections").fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM project_sections WHERE validation_status='validated'"
        ).fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM ai_calls").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    with service.repository._connect() as configured_connection:  # type: ignore[attr-defined]
        assert configured_connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert configured_connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_sqlite_event_window_and_concurrent_updates_survive_restart(tmp_path):
    db_path = tmp_path / "gicagen.db"
    service = ProjectService(str(db_path), backend="sqlite")
    project_id = service.create_project({"title": "Concurrencia"})["id"]

    for index in range(250):
        service.append_event(project_id, {"message": f"event-{index}", "stage": "test"})

    def update(index: int) -> None:
        service.update_progress(project_id, current=index, total=200, current_path=f"unidad-{index}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(update, range(1, 201)))

    reopened = ProjectService(str(db_path), backend="sqlite")
    restored = reopened.get_project(project_id)
    assert restored is not None
    assert len(restored["events"]) == 200
    assert restored["events"][0]["message"] == "event-50"
    assert restored["events"][-1]["message"] == "event-249"
    assert restored["progress"]["total"] == 200
    assert 1 <= restored["progress"]["current"] <= 200


def test_sqlite_progress_updates_do_not_reload_or_rewrite_other_sections(tmp_path):
    db_path = tmp_path / "performance.db"
    service = ProjectService(str(db_path), backend="sqlite")
    project_id = service.create_project({"title": "Rendimiento"})["id"]
    sections = [
        {
            "sectionId": f"section-{index}",
            "path": f"Sección {index}",
            "content": [{"tipo": "parrafo", "texto": " ".join([f"palabra{index}"] * 1200)}],
        }
        for index in range(25)
    ]
    service.update_project(project_id, {"run_id": "run-performance", "ai_result": {"sections": sections}})

    started = time.perf_counter()
    for index in range(200):
        service.update_progress(project_id, current=index + 1, total=200, current_path=f"unidad-{index + 1}")
    elapsed = time.perf_counter() - started

    assert elapsed / 200 < 0.05
    restored = service.get_project(project_id)
    assert restored is not None
    assert len(restored["ai_result"]["sections"]) == 25
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT count(*) FROM project_sections").fetchone()[0] == 25

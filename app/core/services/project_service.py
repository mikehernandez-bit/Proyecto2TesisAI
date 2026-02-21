from __future__ import annotations
import datetime as dt
from typing import Any, Dict, List, Optional
from app.core.utils.id import new_id
from app.core.database import db_manager, ProjectDB

class ProjectService:
    """Stores generation projects in PostgreSQL via SQLAlchemy."""

    def _to_dict(self, db_obj: ProjectDB) -> Dict[str, Any]:
        """Convierte el objeto SQLAlchemy a un diccionario que el frontend entiende."""
        if not db_obj:
            return None
        return {
            "id": db_obj.id,
            "title": db_obj.title,
            "prompt_id": db_obj.prompt_id,
            "prompt_name": db_obj.prompt_name,
            "prompt_template": db_obj.prompt_template,
            "format_id": db_obj.format_id,
            "format_name": db_obj.format_name,
            "format_version": db_obj.format_version,
            "variables": db_obj.variables or {},
            "values": db_obj.values_data or {},
            "status": db_obj.status,
            "created_at": db_obj.created_at,
            "updated_at": db_obj.updated_at,
            "output_file": db_obj.output_file,
            "error": db_obj.error,
            "ai_result": db_obj.ai_result,
            "run_id": db_obj.run_id,
            "artifacts": db_obj.artifacts or []
        }

    def list_projects(self) -> List[Dict[str, Any]]:
        with next(db_manager.get_session()) as db:
            projects = db.query(ProjectDB).order_by(ProjectDB.created_at.desc()).all()
            return [self._to_dict(p) for p in projects]

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with next(db_manager.get_session()) as db:
            project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            return self._to_dict(project)

    def create_project(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with next(db_manager.get_session()) as db:
            now = dt.datetime.now().isoformat(timespec="seconds")
            values = payload.get("variables")
            if values is None:
                values = payload.get("values", {})
            
            new_project = ProjectDB(
                id=new_id("proj"),
                title=payload.get("title") or payload.get("tema") or "Proyecto sin título",
                prompt_id=payload.get("prompt_id"),
                prompt_name=payload.get("prompt_name"),
                prompt_template=payload.get("prompt_template"),
                format_id=payload.get("format_id"),
                format_name=payload.get("format_name"),
                format_version=payload.get("format_version"),
                variables=values or {},
                values_data=values or {},
                status=payload.get("status") or "processing",
                created_at=now,
                updated_at=now
            )
            db.add(new_project)
            db.commit()
            db.refresh(new_project)
            return self._to_dict(new_project)

    def update_project(self, project_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with next(db_manager.get_session()) as db:
            project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if not project:
                return None

            for key, value in payload.items():
                if key == "values": # Mapear values a values_data
                    setattr(project, "values_data", value)
                elif hasattr(project, key):
                    setattr(project, key, value)
            
            if "variables" in payload or "values" in payload:
                v = payload.get("variables") or payload.get("values", {})
                project.variables = v
                project.values_data = v

            project.updated_at = dt.datetime.now().isoformat(timespec="seconds")
            db.commit()
            db.refresh(project)
            return self._to_dict(project)

    def mark_ai_received(self, project_id: str, ai_result: Dict[str, Any], run_id: Optional[str] = None, artifacts: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        return self.update_project(project_id, {
            "status": "ai_received",
            "ai_result": ai_result,
            "run_id": run_id,
            "artifacts": artifacts or [],
            "error": None
        })

    def mark_simulated(self, project_id: str, ai_result: Dict[str, Any], run_id: str, artifacts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return self.update_project(project_id, {
            "status": "simulated",
            "ai_result": ai_result,
            "run_id": run_id,
            "artifacts": artifacts,
            "error": None
        })

    def mark_completed(self, project_id: str, output_file: str) -> Optional[Dict[str, Any]]:
        return self.update_project(project_id, {
            "status": "completed",
            "output_file": output_file,
            "error": None
        })

    def mark_failed(self, project_id: str, error: str) -> Optional[Dict[str, Any]]:
        return self.update_project(project_id, {
            "status": "failed",
            "error": error
        })
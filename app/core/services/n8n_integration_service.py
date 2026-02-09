from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings


class N8NIntegrationService:
    """Build wizard step 4 contracts and simulation payload examples."""

    def build_spec(
        self,
        project: Dict[str, Any],
        format_detail: Optional[Dict[str, Any]] = None,
        prompt: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        project_id = str(project.get("id") or "")
        callback_url = f"{settings.GICAGEN_BASE_URL.rstrip('/')}/api/integrations/n8n/callback"
        base_url = settings.GICATESIS_BASE_URL.rstrip("/")
        run_id = str(project.get("run_id") or f"sim-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")

        format_obj = self._format_summary(project, format_detail)
        prompt_obj = self._prompt_summary(project, prompt)
        values = self._project_values(project)
        format_definition = (
            format_detail.get("definition")
            if isinstance(format_detail, dict) and isinstance(format_detail.get("definition"), dict)
            else {}
        )

        webhook_url = settings.N8N_WEBHOOK_URL or "<configure N8N_WEBHOOK_URL>"
        secret = settings.N8N_SHARED_SECRET or "<configure N8N_SHARED_SECRET>"

        request_payload = {
            "projectId": project_id,
            "format": {
                "id": format_obj["id"],
                "version": format_obj["version"],
                "university": format_obj["university"],
                "category": format_obj["category"],
                "documentType": format_obj["documentType"],
            },
            "prompt": {
                "id": prompt_obj["id"],
                "text": prompt_obj["text"],
            },
            "values": values,
            "runtime": {
                "gicatesisBaseUrl": base_url,
                "callbackUrl": callback_url,
            },
        }

        expected_body = self.build_simulated_output(project_id=project_id, run_id=run_id)

        spec = {
            "mode": "simulation",
            "summary": {
                "projectId": project_id,
                "status": project.get("status") or "draft",
                "format": {
                    "id": format_obj["id"],
                    "version": format_obj["version"],
                    "university": format_obj["university"],
                    "category": format_obj["category"],
                    "documentType": format_obj["documentType"],
                    "title": format_obj["title"],
                },
                "prompt": {
                    "id": prompt_obj["id"],
                    "name": prompt_obj["name"],
                    "preview": prompt_obj["preview"],
                },
            },
            "envCheck": {
                "GICATESIS_BASE_URL": {
                    "ok": bool(settings.GICATESIS_BASE_URL),
                    "value": settings.GICATESIS_BASE_URL or "",
                },
                "N8N_WEBHOOK_URL": {
                    "ok": bool(settings.N8N_WEBHOOK_URL),
                    "value": settings.N8N_WEBHOOK_URL or "",
                },
                "N8N_SHARED_SECRET": {
                    "ok": bool(settings.N8N_SHARED_SECRET),
                    "value": "***configured***" if settings.N8N_SHARED_SECRET else "",
                },
            },
            "request": {
                "webhookUrl": webhook_url,
                "headers": {
                    "X-GICAGEN-SECRET": secret,
                },
                "payload": request_payload,
            },
            "formatDetail": format_detail or {
                "id": format_obj["id"],
                "title": format_obj["title"],
                "university": format_obj["university"],
                "category": format_obj["category"],
                "documentType": format_obj["documentType"],
                "version": format_obj["version"],
                "fields": [],
                "assets": [],
                "definition": {},
            },
            "formatDefinition": format_definition,
            "promptDetail": {
                "id": prompt_obj["id"],
                "name": prompt_obj["name"],
                "text": prompt_obj["text"],
                "variables": prompt_obj["variables"],
            },
            "promptText": prompt_obj["text"],
            "expectedResponse": {
                "callbackUrl": callback_url,
                "headers": {
                    "X-N8N-SECRET": secret,
                },
                "bodyExample": expected_body,
            },
            "simulationOutput": self._latest_or_example_output(project, expected_body),
            "checklist": self._checklist(),
        }
        spec["markdown"] = self._build_markdown(spec)
        return spec

    def build_simulated_output(self, project_id: str, run_id: str) -> Dict[str, Any]:
        return {
            "projectId": project_id,
            "runId": run_id,
            "status": "success",
            "aiResult": {
                "sections": [
                    {"title": "Introduccion", "content": "Texto generado por simulacion."},
                    {"title": "Marco teorico", "content": "Contexto y antecedentes de ejemplo."},
                    {"title": "Metodologia", "content": "Detalle metodologico de ejemplo."},
                ]
            },
            "artifacts": [
                {
                    "type": "docx",
                    "name": "simulated.docx",
                    "downloadUrl": (
                        f"{settings.GICAGEN_BASE_URL.rstrip('/')}/api/sim/download/docx"
                        f"?projectId={project_id}&runId={run_id}"
                    ),
                },
                {
                    "type": "pdf",
                    "name": "simulated.pdf",
                    "downloadUrl": (
                        f"{settings.GICAGEN_BASE_URL.rstrip('/')}/api/sim/download/pdf"
                        f"?projectId={project_id}&runId={run_id}"
                    ),
                },
            ],
        }

    def _latest_or_example_output(
        self,
        project: Dict[str, Any],
        example_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_run = project.get("run_id")
        ai_result = project.get("ai_result")
        artifacts = project.get("artifacts")

        if isinstance(ai_result, dict):
            return {
                "projectId": str(project.get("id") or ""),
                "runId": str(current_run or example_output["runId"]),
                "status": "success",
                "aiResult": ai_result,
                "artifacts": artifacts if isinstance(artifacts, list) else example_output["artifacts"],
            }
        return example_output

    def _checklist(self) -> List[Dict[str, Any]]:
        return [
            {"step": 1, "title": "Webhook Trigger", "detail": "Crear trigger POST en n8n para recibir request.payload."},
            {"step": 2, "title": "Secret compartido", "detail": "Configurar X-GICAGEN-SECRET en entrada y X-N8N-SECRET en callback."},
            {"step": 3, "title": "GET format", "detail": "Consumir formato desde request.runtime.gicatesisBaseUrl + /formats/{id}."},
            {"step": 4, "title": "Prompt final", "detail": "Combinar prompt.text con values para construir el prompt de ejecucion."},
            {"step": 5, "title": "IA a JSON", "detail": "Ejecutar IA y producir JSON estable en aiResult."},
            {"step": 6, "title": "Validacion", "detail": "Validar estructura antes de callback (projectId, status, aiResult, artifacts)."},
            {"step": 7, "title": "Callback", "detail": "Enviar POST al callbackUrl con header X-N8N-SECRET."},
            {"step": 8, "title": "Responder al webhook", "detail": "Responder 200 al trigger inicial y guardar trazabilidad de runId."},
        ]

    def _project_values(self, project: Dict[str, Any]) -> Dict[str, Any]:
        values = project.get("values")
        if isinstance(values, dict):
            return values
        values = project.get("variables")
        if isinstance(values, dict):
            return values
        return {}

    def _format_summary(self, project: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if detail and isinstance(detail, dict):
            return {
                "id": detail.get("id") or project.get("format_id") or "",
                "version": detail.get("version"),
                "university": detail.get("university"),
                "category": detail.get("category"),
                "documentType": detail.get("documentType"),
                "title": detail.get("title") or project.get("format_name") or detail.get("id") or "",
            }
        return {
            "id": project.get("format_id") or "",
            "version": project.get("format_version"),
            "university": None,
            "category": None,
            "documentType": None,
            "title": project.get("format_name") or project.get("format_id") or "",
        }

    def _prompt_summary(self, project: Dict[str, Any], prompt: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        text = ""
        name = ""
        prompt_id = project.get("prompt_id") or ""
        variables: List[str] = []
        if prompt and isinstance(prompt, dict):
            text = str(prompt.get("template") or "")
            name = str(prompt.get("name") or "")
            prompt_id = str(prompt.get("id") or prompt_id)
            raw_variables = prompt.get("variables")
            if isinstance(raw_variables, list):
                variables = [str(v) for v in raw_variables]
        else:
            text = str(project.get("prompt_template") or "")
            name = str(project.get("prompt_name") or "")

        preview = text[:500] if len(text) > 500 else text
        return {
            "id": prompt_id,
            "name": name,
            "text": text,
            "preview": preview,
            "variables": variables,
        }

    def _build_markdown(self, spec: Dict[str, Any]) -> str:
        summary = spec.get("summary", {})
        checklist = spec.get("checklist", [])
        env_check = spec.get("envCheck", {})

        env_lines = []
        for key, value in env_check.items():
            mark = "OK" if value.get("ok") else "MISSING"
            env_lines.append(f"- `{key}`: {mark} ({value.get('value')})")

        checklist_lines = []
        for item in checklist:
            checklist_lines.append(f"{item.get('step')}. {item.get('title')}: {item.get('detail')}")

        payload_json = json.dumps(spec.get("request", {}).get("payload", {}), indent=2, ensure_ascii=False)
        request_headers_json = json.dumps(spec.get("request", {}).get("headers", {}), indent=2, ensure_ascii=False)
        callback_headers_json = json.dumps(spec.get("expectedResponse", {}).get("headers", {}), indent=2, ensure_ascii=False)
        format_definition_json = json.dumps(spec.get("formatDefinition", {}), indent=2, ensure_ascii=False)
        output_json = json.dumps(spec.get("simulationOutput", {}), indent=2, ensure_ascii=False)

        return (
            "# Guia operativa n8n (simulacion)\n\n"
            "## A) Resumen\n"
            f"- projectId: {summary.get('projectId')}\n"
            f"- status: {summary.get('status')}\n"
            f"- formato: {summary.get('format', {}).get('title')}\n"
            f"- prompt: {summary.get('prompt', {}).get('name')}\n\n"
            "## B) Auto-check\n"
            f"{chr(10).join(env_lines)}\n\n"
            "## C) Payload copiable\n"
            f"```json\n{payload_json}\n```\n\n"
            "## D) Headers copiable\n"
            f"Entrada n8n:\n```json\n{request_headers_json}\n```\n\n"
            f"Callback a GicaGen:\n```json\n{callback_headers_json}\n```\n\n"
            "## E) Checklist 8 pasos\n"
            f"{chr(10).join(checklist_lines)}\n\n"
            "## F) URLs\n"
            f"- webhook: `{spec.get('request', {}).get('webhookUrl')}`\n"
            f"- callback: `{spec.get('expectedResponse', {}).get('callbackUrl')}`\n\n"
            "## G) Formato completo (definition)\n"
            f"```json\n{format_definition_json}\n```\n\n"
            "## H) Simulacion de respuesta n8n (output)\n"
            f"```json\n{output_json}\n```\n"
        )

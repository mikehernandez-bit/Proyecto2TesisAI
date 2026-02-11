# Integracion GicaTesis y Simulacion n8n

## Resumen
GicaGen consume formatos de GicaTesis usando un BFF. El frontend solo llama a `http://localhost:8001/api/*`.

- Upstream formatos: `http://localhost:8000/api/v1`
- BFF GicaGen: `http://localhost:8001/api`

## Endpoints BFF de formatos
- `GET /api/formats/version`
- `GET /api/formats`
- `GET /api/formats/{id}`
- `GET /api/assets/{path}`

## Endpoints de proyecto e integracion
- `POST /api/projects/draft`
- `GET /api/projects/{project_id}`
- `PUT /api/projects/{project_id}`
- `GET /api/integrations/n8n/spec?projectId=...`
- `POST /api/integrations/n8n/callback`
- `POST /api/sim/n8n/run?projectId=...`
- `GET /api/sim/download/docx?projectId=...`
- `GET /api/sim/download/pdf?projectId=...`
- `GET /api/_meta/build`

## Contrato de `POST /api/projects/draft`
Body opcional:

```json
{
  "title": "opcional",
  "formatId": "opcional",
  "promptId": "opcional",
  "values": {
    "campo": "valor"
  }
}
```

Respuesta:

```json
{
  "id": "proj_xxx",
  "projectId": "proj_xxx",
  "status": "draft"
}
```

## Contrato de `GET /api/integrations/n8n/spec`
Devuelve modo simulacion y bloques para Step 4:

- `mode`
- `summary`
- `envCheck`
- `request`
- `formatDetail`
- `formatDefinition`
- `promptDetail`
- `expectedResponse`
- `simulationOutput`
- `checklist` (8 pasos)
- `markdown`

Estructura esperada:

```json
{
  "mode": "simulation",
  "summary": {
    "projectId": "proj_xxx",
    "status": "draft",
    "format": {
      "id": "unac-informe-cual",
      "version": "abc123",
      "university": "unac",
      "category": "informe",
      "documentType": "cual",
      "title": "Informe Cual"
    },
    "prompt": {
      "id": "prompt_tesis_estandar",
      "name": "Tesis Ingenieria Estandar",
      "preview": "..."
    }
  },
  "envCheck": {
    "GICATESIS_BASE_URL": { "ok": true, "value": "http://localhost:8000/api/v1" },
    "N8N_WEBHOOK_URL": { "ok": false, "value": "" },
    "N8N_SHARED_SECRET": { "ok": false, "value": "" }
  },
  "request": {
    "webhookUrl": "<configure N8N_WEBHOOK_URL>",
    "headers": { "X-GICAGEN-SECRET": "<configure N8N_SHARED_SECRET>" },
    "payload": {
      "projectId": "proj_xxx",
      "format": {
        "id": "unac-informe-cual",
        "version": "abc123",
        "university": "unac",
        "category": "informe",
        "documentType": "cual"
      },
      "prompt": {
        "id": "prompt_tesis_estandar",
        "text": "prompt completo"
      },
      "values": {
        "tema": "..."
      },
      "runtime": {
        "gicatesisBaseUrl": "http://localhost:8000/api/v1",
        "callbackUrl": "http://localhost:8001/api/integrations/n8n/callback"
      }
    }
  },
  "formatDetail": {},
  "formatDefinition": {},
  "promptDetail": {
    "id": "prompt_tesis_estandar",
    "name": "Tesis Ingenieria Estandar",
    "text": "prompt completo",
    "variables": ["tema", "objetivo_general"]
  },
  "expectedResponse": {
    "callbackUrl": "http://localhost:8001/api/integrations/n8n/callback",
    "headers": { "X-N8N-SECRET": "<configure N8N_SHARED_SECRET>" },
    "bodyExample": {
      "projectId": "proj_xxx",
      "runId": "sim-20260206...",
      "status": "success",
      "aiResult": {
        "sections": [
          { "title": "Introduccion", "content": "..." }
        ]
      },
      "artifacts": [
        { "type": "docx", "name": "simulated.docx", "downloadUrl": "http://localhost:8001/api/sim/download/docx?projectId=proj_xxx" },
        { "type": "pdf", "name": "simulated.pdf", "downloadUrl": "http://localhost:8001/api/sim/download/pdf?projectId=proj_xxx" }
      ]
    }
  },
  "simulationOutput": {
    "projectId": "proj_xxx",
    "runId": "sim-20260206...",
    "status": "success",
    "aiResult": {
      "sections": [
        { "title": "Resumen ejecutivo", "content": "..." }
      ]
    },
    "artifacts": [
      { "type": "docx", "name": "simulated.docx", "downloadUrl": "http://localhost:8001/api/sim/download/docx?projectId=proj_xxx&runId=sim-20260206..." },
      { "type": "pdf", "name": "simulated.pdf", "downloadUrl": "http://localhost:8001/api/sim/download/pdf?projectId=proj_xxx&runId=sim-20260206..." }
    ]
  },
  "checklist": [
    { "step": 1, "title": "Webhook Trigger", "detail": "..." }
  ],
  "markdown": "# Guia operativa n8n (simulacion)"
}
```

## Callback stub de simulacion
`POST /api/integrations/n8n/callback`

- Si `N8N_SHARED_SECRET` esta configurado, valida `X-N8N-SECRET`.
- Guarda `aiResult`, `runId`, `artifacts`.
- Marca proyecto con estado `ai_received`.

## Descargas simuladas
- `GET /api/sim/download/docx?projectId=...`
- `GET /api/sim/download/pdf?projectId=...`

Generan archivos placeholder sin depender de IA real ni de n8n.

## Simulacion manual de n8n
`POST /api/sim/n8n/run?projectId=...`

- Genera `runId` de simulacion.
- Persiste `ai_result` y `artifacts` en el proyecto.
- Marca el proyecto con estado `simulated`.
- Devuelve JSON listo para mostrar en Paso 4 (seccion H) y para habilitar descargas.

## Build info para validar instancia activa
`GET /api/_meta/build`

Respuesta:

```json
{
  "service": "gicagen",
  "cwd": "c:\\Users\\jhoan\\Documents\\gicagen_tesis-main",
  "started_at": "2026-02-06T18:31:46.523432+00:00",
  "git_commit": "db75975"
}
```

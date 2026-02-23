# Integracion GicaTesis

> Documentacion de la integracion BFF entre GicaGen y GicaTesis para formatos academicos.

---

## Arquitectura de la Integracion

```mermaid
graph LR
    subgraph "GicaGen (puerto 8001)"
        API[api/router.py]
        FMT_SVC[FormatService]
        GT_CLIENT[GicaTesisClient]
        GT_CACHE[FormatCache]
        GT_TYPES[DTOs - types.py]
        GT_ERRORS[errors.py]
    end
    
    subgraph "GicaTesis (puerto 8000)"
        GT_API[/api/v1/formats]
        GT_ASSETS[/api/v1/assets]
        GT_VERSION[/api/v1/formats/version]
    end
    
    API -->|GET /api/formats| FMT_SVC
    FMT_SVC --> GT_CLIENT
    FMT_SVC --> GT_CACHE
    GT_CLIENT -->|httpx async| GT_API
    GT_CLIENT -->|httpx async| GT_ASSETS
    GT_CLIENT -->|httpx async| GT_VERSION
    GT_CACHE -->|data/gicatesis_cache.json| GT_CACHE
```

## Modulo de Integracion

**Ubicacion:** `app/integrations/gicatesis/`

| Archivo | Proposito | Lineas |
|---------|-----------|--------|
| `client.py` | Cliente HTTP async para GicaTesis API v1 | 136 |
| `types.py` | DTOs Pydantic que reflejan contratos API | 64 |
| `errors.py` | Excepciones custom para errores upstream | 28 |
| `cache/format_cache.py` | Cache local con ETag y timestamps | ~50 |

### DTOs (types.py)

```python
class FormatSummary(BaseModel):
    id: str
    title: str
    university: str
    category: str | None
    documentType: str | None
    version: str

class FormatDetail(FormatSummary):
    description: str | None
    fields: list[FormatField]
    definition: dict | None     # Estructura del documento
    assets: list[AssetRef]
    templates: list[TemplateRef]

class CatalogVersionResponse(BaseModel):
    current: str
    cached: str | None
    changed: bool
```

### Errores (errors.py)

```python
class GicaTesisError(Exception): ...
class UpstreamUnavailable(GicaTesisError): ...   # GicaTesis no accesible
class UpstreamTimeout(GicaTesisError): ...        # Request excedio timeout
class BadUpstreamResponse(GicaTesisError): ...    # Respuesta invalida
```

---

## Endpoints BFF (GicaGen -> Browser)

### GET /api/formats

Retorna lista de formatos desde GicaTesis con cache.

**Query params:** `university`, `category`, `documentType`

**Response:**
```json
{
  "formats": [
    {
      "id": "unac-tesis-2024",
      "title": "Formato Tesis UNAC 2024",
      "university": "UNAC",
      "category": "Proyecto de Tesis",
      "documentType": "tesis",
      "version": "1.0"
    }
  ],
  "stale": false,
  "cached_at": "2024-01-15T10:30:00Z"
}
```

**Flujo BFF:**
1. Verifica version con GicaTesis (`/api/v1/formats/version`)
2. Si la version no cambio, retorna cache local
3. Si cambio, sincroniza desde GicaTesis
4. Si GicaTesis no esta disponible, retorna cache stale
5. Si no hay cache, usa `data/formats_sample.json` (demo)

### GET /api/formats/{id}

Retorna detalle de un formato especifico.

**Response:** `FormatDetail` con `definition` (estructura del documento).

### GET /api/formats/version

Retorna version actual del catalogo.

**Response:**
```json
{
  "current": "2024-01-15T10:30:00Z",
  "cached": "2024-01-14T08:00:00Z",
  "changed": true
}
```

### GET /api/assets/{path}

Proxy para assets de GicaTesis (logos, imagenes).

**Flujo:** GicaGen -> GicaTesis `/api/v1/assets/{path}` -> respuesta streamed.

---

## Endpoints de Proyecto

### POST /api/projects/draft

Crea un borrador de proyecto desde el wizard.

**Request:**
```json
{
  "title": "Mi Tesis",
  "formatId": "unac-tesis-2024",
  "promptId": "prompt_tesis_estandar",
  "values": {
    "tema": "Inteligencia Artificial",
    "titulo_propuesto": "IA en Educacion"
  }
}
```

**Response:**
```json
{
  "projectId": "proj_abc123",
  "status": "draft",
  "title": "Mi Tesis"
}
```

### GET /api/projects

Lista todos los proyectos creados.

### GET /api/projects/{id}

Detalle de un proyecto especifico.

### PUT /api/projects/{id}

Actualiza campos del proyecto.

### POST /api/projects/{id}/generate

Inicia la generacion en modo **asyncrono**.

- Respuesta rapida: `202 Accepted`.
- No espera a que termine la IA.
- El trabajo corre en background y actualiza el proyecto de forma incremental.

**Response:**
```json
{
  "ok": true,
  "status": "generating",
  "projectId": "proj_abc123",
  "runId": "gemini-20260219180617",
  "mode": "async"
}
```

### GET /api/projects/{id} (estado en vivo)

Este endpoint es la fuente principal para polling del Paso 4 (cada 1s).

Campos relevantes para UI:

- `status`: `draft | generating | ai_received | completed | failed | blocked | cancel_requested`
- `progress`:
  - `current`: secciones completadas/actuales
  - `total`: total de secciones detectadas
  - `currentPath`: ruta/nombre de la seccion actual
  - `provider`: proveedor activo (`gemini` o `mistral`)
  - `updatedAt`: marca temporal de ultimo avance
- `events`: timeline incremental (maximo 200)

**Fragmento de ejemplo:**
```json
{
  "id": "proj_abc123",
  "status": "generating",
  "progress": {
    "current": 12,
    "total": 74,
    "currentPath": "1.2 Planteamiento del problema",
    "provider": "gemini",
    "updatedAt": "2026-02-19T18:06:17"
  },
  "events": [
    {
      "ts": "2026-02-19T18:06:17Z",
      "level": "info",
      "stage": "section_start",
      "message": "IA: seccion 12/74 (...)",
      "provider": "gemini",
      "sectionCurrent": 12,
      "sectionTotal": 74,
      "sectionPath": "1.2 Planteamiento del problema"
    }
  ]
}
```

## Reglas de compilacion de secciones IA

GicaGen compila `definition` a `section_index` antes de llamar a IA.
La compilacion evita ramas no generativas para proteger el render final.

Secciones excluidas del `section_index`:

- `preliminares.indices` y cualquier subitem del indice.
- nodos de indice de tablas, indice de figuras e indice de abreviaturas.
- ramas de `imagenes`, `figuras`, `tablas` y equivalentes de placeholders.

Secciones incluidas:

- capitulos y subcapitulos reales del `cuerpo`.
- anexos textuales, cuando existen en `definition`.
- abreviaturas solo cuando no pertenecen a un bloque de indice.

Fallback defensivo:

- Si una ruta de indice llega por error a IA, el prompt devuelve
  `<<SKIP_SECTION>>`.
- El `OutputValidator` normaliza ese token a contenido vacio antes de enviar
  `aiResult` al render.

## Relleno de `values.title`

Antes de enviar payload a GicaTesis (`render/docx`, `render/pdf`, o
`_ai_generation_job`), GicaGen normaliza valores:

- Si `values.title` esta vacio, se completa con `project.title`.

Este fallback evita que la caratula quede con texto placeholder.

### POST /api/projects/{id}/cancel

Solicita la cancelacion de una corrida en curso.

El backend marca `cancel_requested` y el loop de generacion se detiene en el
siguiente punto seguro.

---

## Endpoints de Integracion n8n

### GET /api/integrations/n8n/spec

Retorna la guia/contrato para el paso 4 del wizard.

**Query:** `projectId`

**Response:**
```json
{
  "summary": "...",
  "environmentCheck": {...},
  "requestPayload": {...},
  "requestHeaders": {...},
  "checklist": [...],
  "markdownGuide": "...",
  "simulationOutput": {
    "aiResult": {...},
    "artifacts": [...]
  },
  "formatDefinition": {...},
  "promptDetail": {...},
  "sectionIndex": [...]
}
```

### POST /api/integrations/n8n/callback

Recibe resultado de n8n (o simulacion).

**Request:**
```json
{
  "projectId": "proj_abc123",
  "aiResult": {
    "sections": {...}
  }
}
```

### GET /api/integrations/n8n/health

Health check de la integracion n8n.

---

## Endpoints de Simulacion

### POST /api/sim/n8n/run

Ejecuta una simulacion completa de n8n.

**Query:** `projectId`

**Response:**
```json
{
  "runId": "sim_abc123",
  "projectId": "proj_abc123",
  "status": "simulated",
  "aiResult": {...},
  "artifacts": [
    {"type": "docx", "url": "/api/sim/download/docx?projectId=..."},
    {"type": "pdf", "url": "/api/sim/download/pdf?projectId=..."}
  ]
}
```

### GET /api/sim/download/docx

Descarga el DOCX simulado.

### GET /api/sim/download/pdf

Descarga el PDF simulado.

---

## Endpoints Legacy

### POST /api/projects/generate

Genera un proyecto (modo legacy).

### GET /api/download/{id}

Descarga DOCX generado (modo legacy).

---

## Build Info

### GET /api/_meta/build

Retorna informacion de la instancia activa.

**Response:**
```json
{
  "service": "gicagen",
  "cwd": "C:\\Users\\jhoan\\Documents\\gicagen_tesis-main",
  "started_at": "2024-01-15T10:30:00Z",
  "git_commit": "abc1234"
}
```

---

## Configuracion

**Variables de entorno (`.env`):**

| Variable | Descripcion | Default |
|----------|-------------|---------|
| `GICATESIS_BASE_URL` | Base URL de GicaTesis API v1 | `http://localhost:8000/api/v1` |
| `GICATESIS_TIMEOUT` | Timeout para requests (segundos) | `8` |
| `GICAGEN_PORT` | Puerto de GicaGen | `8001` |
| `GICAGEN_BASE_URL` | URL base de GicaGen | `http://localhost:8001` |
| `GICAGEN_DEMO_MODE` | Usar datos demo si GicaTesis no disponible | `false` |
| `N8N_WEBHOOK_URL` | URL webhook de n8n (opcional) | `""` |
| `N8N_SHARED_SECRET` | Secreto compartido n8n (opcional) | `""` |

---

## Notas Tecnicas

- GicaTesis corre en port **8000**, GicaGen en port **8001**
- La integracion usa patron **BFF** (Backend for Frontend)
- El cache usa **ETag** para validacion eficiente
- Si GicaTesis no esta disponible, GicaGen funciona con cache stale
- Si no hay cache, existe un **fallback demo** con `data/formats_sample.json`
- Los assets (logos, imagenes) se proxean desde GicaTesis via `/api/assets/`

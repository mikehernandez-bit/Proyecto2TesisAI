# GicaGen

GicaGen es un generador de documentos academicos con FastAPI + SPA.
El flujo principal es **code-first**: GicaGen genera con IA y luego envia a
GicaTesis para render DOCX/PDF.

## Estado actual (February 19, 2026)

- `POST /api/projects/{id}/generate` ahora responde rapido con **202 Accepted**.
- La generacion corre en segundo plano y registra progreso en `project.progress`
  y eventos en `project.events`.
- Paso 4 del wizard muestra pipeline en vivo con progreso por secciones,
  fallback de proveedor y timeline expandible.
- n8n sigue disponible solo como ruta legacy/deprecated.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --port 8001 --reload
```

Abre `http://127.0.0.1:8001/`.

## Variables clave

Fuente: `app/core/config.py` y `.env.example`.

| Variable | Default | Uso |
|---|---|---|
| `GEMINI_API_KEY` | `""` | Autenticacion Gemini |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Modelo Gemini |
| `MISTRAL_API_KEY` | `""` | Autenticacion Mistral |
| `MISTRAL_MODEL` | `mistral-medium-2505` | Modelo Mistral |
| `AI_PRIMARY_PROVIDER` | `gemini` | Proveedor primario |
| `AI_FALLBACK_ON_QUOTA` | `true` | Fallback entre proveedores |
| `GICATESIS_BASE_URL` | `http://localhost:8000/api/v1` | Upstream GicaTesis |
| `GICAGEN_DEMO_MODE` | `false` | Catalogo demo sin upstream |

## Reglas de secciones IA

El compilador de secciones de GicaGen (`compile_definition_to_section_index`)
solo envia a IA bloques generativos.

Se excluyen automaticamente:

- `preliminares.indices` y subitems.
- secciones de indice de tablas, figuras y abreviaturas.
- ramas de figuras/tablas/imagenes que son placeholders del formato.

Se incluyen:

- capitulos y subcapitulos del `cuerpo`.
- contenido textual de anexos cuando el formato lo define.
- abreviaturas solo cuando no forman parte de un indice.

Esto evita colisiones entre encabezados del indice y capitulos reales en el
payload `aiResult.sections`.

Si, por cualquier motivo, entra una seccion de indice al pipeline IA, el
prompt de generacion/correccion usa el token `<<SKIP_SECTION>>` y la capa de
validacion lo normaliza a contenido vacio para no contaminar DOCX/PDF.

## Fallback de titulo en caratula

Antes de generar y antes de enviar payload a GicaTesis, GicaGen garantiza:

- si `values.title` viene vacio, usa `project.title` como respaldo.

Con esto, la caratula no queda con placeholders como `TÍTULO DEL PROYECTO`.

## Trace en vivo (Paso 4)

El frontend consume eventos reales del backend, no eventos simulados.

Endpoints:

- `GET /api/projects/{projectId}` (estado, `progress`, `events`)
- `GET /api/projects/{projectId}/trace`
- `GET /api/projects/{projectId}/trace/stream` (SSE)
- `POST /api/projects/{projectId}/cancel`

Estructura incremental en `GET /api/projects/{projectId}`:

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

Estructura de evento:

```json
{
  "ts": "2026-02-19T16:01:02Z",
  "step": "ai.generate.section",
  "status": "running|done|error|warn",
  "title": "IA: seccion 12/74 (Introduccion)",
  "detail": "texto corto",
  "meta": {"sectionIndex": 12, "sectionTotal": 74},
  "preview": {"prompt": "...", "raw": "...", "clean": "..."}
}
```

Notas:

- `project.events` rota automaticamente y conserva maximo 200 eventos.
- `project.trace` se mantiene por compatibilidad y refleja la misma lista.
- Los previews se recortan y se sanitizan para no exponer secretos.

## Comportamiento ante cuota IA (429)

Con el flujo async (`202`), los errores de cuota no salen como respuesta final
inmediata del `POST /generate`.

Comportamiento esperado:

1. El endpoint acepta la ejecucion (`202`).
2. El trace registra `ai.provider.quota` y, si aplica, `ai.provider.fallback`.
3. Si no se puede recuperar, el proyecto termina en `failed` o `blocked`.
4. El Paso 4 muestra el error en vivo y permite reintentar.

## Resolver "No Cloud Projects Available" en AI Studio

1. Crea o selecciona un proyecto en Google Cloud.
2. En AI Studio abre **Dashboard -> Projects -> Import projects**.
3. Importa el proyecto y crea la API key.
4. Guarda la key solo en `.env` local.

```dotenv
GEMINI_API_KEY="<YOUR_GEMINI_API_KEY>"
```

Referencia oficial:

- https://ai.google.dev/gemini-api/docs/api-key

## Runbook de GicaTesis

Si GicaTesis no esta disponible, las rutas de render/proxy devuelven `503`
con mensaje de remediacion.

Ver detalles en:

- `docs/06-desarrollo-local.md`
- `docs/09-troubleshooting.md`

## Testing rapido

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python scripts/quality_gate.py lint
.venv\Scripts\python scripts/quality_gate.py typecheck
.venv\Scripts\python -m pytest tests -v
.venv\Scripts\python scripts/check_encoding.py
.venv\Scripts\python scripts/check_mojibake.py
```

## Como correr CI localmente

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python scripts/quality_gate.py all
.venv\Scripts\python -m pytest tests -v
```

## E2E scaffold (P1)

- `playwright.config.ts`
- `e2e/tests/wizard.demo.spec.ts`
- `e2e/tests/wizard.quota.spec.ts`
- `package.json`

```powershell
npm install
npm run e2e:install
npm run e2e
```

## Known gaps / TODO

- P1: migrar SDK `google-generativeai` a `google.genai`.
- P1: ampliar cobertura `mypy` a mas modulos.
- P1: expandir E2E con backend real y fixtures.
- P2: agregar stage E2E opcional en CI.

## Documentacion

Indice: `docs/00-indice.md`.

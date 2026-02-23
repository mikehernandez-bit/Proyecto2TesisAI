# Catalogo de Archivos - GicaGen

> Inventario completo de archivos con proposito, tipo, dependencias y estado sugerido.

---

## Archivos Raiz

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `README.md` | doc | Documentacion principal del proyecto | Desarrolladores, GitHub | Mantener |
| `AGENTS.md` | doc | Entrada rapida para agentes AI | Agentes | Mantener |
| `readme.txt` | doc | Descripcion tecnica adicional | Desarrolladores | Unificar con README.md |
| `requirements.txt` | config | Dependencias Python | pip install | Mantener |
| `.env.example` | config | Ejemplo de variables de entorno | Desarrolladores | Mantener |

---

## `/app` - Codigo Principal

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/__init__.py` | codigo | Marca app como paquete Python | Python imports | Mantener |
| `app/main.py` | codigo | **Entrypoint** FastAPI: monta routers y static files (34 lineas) | uvicorn | Mantener |

---

## `/app/core` - Nucleo de Negocio

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/core/__init__.py` | codigo | Marca core como paquete | Python imports | Mantener |
| `app/core/config.py` | config | Settings singleton (dataclass frozen) desde env vars via python-dotenv (30 lineas) | Todos los modulos | Mantener |
| `app/core/templates.py` | codigo | Configuracion de Jinja2Templates (3 lineas) | ui/router.py | Mantener |

---

## `/app/core/clients` - Clientes HTTP Legacy

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/core/clients/__init__.py` | codigo | Marca clients como paquete | Python imports | Mantener |
| `app/core/clients/gicatesis_client.py` | codigo | Cliente HTTP legacy para GicaTesis (168 lineas) | (legacy, reemplazado) | Evaluar eliminacion |

---

## `/app/core/services` - Servicios de Negocio

| Archivo | Tipo | Proposito | Lineas | Consumido por | Estado |
|---------|------|-----------|--------|---------------|--------|
| `app/core/services/__init__.py` | codigo | Marca services como paquete | - | Python imports | Mantener |
| `app/core/services/format_service.py` | codigo | Orquesta formatos via GicaTesis con cache ETag | 277 | api/router.py | Mantener |
| `app/core/services/prompt_service.py` | codigo | CRUD de prompts (list, get, create, update, delete) | ~60 | api/router.py | Mantener |
| `app/core/services/project_service.py` | codigo | CRUD de proyectos y estados | ~170 | api/router.py | Mantener |
| `app/core/services/docx_builder.py` | codigo | Genera documento DOCX placeholder (legacy) | ~25 | api/router.py | Mover a adapters |
| `app/core/services/n8n_client.py` | codigo | Cliente HTTP para webhook n8n | ~120 | api/router.py | Mover a adapters |
| `app/core/services/n8n_integration_service.py` | codigo | Arma spec del paso 4 (payload/headers/checklist/markdown) | 303 | api/router.py | Mantener |
| `app/core/services/definition_compiler.py` | codigo | Compila definiciones de formato a IR (headings, secciones, placeholders) | 371 | n8n_integration_service, simulation_artifact_service | Mantener |
| `app/core/services/simulation_artifact_service.py` | codigo | Genera DOCX/PDF simulados desde IR de formato | 346 | api/router.py | Mantener |

---

## `/app/core/storage` - Persistencia

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/core/storage/__init__.py` | codigo | Marca storage como paquete | Python imports | Mantener |
| `app/core/storage/json_store.py` | codigo | Storage generico JSON con locks (read_list, write_list) | PromptService, ProjectService | Mover a adapters |

---

## `/app/core/utils` - Utilidades

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/core/utils/__init__.py` | codigo | Marca utils como paquete | Python imports | Mantener |
| `app/core/utils/id.py` | codigo | Genera IDs unicos con prefijo (ej: `proj_abc123`) | PromptService, ProjectService | Mantener |

---

## `/app/integrations` - Integraciones Externas

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/integrations/__init__.py` | codigo | Marca integrations como paquete | Python imports | Mantener |

---

## `/app/integrations/gicatesis` - Integracion GicaTesis

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/integrations/gicatesis/__init__.py` | codigo | Marca gicatesis como paquete | Python imports | Mantener |
| `app/integrations/gicatesis/client.py` | codigo | Cliente HTTP async para GicaTesis API v1 (136 lineas) | FormatService | Mantener |
| `app/integrations/gicatesis/types.py` | codigo | DTOs Pydantic: FormatSummary, FormatDetail, FormatField, AssetRef, TemplateRef, CatalogVersionResponse (64 lineas) | FormatService, client.py | Mantener |
| `app/integrations/gicatesis/errors.py` | codigo | Excepciones: GicaTesisError, UpstreamUnavailable, UpstreamTimeout, BadUpstreamResponse (28 lineas) | client.py, format_service.py | Mantener |

---

## `/app/integrations/gicatesis/cache` - Cache de Formatos

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/integrations/gicatesis/cache/__init__.py` | codigo | Marca cache como paquete | Python imports | Mantener |
| `app/integrations/gicatesis/cache/format_cache.py` | codigo | Cache de formatos con ETag, timestamps y persistencia en JSON | FormatService | Mantener |

---

## `/app/modules/api` - API REST

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/modules/api/__init__.py` | codigo | Marca api como paquete | Python imports | Mantener |
| `app/modules/api/router.py` | codigo | **Router principal**: 21+ endpoints (730 lineas) | main.py | Mantener |
| `app/modules/api/models.py` | codigo | 5 modelos Pydantic: PromptIn, ProjectDraftIn, ProjectUpdateIn, ProjectGenerateIn, N8NCallbackIn (76 lineas) | api/router.py | Mantener |

---

## `/app/modules/ui` - Interfaz Web

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/modules/ui/__init__.py` | codigo | Marca ui como paquete | Python imports | Mantener |
| `app/modules/ui/router.py` | codigo | Endpoint GET `/` que renderiza pagina principal (8 lineas) | main.py | Mantener |

---

## `/app/static/js` - Frontend

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/static/js/app.js` | codigo | **Frontend SPA completo** (898 lineas): Dashboard, Wizard 5 pasos, CRUD prompts, Historial | Browser | Mantener |

---

## `/app/templates` - HTML

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `app/templates/base.html` | template | Layout base HTML (head, CDNs Tailwind/FontAwesome) (31 lineas) | pages/app.html | Mantener |
| `app/templates/pages/app.html` | template | Pagina principal: Sidebar, Dashboard, Wizard, Admin, History (433 lineas) | ui/router.py | Mantener |

---

## `/data` - Datos JSON

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `data/formats_sample.json` | asset | Formatos institucionales de ejemplo (fallback demo) | FormatService | Mantener |
| `data/prompts.json` | asset | Prompts guardados por el usuario | PromptService via JsonStore | Mantener |
| `data/projects.json` | asset | Historial de proyectos generados | ProjectService via JsonStore | Mantener |
| `data/gicatesis_cache.json` | cache | Cache de formatos sincronizados desde GicaTesis con ETag | FormatCache | Mantener (regenerable) |

---

## `/scripts` - Utilidades

| Archivo | Tipo | Proposito | Consumido por | Estado |
|---------|------|-----------|---------------|--------|
| `scripts/check_encoding.py` | script | Verifica encoding UTF-8 de archivos del repositorio | Desarrolladores (pre-commit) | Mantener |
| `scripts/check_mojibake.py` | script | Detecta caracteres mojibake (corrupcion de encoding) | Desarrolladores (pre-commit) | Mantener |
| `scripts/fix_encoding.py` | script | Corrige automaticamente problemas de encoding en archivos | Desarrolladores | Mantener |

---

## Archivos `__pycache__` (Excluidos)

Los archivos `.pyc` en carpetas `__pycache__/` son cache de bytecode Python. Se excluyen del catalogo por ser generados automaticamente.

---

## Resumen por Clasificacion

| Pertenece a | Cantidad | Archivos principales |
|-------------|----------|---------------------|
| **core** | 12 | main.py, config.py, templates.py, format_service.py, prompt_service.py, project_service.py, n8n_integration_service.py, definition_compiler.py, simulation_artifact_service.py, id.py |
| **integrations** | 6 | client.py, types.py, errors.py, format_cache.py |
| **adapters** (propuestos mover) | 3 | docx_builder.py, n8n_client.py, json_store.py |
| **ports-interfaces** | 3 | api/router.py, api/models.py |
| **ui** | 5 | ui/router.py, app.js, base.html, app.html |
| **config** | 2 | requirements.txt, .env.example |
| **assets** | 4 | formats_sample.json, prompts.json, projects.json, gicatesis_cache.json |
| **docs** | 3 | README.md, AGENTS.md, readme.txt |
| **scripts** | 3 | check_encoding.py, check_mojibake.py, fix_encoding.py |

---

## Estadisticas del Repositorio

> **Fuente:** Conteo real del repositorio (excluyendo `.venv`, `__pycache__`, `.git`, `.cca`, `outputs`)

| Metrica | Valor |
|---------|-------|
| Archivos totales | 73 |
| Archivos de codigo Python (.py) | 33 |
| Lineas de codigo Python | 2875 |
| Lineas de codigo JavaScript | 898 |
| Lineas de HTML | 464 (base.html: 31, app.html: 433) |
| Archivos de datos JSON | 4 |
| Archivos de configuracion | 2 (requirements.txt, .env.example) |
| Scripts de utilidad | 3 |
| Dependencias Python | 7 paquetes (+ python-dotenv implicito) |

---

## Set Minimo para Ejecutar el Sistema

### Archivos Estrictamente Necesarios

```
requirements.txt                    # Dependencias
app/
+-- __init__.py
+-- main.py                         # Entrypoint
+-- core/
|   +-- __init__.py
|   +-- config.py                   # Settings
|   +-- templates.py                # Jinja config
|   +-- services/
|   |   +-- __init__.py
|   |   +-- format_service.py       # Formatos BFF
|   |   +-- prompt_service.py
|   |   +-- project_service.py
|   |   +-- docx_builder.py
|   |   +-- n8n_client.py
|   |   +-- n8n_integration_service.py
|   |   +-- definition_compiler.py
|   |   `-- simulation_artifact_service.py
|   +-- storage/
|   |   +-- __init__.py
|   |   `-- json_store.py
|   `-- utils/
|       +-- __init__.py
|       `-- id.py
+-- integrations/
|   +-- __init__.py
|   `-- gicatesis/
|       +-- __init__.py
|       +-- client.py
|       +-- types.py
|       +-- errors.py
|       `-- cache/
|           +-- __init__.py
|           `-- format_cache.py
+-- modules/
|   +-- __init__.py
|   +-- api/
|   |   +-- __init__.py
|   |   +-- router.py
|   |   `-- models.py
|   `-- ui/
|       +-- __init__.py
|       `-- router.py
+-- static/
|   `-- js/
|       `-- app.js
`-- templates/
    +-- base.html
    `-- pages/
        `-- app.html
data/
+-- formats_sample.json             # Puede estar vacio: []
+-- prompts.json                    # Puede estar vacio: []
`-- projects.json                   # Puede estar vacio: []
```

### Archivos Opcionales/Eliminables

| Archivo | Justificacion |
|---------|---------------|
| `readme.txt` | Duplica informacion de README.md |
| `docs/*` | No afecta ejecucion |
| `AGENTS.md` | Solo para agentes AI |
| `scripts/*` | Utilidades de mantenimiento |
| `data/gicatesis_cache.json` | Se regenera automaticamente |
| `app/core/clients/*` | Legacy, reemplazado por integrations/ |
| `__pycache__/*` | Cache regenerable |

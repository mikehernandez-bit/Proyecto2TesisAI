# Catálogo de Archivos - GicaGen

> Inventario completo de archivos con propósito, tipo, dependencias y estado sugerido.

---

## Archivos Raíz

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado |
|---------|------|-----------|---------------|-------------|--------|
| `README.md` | doc | Documentación principal del proyecto | Desarrolladores, GitHub | docs | ✅ Mantener |
| `AGENTS.md` | doc | Entrada rápida para agentes AI | Agentes | docs | ✅ Mantener |
| `readme.txt` | doc | Descripción técnica adicional | Desarrolladores | docs | ⚠️ Unificar con README.md |
| `requirements.txt` | config | Dependencias Python | pip install | config | ✅ Mantener |
| `.env.example` | config | Ejemplo de variables de entorno | Desarrolladores | config | ✅ Mantener |

---

## `/app` - Código Principal

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado |
|---------|------|-----------|---------------|-------------|--------|
| `app/__init__.py` | código | Marca app como paquete Python | Python imports | core | ✅ Mantener |
| `app/main.py` | código | **Entrypoint** FastAPI: monta routers y static files | uvicorn | core | ✅ Mantener |

---

## `/app/core` - Núcleo de Negocio

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado |
|---------|------|-----------|---------------|-------------|--------|
| `app/core/__init__.py` | código | Marca core como paquete | Python imports | core | ✅ Mantener |
| `app/core/config.py` | config | Settings singleton desde env vars (APP_NAME, FORMAT_API_*, N8N_*) | Todos los módulos | config | ✅ Mantener |
| `app/core/templates.py` | código | Configuración de Jinja2Templates | ui/router.py | core | ✅ Mantener |

---

## `/app/core/services` - Servicios de Negocio

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado | Nota de Acoplamiento |
|---------|------|-----------|---------------|-------------|--------|---------------------|
| `app/core/services/__init__.py` | código | Marca services como paquete | Python imports | core | ✅ Mantener | - |
| `app/core/services/format_api.py` | código | Obtiene formatos institucionales (API externa o sample local) | api/router.py | **adapters** | ⚡ Mover | ⚠️ Mezcla HTTP client + fallback local. Separar en interface + adapter |
| `app/core/services/prompt_service.py` | código | CRUD de prompts (list, get, create, update, delete) | api/router.py | core | ✅ Mantener | ⚠️ Depende directamente de JsonStore |
| `app/core/services/project_service.py` | código | CRUD de proyectos y estados (create, mark_completed, mark_failed) | api/router.py | core | ✅ Mantener | ⚠️ Depende directamente de JsonStore |
| `app/core/services/docx_builder.py` | código | Genera documento DOCX placeholder (modo demo) | api/router.py | **adapters** | ⚡ Mover | ⚠️ Dependencia directa a python-docx. Debería ser adapter |
| `app/core/services/n8n_client.py` | código | Cliente HTTP para webhook n8n | api/router.py | **adapters** | ⚡ Mover | ⚠️ Integración externa. Debería ser adapter con interface |

---

## `/app/core/storage` - Persistencia

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado | Nota de Acoplamiento |
|---------|------|-----------|---------------|-------------|--------|---------------------|
| `app/core/storage/__init__.py` | código | Marca storage como paquete | Python imports | infra | ✅ Mantener | - |
| `app/core/storage/json_store.py` | código | Storage genérico JSON con locks (read_list, write_list) | PromptService, ProjectService | **adapters** | ⚡ Mover | Implementación de persistencia - debería ser adapter que implemente interface |

---

## `/app/core/utils` - Utilidades

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado |
|---------|------|-----------|---------------|-------------|--------|
| `app/core/utils/__init__.py` | código | Marca utils como paquete | Python imports | core | ✅ Mantener |
| `app/core/utils/id.py` | código | Genera IDs únicos con prefijo (ej: `proj_abc123`) | PromptService, ProjectService | core | ✅ Mantener |

---

## `/app/modules/api` - API REST

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado | Nota de Acoplamiento |
|---------|------|-----------|---------------|-------------|--------|---------------------|
| `app/modules/api/__init__.py` | código | Marca api como paquete | Python imports | ports-interfaces | ✅ Mantener | - |
| `app/modules/api/router.py` | código | **Router principal**: endpoints /formats, /prompts, /projects, /download, /n8n/callback | main.py | ports-interfaces | ✅ Mantener | ⚠️ Instancia servicios como globals en vez de usar Depends() |
| `app/modules/api/models.py` | código | Modelos Pydantic: PromptIn, ProjectGenerateIn | api/router.py | ports-interfaces | ✅ Mantener | - |

---

## `/app/modules/ui` - Interfaz Web

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado |
|---------|------|-----------|---------------|-------------|--------|
| `app/modules/ui/__init__.py` | código | Marca ui como paquete | Python imports | ui | ✅ Mantener |
| `app/modules/ui/router.py` | código | Endpoint GET `/` que renderiza página principal | main.py | ui | ✅ Mantener |

---

## `/app/static/js` - Frontend

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado | Nota |
|---------|------|-----------|---------------|-------------|--------|------|
| `app/static/js/app.js` | código | **Frontend SPA completo** (563 líneas): Dashboard, Wizard 4 pasos, CRUD prompts, Historial | Browser | ui | ✅ Mantener | ⚠️ Archivo grande - considerar modularizar si crece |

---

## `/app/templates` - HTML

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado |
|---------|------|-----------|---------------|-------------|--------|
| `app/templates/base.html` | template | Layout base HTML (head, CDNs Tailwind/FontAwesome) | pages/app.html | ui | ✅ Mantener |
| `app/templates/pages/app.html` | template | Página principal (416 líneas): Sidebar, Dashboard, Wizard, Admin, History | ui/router.py | ui | ✅ Mantener |

---

## `/data` - Datos JSON

| Archivo | Tipo | Propósito | Consumido por | Pertenece a | Estado |
|---------|------|-----------|---------------|-------------|--------|
| `data/formats_sample.json` | asset | Formatos institucionales de ejemplo (UNT, UPN) | FormatService | assets | ✅ Mantener |
| `data/prompts.json` | asset | Prompts guardados por el usuario | PromptService via JsonStore | assets | ✅ Mantener |
| `data/projects.json` | asset | Historial de proyectos generados | ProjectService via JsonStore | assets | ✅ Mantener |

---

## Archivos `__pycache__` (Excluidos)

Los archivos `.pyc` en carpetas `__pycache__/` son cache de bytecode Python. Se excluyen del catálogo por ser generados automáticamente.

---

## Resumen por Clasificación

| Pertenece a | Cantidad | Archivos |
|-------------|----------|----------|
| **core** | 8 | main.py, config.py, templates.py, prompt_service.py, project_service.py, id.py, __init__.py (varios) |
| **adapters** (propuestos) | 4 | format_api.py, docx_builder.py, n8n_client.py, json_store.py |
| **ports-interfaces** | 3 | api/router.py, api/models.py, api/__init__.py |
| **ui** | 5 | ui/router.py, app.js, base.html, app.html, ui/__init__.py |
| **config** | 2 | requirements.txt, .env.example |
| **assets** | 3 | formats_sample.json, prompts.json, projects.json |
| **docs** | 3 | README.md, AGENTS.md, readme.txt |

---

## Set Mínimo para Ejecutar el Sistema

### Archivos Estrictamente Necesarios

```
requirements.txt                    # Dependencias
app/
├── __init__.py
├── main.py                         # Entrypoint
├── core/
│   ├── __init__.py
│   ├── config.py                   # Settings
│   ├── templates.py                # Jinja config
│   ├── services/
│   │   ├── __init__.py
│   │   ├── format_api.py
│   │   ├── prompt_service.py
│   │   ├── project_service.py
│   │   ├── docx_builder.py
│   │   └── n8n_client.py
│   ├── storage/
│   │   ├── __init__.py
│   │   └── json_store.py
│   └── utils/
│       ├── __init__.py
│       └── id.py
├── modules/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── models.py
│   └── ui/
│       ├── __init__.py
│       └── router.py
├── static/
│   └── js/
│       └── app.js
└── templates/
    ├── base.html
    └── pages/
        └── app.html
data/
├── formats_sample.json             # Puede estar vacío: []
├── prompts.json                    # Puede estar vacío: []
└── projects.json                   # Puede estar vacío: []
```

### Archivos Opcionales/Eliminables

| Archivo | Justificación |
|---------|---------------|
| `readme.txt` | Duplica información de README.md |
| `docs/*` | No afecta ejecución |
| `AGENTS.md` | Solo para agentes AI |
| `__pycache__/*` | Cache regenerable |

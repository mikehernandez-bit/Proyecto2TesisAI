# Arquitectura - GicaGen

> Documentación de la arquitectura actual y objetivo del sistema.

---

## A) Arquitectura Actual

### Diagrama de Componentes

```mermaid
graph TB
    subgraph "Capa de Presentación"
        BROWSER[Browser]
        JS[app.js - SPA]
        HTML[templates/app.html]
    end
    
    subgraph "Capa de Entrada (FastAPI)"
        MAIN[main.py]
        API_ROUTER[api/router.py]
        UI_ROUTER[ui/router.py]
    end
    
    subgraph "Capa de Servicios (Core)"
        FMT_SVC[FormatService]
        PRM_SVC[PromptService]
        PRJ_SVC[ProjectService]
        DOCX_SVC[DocxBuilder]
        N8N_SVC[N8NClient]
    end
    
    subgraph "Capa de Infraestructura"
        JSON_STORE[JsonStore]
        CONFIG[config.py]
    end
    
    subgraph "Recursos Externos"
        FS[(Filesystem - data/*.json)]
        EXT_API[API Externa de Formatos]
        N8N_WH[n8n Webhook]
    end
    
    BROWSER --> JS
    JS --> API_ROUTER
    MAIN --> API_ROUTER
    MAIN --> UI_ROUTER
    UI_ROUTER --> HTML
    
    API_ROUTER --> FMT_SVC
    API_ROUTER --> PRM_SVC
    API_ROUTER --> PRJ_SVC
    API_ROUTER --> DOCX_SVC
    API_ROUTER --> N8N_SVC
    
    FMT_SVC --> CONFIG
    FMT_SVC --> FS
    FMT_SVC -.-> EXT_API
    
    PRM_SVC --> JSON_STORE
    PRJ_SVC --> JSON_STORE
    JSON_STORE --> FS
    
    N8N_SVC --> CONFIG
    N8N_SVC -.-> N8N_WH
    
    DOCX_SVC --> FS
```

### Componentes Detectados

| Componente | Archivo | Responsabilidad |
|------------|---------|-----------------|
| **Entrypoint** | `app/main.py` | Configura FastAPI, monta routers y static files |
| **API Router** | `app/modules/api/router.py` | 15 endpoints REST para formatos, prompts, proyectos |
| **UI Router** | `app/modules/ui/router.py` | Renderiza página principal via Jinja2 |
| **FormatService** | `app/core/services/format_api.py` | Obtiene formatos (API externa o sample local) |
| **PromptService** | `app/core/services/prompt_service.py` | CRUD de prompts |
| **ProjectService** | `app/core/services/project_service.py` | CRUD de proyectos y estados |
| **DocxBuilder** | `app/core/services/docx_builder.py` | Genera DOCX placeholder |
| **N8NClient** | `app/core/services/n8n_client.py` | Trigger webhook n8n |
| **JsonStore** | `app/core/storage/json_store.py` | Persistencia JSON con locks |
| **Config** | `app/core/config.py` | Settings desde env vars |

### Flujos Principales

#### 1. Generación de Documento (Wizard)

```mermaid
sequenceDiagram
    participant B as Browser
    participant API as api/router
    participant PS as ProjectService
    participant N8N as N8NClient
    participant DOCX as DocxBuilder
    participant FS as Filesystem
    
    B->>API: POST /api/projects/generate
    API->>PS: create_project()
    PS-->>API: project (status: processing)
    API-->>B: project
    
    Note over API: Background Task
    API->>N8N: trigger(payload)
    alt n8n configurado y responde
        N8N-->>API: {ok: true}
        Note over API: Espera callback /api/n8n/callback/{id}
    else n8n no disponible
        API->>DOCX: build_demo_docx()
        DOCX->>FS: save .docx
        API->>PS: mark_completed()
    end
    
    loop Polling cada 1.2s
        B->>API: GET /api/projects/{id}
        API->>PS: get_project()
        PS-->>B: project
    end
```

#### 2. CRUD de Prompts

```
Browser → POST/PUT/DELETE /api/prompts → PromptService → JsonStore → data/prompts.json
```

### Entrypoints

| Entrypoint | Descripción |
|------------|-------------|
| `python -m uvicorn app.main:app` | Servidor web principal |
| `GET /` | UI principal (SPA) |
| `GET /api/formats` | Lista formatos |
| `GET/POST/PUT/DELETE /api/prompts` | CRUD prompts |
| `GET/POST /api/projects` | Lista/crea proyectos |
| `POST /api/projects/generate` | Inicia generación |
| `GET /api/download/{id}` | Descarga DOCX |
| `POST /api/n8n/callback/{id}` | Callback desde n8n |
| `GET /healthz` | Health check |

### Dependencias Cruzadas Peligrosas

| Problema | Evidencia | Severidad |
|----------|-----------|-----------|
| **Servicios como globals** | `api/router.py:19-22` instancia `FormatService()`, `PromptService()`, etc. como variables globales | 🟡 Media |
| **Core depende de infraestructura** | `prompt_service.py:4` importa `JsonStore` directamente | 🟡 Media |
| **Adapters en core** | `format_api.py` usa `httpx` directamente, `docx_builder.py` usa `python-docx` | 🟡 Media |
| **Config hardcodeada** | `docx_builder.py:21` tiene secciones fijas | 🟢 Baja |

---

## B) Arquitectura Objetivo (Propuesta)

### Diagrama con Boundaries

```mermaid
graph TB
    subgraph "UI Layer"
        BROWSER[Browser]
        JS[app.js]
        TEMPLATES[Jinja Templates]
    end
    
    subgraph "API Layer (Ports)"
        API[FastAPI Routers]
        MODELS[Pydantic Models]
    end
    
    subgraph "Core Domain"
        direction TB
        subgraph "Services"
            PROMPT_SVC[PromptService]
            PROJECT_SVC[ProjectService]
            GEN_SVC[GenerationService]
        end
        subgraph "Ports/Interfaces"
            I_STORE[IDataStore]
            I_DOCGEN[IDocumentGenerator]
            I_FORMAT[IFormatProvider]
            I_WORKFLOW[IWorkflowEngine]
        end
    end
    
    subgraph "Adapters Layer"
        JSON_ADAPTER[JsonStoreAdapter]
        DOCX_ADAPTER[DocxAdapter]
        FORMAT_ADAPTER[ExternalFormatAdapter]
        N8N_ADAPTER[N8NAdapter]
    end
    
    subgraph "Infra Layer"
        CONFIG[Settings]
        FS[Filesystem]
        HTTP[HTTP Client]
    end
    
    subgraph "External"
        EXT_API[API Formatos]
        N8N[n8n]
        GICATESIS[GicaTesis - futuro]
    end
    
    BROWSER --> JS
    JS --> API
    API --> MODELS
    API --> PROMPT_SVC
    API --> PROJECT_SVC
    API --> GEN_SVC
    
    PROMPT_SVC --> I_STORE
    PROJECT_SVC --> I_STORE
    GEN_SVC --> I_DOCGEN
    GEN_SVC --> I_FORMAT
    GEN_SVC --> I_WORKFLOW
    
    I_STORE -.->|implements| JSON_ADAPTER
    I_DOCGEN -.->|implements| DOCX_ADAPTER
    I_FORMAT -.->|implements| FORMAT_ADAPTER
    I_WORKFLOW -.->|implements| N8N_ADAPTER
    
    JSON_ADAPTER --> FS
    DOCX_ADAPTER --> FS
    FORMAT_ADAPTER --> HTTP
    FORMAT_ADAPTER --> EXT_API
    N8N_ADAPTER --> HTTP
    N8N_ADAPTER --> N8N
    
    FORMAT_ADAPTER -.->|futuro| GICATESIS
```

### Estructura de Carpetas Propuesta

```
app/
├── main.py                      # Composition root
├── core/
│   ├── domain/                  # Entidades de dominio (si las hay)
│   ├── services/                # Servicios de negocio
│   │   ├── prompt_service.py
│   │   ├── project_service.py
│   │   └── generation_service.py
│   └── ports/                   # Interfaces/Contratos
│       ├── data_store.py        # Protocol IDataStore
│       ├── document_generator.py
│       ├── format_provider.py
│       └── workflow_engine.py
├── adapters/                    # ← NUEVO
│   ├── storage/
│   │   └── json_store_adapter.py
│   ├── documents/
│   │   └── docx_adapter.py
│   ├── formats/
│   │   └── external_format_adapter.py
│   └── workflows/
│       └── n8n_adapter.py
├── infra/                       # ← NUEVO
│   ├── config.py
│   └── http_client.py
├── modules/                     # Se mantiene igual
│   ├── api/
│   └── ui/
└── ...
```

---

## C) Reglas de Acoplamiento

### Principios

1. **Core no importa adapters/infra**
   - ❌ `from app.adapters.storage import JsonStore`
   - ✅ `from app.core.ports import IDataStore` (interface)

2. **Adapters implementan ports**
   - Los adapters implementan las interfaces definidas en `core/ports/`
   - Ejemplo: `JsonStoreAdapter` implementa `IDataStore`

3. **Composition root hace el wiring**
   - `main.py` crea las instancias concretas y las inyecta
   - Usar `Depends()` de FastAPI para inyección

4. **Config declarativa manda**
   - Las URLs, claves y opciones vienen de `config.py`
   - No hardcodear en servicios

### Ejemplo de Código (Propuesto)

```python
# core/ports/data_store.py
from typing import Protocol, List, Dict, Any

class IDataStore(Protocol):
    def read_list(self) -> List[Dict[str, Any]]: ...
    def write_list(self, items: List[Dict[str, Any]]) -> None: ...

# core/services/prompt_service.py
class PromptService:
    def __init__(self, store: IDataStore):  # ← Inyectado
        self.store = store
    # ...

# adapters/storage/json_store_adapter.py
class JsonStoreAdapter:
    """Implementa IDataStore usando archivos JSON."""
    # ... (el código actual de json_store.py)

# main.py (composition root)
from fastapi import Depends

def get_prompt_store():
    return JsonStoreAdapter("data/prompts.json")

def get_prompt_service(store = Depends(get_prompt_store)):
    return PromptService(store)

@router.get("/prompts")
def list_prompts(svc: PromptService = Depends(get_prompt_service)):
    return svc.list_prompts()
```

---

## D) Plan de Desacoplo

### Problemas Identificados

| # | Problema | Evidencia | Impacto |
|---|----------|-----------|---------|
| 1 | Servicios como globals en router | `api/router.py:19-22` | Testing difícil, no inyectable |
| 2 | PromptService depende de JsonStore | `prompt_service.py:4` | Core acoplado a infra |
| 3 | ProjectService depende de JsonStore | `project_service.py:7` | Core acoplado a infra |
| 4 | FormatService mezcla HTTP y archivo | `format_api.py` | Difícil testear/cambiar |
| 5 | DocxBuilder usa python-docx directo | `docx_builder.py` | No reemplazable |
| 6 | N8NClient en core | `n8n_client.py` | Integración en core |

### Soluciones Propuestas

| # | Solución | Archivos a modificar | Riesgo |
|---|----------|---------------------|--------|
| 1 | Usar `Depends()` de FastAPI | `api/router.py`, `main.py` | 🟢 Bajo |
| 2-3 | Crear `IDataStore` Protocol, inyectar | `prompt_service.py`, `project_service.py`, nuevo `ports/` | 🟡 Medio |
| 4 | Crear `IFormatProvider`, mover a adapters | `format_api.py` → `adapters/` | 🟡 Medio |
| 5 | Crear `IDocumentGenerator`, mover a adapters | `docx_builder.py` → `adapters/` | 🟡 Medio |
| 6 | Crear `IWorkflowEngine`, mover a adapters | `n8n_client.py` → `adapters/` | 🟡 Medio |

### Orden Recomendado de Ejecución

1. **Fase 1 (Bajo riesgo):** Cambiar servicios globals a `Depends()` en router
2. **Fase 2:** Crear carpeta `core/ports/` con interfaces
3. **Fase 3:** Mover `json_store.py` a `adapters/storage/`, hacer que implemente interface
4. **Fase 4:** Actualizar servicios para recibir interface inyectada
5. **Fase 5:** Mover `format_api.py`, `n8n_client.py`, `docx_builder.py` a `adapters/`

### Checklist de Validación Post-Cambios

- [ ] `python -m uvicorn app.main:app --reload` inicia sin errores
- [ ] Navegar a http://127.0.0.1:8000/ carga correctamente
- [ ] Wizard completo funciona (pasos 1-4)
- [ ] CRUD de prompts funciona
- [ ] Descargar DOCX generado funciona
- [ ] `GET /healthz` retorna `{"ok": true}`

---

## Diagrama de Arquitectura (Archivo)

Ver diagrama completo en: [diagramas/arquitectura.mmd](diagramas/arquitectura.mmd)

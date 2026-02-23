# Catalogo de Carpetas - GicaGen

> Inventario completo de carpetas del repositorio con proposito, responsabilidades, criticidad y recomendaciones.

---

## `/` (Raiz)

| Atributo | Valor |
|----------|-------|
| **Proposito** | Raiz del proyecto. Contiene configuracion, documentacion raiz y punto de entrada. |
| **Responsabilidades** | - Archivos de configuracion (requirements.txt, .env.example)<br>- Documentacion (README.md, AGENTS.md)<br>- Directorio principal de codigo (app/) |
| **Dependencias** | Entrante: ninguna. Saliente: app/, data/, docs/ |
| **Criticidad** | Critica |
| **Riesgos** | Ninguno identificado |
| **Recomendacion** | Mantener |

---

## `/app`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Codigo fuente principal de la aplicacion FastAPI. |
| **Responsabilidades** | - Entrypoint (`main.py`)<br>- Configuracion y core (`core/`)<br>- Modulos API y UI (`modules/`)<br>- Integraciones externas (`integrations/`)<br>- Assets estaticos y templates |
| **Dependencias** | Entrante: `main.py` ejecutado por uvicorn. Saliente: `data/` para persistencia JSON |
| **Criticidad** | Critica |
| **Riesgos** | Ninguno - estructura clara |
| **Recomendacion** | Mantener |

---

## `/app/core`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Logica de negocio central: configuracion, servicios, storage, utilidades. |
| **Responsabilidades** | - `config.py`: Settings desde env vars (dataclass frozen)<br>- `templates.py`: Configuracion Jinja2<br>- `clients/`: Cliente HTTP legacy<br>- `services/`: 8 servicios de negocio<br>- `storage/`: Persistencia JSON<br>- `utils/`: Generador de IDs |
| **Dependencias** | Entrante: `app/modules/`, `app/integrations/`. Saliente: `data/` (archivos JSON) |
| **Criticidad** | Critica |
| **Riesgos** | Los servicios dependen directamente de `JsonStore` (acoplamiento a infraestructura) |
| **Recomendacion** | Reestructurar - Separar interfaces de implementaciones |

---

## `/app/core/clients`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Clientes HTTP legacy para APIs externas. |
| **Responsabilidades** | - `gicatesis_client.py`: Cliente HTTP legacy para GicaTesis (168 lineas) |
| **Dependencias** | Entrante: ninguna directa (legacy). Saliente: httpx, config.py |
| **Criticidad** | Baja (reemplazado por `integrations/gicatesis/`) |
| **Riesgos** | Codigo duplicado con `integrations/gicatesis/client.py` |
| **Recomendacion** | Evaluar eliminacion si ya no se usa |

---

## `/app/core/services`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Servicios de negocio que implementan la logica principal. |
| **Responsabilidades** | - `format_service.py`: Orquesta formatos via GicaTesis con cache ETag<br>- `prompt_service.py`: CRUD de prompts<br>- `project_service.py`: CRUD de proyectos/historial<br>- `docx_builder.py`: Genera DOCX placeholder (legacy)<br>- `n8n_client.py`: Cliente para webhook n8n<br>- `n8n_integration_service.py`: Arma spec del paso 4<br>- `definition_compiler.py`: Compila definiciones de formato a IR<br>- `simulation_artifact_service.py`: Genera DOCX/PDF simulados desde IR |
| **Dependencias** | Entrante: `app/modules/api/router.py`. Saliente: `storage/`, `config.py`, `utils/`, `integrations/gicatesis/`, librerias externas (httpx, python-docx) |
| **Criticidad** | Critica |
| **Riesgos** | Servicios instanciados directamente en router (no inyeccion) |
| **Recomendacion** | Reestructurar - Aplicar inyeccion de dependencias |

---

## `/app/core/storage`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Capa de persistencia simple basada en archivos JSON. |
| **Responsabilidades** | - `json_store.py`: Lectura/escritura de listas JSON con locks |
| **Dependencias** | Entrante: `ProjectService`, `PromptService`. Saliente: filesystem (`data/`) |
| **Criticidad** | Importante |
| **Riesgos** | No escalable para produccion (concurrencia limitada, sin transacciones) |
| **Recomendacion** | Mantener para MVP, documentar como adapter reemplazable |

---

## `/app/core/utils`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Utilidades genericas reutilizables. |
| **Responsabilidades** | - `id.py`: Generador de IDs con prefijo (ej: `proj_abc123`) |
| **Dependencias** | Entrante: `ProjectService`, `PromptService`. Saliente: ninguna |
| **Criticidad** | Opcional |
| **Riesgos** | Ninguno |
| **Recomendacion** | Mantener |

---

## `/app/integrations`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Modulo de integraciones con sistemas externos. |
| **Responsabilidades** | - Contiene submodulos para cada integracion externa<br>- Actualmente solo GicaTesis |
| **Dependencias** | Entrante: `core/services/format_service.py`. Saliente: APIs externas via httpx |
| **Criticidad** | Critica |
| **Riesgos** | Ninguno - bien aislado |
| **Recomendacion** | Mantener |

---

## `/app/integrations/gicatesis`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Integracion completa con GicaTesis API v1 para formatos academicos. |
| **Responsabilidades** | - `client.py`: Cliente HTTP async con manejo de errores (136 lineas)<br>- `types.py`: DTOs Pydantic (FormatSummary, FormatDetail, FormatField, AssetRef, etc.)<br>- `errors.py`: Excepciones custom (UpstreamUnavailable, UpstreamTimeout, BadUpstreamResponse)<br>- `cache/`: Subcarpeta de cache |
| **Dependencias** | Entrante: `core/services/format_service.py`. Saliente: httpx, GicaTesis API |
| **Criticidad** | Critica |
| **Riesgos** | Dependencia de GicaTesis disponible; mitigado con cache y fallback |
| **Recomendacion** | Mantener |

---

## `/app/integrations/gicatesis/cache`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Cache de formatos con validacion ETag para evitar requests innecesarios. |
| **Responsabilidades** | - `format_cache.py`: Lectura/escritura de cache local (`data/gicatesis_cache.json`) con timestamps y ETag |
| **Dependencias** | Entrante: `core/services/format_service.py`. Saliente: filesystem (`data/gicatesis_cache.json`) |
| **Criticidad** | Importante |
| **Riesgos** | Cache corrupto puede causar datos stale; se puede eliminar para forzar resync |
| **Recomendacion** | Mantener |

---

## `/app/modules`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Modulos de entrada/salida: API REST y UI web. |
| **Responsabilidades** | - `api/`: Endpoints REST<br>- `ui/`: Renderizado de paginas HTML |
| **Dependencias** | Entrante: `main.py`. Saliente: `core/services/`, `core/config.py` |
| **Criticidad** | Critica |
| **Riesgos** | Ninguno - bien separado |
| **Recomendacion** | Mantener |

---

## `/app/modules/api`

| Atributo | Valor |
|----------|-------|
| **Proposito** | API REST con endpoints BFF para formatos, prompts, proyectos, n8n y simulacion. |
| **Responsabilidades** | - `router.py`: Todos los endpoints API (730 lineas)<br>- `models.py`: 5 modelos Pydantic de request (PromptIn, ProjectDraftIn, ProjectUpdateIn, ProjectGenerateIn, N8NCallbackIn) |
| **Dependencias** | Entrante: `main.py`. Saliente: todos los servicios en `core/services/`, `integrations/` |
| **Criticidad** | Critica |
| **Riesgos** | `router.py` instancia servicios como singletons globales |
| **Recomendacion** | Reestructurar - Usar Depends() de FastAPI para inyeccion |

---

## `/app/modules/ui`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Renderizado de la interfaz web (SPA servida desde Jinja). |
| **Responsabilidades** | - `router.py`: Endpoint GET `/` que renderiza `app.html` |
| **Dependencias** | Entrante: `main.py`. Saliente: `core/templates.py`, `core/config.py` |
| **Criticidad** | Importante |
| **Riesgos** | Ninguno |
| **Recomendacion** | Mantener |

---

## `/app/static`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Assets estaticos servidos por FastAPI. |
| **Responsabilidades** | - `js/app.js`: Frontend SPA completo (898 lineas) |
| **Dependencias** | Entrante: Browser. Saliente: API endpoints `/api/*` |
| **Criticidad** | Critica |
| **Riesgos** | Todo el frontend en un solo archivo (dificil de mantener a largo plazo) |
| **Recomendacion** | Mantener para MVP, considerar modularizar si crece |

---

## `/app/templates`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Templates HTML Jinja2. |
| **Responsabilidades** | - `base.html`: Layout base (31 lineas)<br>- `pages/app.html`: Pagina principal con todo el HTML del wizard (433 lineas) |
| **Dependencias** | Entrante: `ui/router.py`. Saliente: ninguna |
| **Criticidad** | Importante |
| **Riesgos** | Ninguno |
| **Recomendacion** | Mantener |

---

## `/data`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Persistencia de datos en formato JSON (demo/MVP). |
| **Responsabilidades** | - `formats_sample.json`: Formatos institucionales de ejemplo (fallback demo)<br>- `prompts.json`: Prompts guardados<br>- `projects.json`: Historial de proyectos generados<br>- `gicatesis_cache.json`: Cache de formatos sincronizados desde GicaTesis |
| **Dependencias** | Entrante: `JsonStore`, `FormatService`, `FormatCache`. Saliente: ninguna |
| **Criticidad** | Importante |
| **Riesgos** | Sin backup, sin validacion de schema |
| **Recomendacion** | Mantener para MVP, migrar a BD si escala |

---

## `/docs`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Documentacion tecnica y operativa del proyecto. |
| **Responsabilidades** | - Indice navegable<br>- Arquitectura y catalogos<br>- ADRs<br>- Runbooks |
| **Dependencias** | Ninguna |
| **Criticidad** | Opcional (no afecta ejecucion) |
| **Riesgos** | Ninguno |
| **Recomendacion** | Mantener y actualizar |

---

## `/scripts`

| Atributo | Valor |
|----------|-------|
| **Proposito** | Scripts de utilidad para mantenimiento del repositorio. |
| **Responsabilidades** | - `check_encoding.py`: Verifica encoding UTF-8 de archivos<br>- `check_mojibake.py`: Detecta caracteres mojibake<br>- `fix_encoding.py`: Corrige problemas de encoding automaticamente |
| **Dependencias** | Entrante: desarrolladores (ejecucion manual). Saliente: archivos del repositorio |
| **Criticidad** | Opcional |
| **Riesgos** | Ninguno |
| **Recomendacion** | Mantener - ejecutar antes de cada commit |

---

## Resumen de Criticidades

| Nivel | Carpetas |
|-------|----------|
| Critica | `/app`, `/app/core`, `/app/core/services`, `/app/modules`, `/app/modules/api`, `/app/static`, `/app/integrations`, `/app/integrations/gicatesis` |
| Importante | `/app/core/storage`, `/app/modules/ui`, `/app/templates`, `/data`, `/app/integrations/gicatesis/cache` |
| Opcional | `/app/core/utils`, `/app/core/clients`, `/docs`, `/scripts` |

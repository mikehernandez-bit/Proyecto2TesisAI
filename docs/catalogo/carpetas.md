# Catálogo de Carpetas - GicaGen

> Inventario completo de carpetas del repositorio con propósito, responsabilidades, criticidad y recomendaciones.

---

## `/` (Raíz)

| Atributo | Valor |
|----------|-------|
| **Propósito** | Raíz del proyecto. Contiene configuración, documentación raíz y punto de entrada. |
| **Responsabilidades** | - Archivos de configuración (requirements.txt, .env.example)<br>- Documentación (README.md, AGENTS.md)<br>- Directorio principal de código (app/) |
| **Dependencias** | Entrante: ninguna. Saliente: app/, data/, docs/ |
| **Criticidad** | 🔴 Crítica |
| **Riesgos** | Ninguno identificado |
| **Recomendación** | ✅ Mantener |

---

## `/app`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Código fuente principal de la aplicación FastAPI. |
| **Responsabilidades** | - Entrypoint (`main.py`)<br>- Configuración y core (`core/`)<br>- Módulos API y UI (`modules/`)<br>- Assets estáticos y templates |
| **Dependencias** | Entrante: `main.py` ejecutado por uvicorn. Saliente: `data/` para persistencia JSON |
| **Criticidad** | 🔴 Crítica |
| **Riesgos** | Ninguno - estructura clara |
| **Recomendación** | ✅ Mantener |

---

## `/app/core`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Lógica de negocio central: configuración, servicios, storage, utilidades. |
| **Responsabilidades** | - `config.py`: Settings desde env vars<br>- `templates.py`: Configuración Jinja2<br>- `services/`: Servicios de negocio<br>- `storage/`: Persistencia JSON<br>- `utils/`: Generador de IDs |
| **Dependencias** | Entrante: `app/modules/`. Saliente: `data/` (archivos JSON) |
| **Criticidad** | 🔴 Crítica |
| **Riesgos** | ⚠️ Los servicios dependen directamente de `JsonStore` (acoplamiento a infraestructura) |
| **Recomendación** | ⚡ Reestructurar - Separar interfaces de implementaciones |

---

## `/app/core/services`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Servicios de negocio que implementan la lógica principal. |
| **Responsabilidades** | - `format_api.py`: Obtiene formatos institucionales (API externa o sample)<br>- `prompt_service.py`: CRUD de prompts<br>- `project_service.py`: CRUD de proyectos/historial<br>- `docx_builder.py`: Genera DOCX demo<br>- `n8n_client.py`: Cliente para webhook n8n |
| **Dependencias** | Entrante: `app/modules/api/router.py`. Saliente: `storage/`, `config.py`, `utils/`, librerías externas (httpx, python-docx) |
| **Criticidad** | 🔴 Crítica |
| **Riesgos** | ⚠️ `format_api.py` mezcla lógica HTTP con fallback a archivo local<br>⚠️ Servicios instanciados directamente en router (no inyección) |
| **Recomendación** | ⚡ Reestructurar - Aplicar inyección de dependencias, separar ports/adapters |

---

## `/app/core/storage`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Capa de persistencia simple basada en archivos JSON. |
| **Responsabilidades** | - `json_store.py`: Lectura/escritura de listas JSON con locks |
| **Dependencias** | Entrante: `ProjectService`, `PromptService`. Saliente: filesystem (`data/`) |
| **Criticidad** | 🟡 Importante |
| **Riesgos** | ⚠️ No escalable para producción (concurrencia limitada, sin transacciones) |
| **Recomendación** | ✅ Mantener para MVP, documentar como adapter reemplazable |

---

## `/app/core/utils`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Utilidades genéricas reutilizables. |
| **Responsabilidades** | - `id.py`: Generador de IDs con prefijo (ej: `proj_abc123`) |
| **Dependencias** | Entrante: `ProjectService`, `PromptService`. Saliente: ninguna |
| **Criticidad** | 🟢 Opcional |
| **Riesgos** | Ninguno |
| **Recomendación** | ✅ Mantener |

---

## `/app/modules`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Módulos de entrada/salida: API REST y UI web. |
| **Responsabilidades** | - `api/`: Endpoints REST<br>- `ui/`: Renderizado de páginas HTML |
| **Dependencias** | Entrante: `main.py`. Saliente: `core/services/`, `core/config.py` |
| **Criticidad** | 🔴 Crítica |
| **Riesgos** | Ninguno - bien separado |
| **Recomendación** | ✅ Mantener |

---

## `/app/modules/api`

| Atributo | Valor |
|----------|-------|
| **Propósito** | API REST con endpoints para formatos, prompts, proyectos y callbacks n8n. |
| **Responsabilidades** | - `router.py`: Todos los endpoints API<br>- `models.py`: Modelos Pydantic de request |
| **Dependencias** | Entrante: `main.py`. Saliente: todos los servicios en `core/services/` |
| **Criticidad** | 🔴 Crítica |
| **Riesgos** | ⚠️ `router.py` instancia servicios como singletons globales |
| **Recomendación** | ⚡ Reestructurar - Usar Depends() de FastAPI para inyección |

---

## `/app/modules/ui`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Renderizado de la interfaz web (SPA servida desde Jinja). |
| **Responsabilidades** | - `router.py`: Endpoint GET `/` que renderiza `app.html` |
| **Dependencias** | Entrante: `main.py`. Saliente: `core/templates.py`, `core/config.py` |
| **Criticidad** | 🟡 Importante |
| **Riesgos** | Ninguno |
| **Recomendación** | ✅ Mantener |

---

## `/app/static`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Assets estáticos servidos por FastAPI. |
| **Responsabilidades** | - `js/app.js`: Frontend SPA completo (563 líneas) |
| **Dependencias** | Entrante: Browser. Saliente: API endpoints `/api/*` |
| **Criticidad** | 🔴 Crítica |
| **Riesgos** | ⚠️ Todo el frontend en un solo archivo (difícil de mantener a largo plazo) |
| **Recomendación** | ✅ Mantener para MVP, considerar modularizar si crece |

---

## `/app/templates`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Templates HTML Jinja2. |
| **Responsabilidades** | - `base.html`: Layout base<br>- `pages/app.html`: Página principal con todo el HTML del wizard |
| **Dependencias** | Entrante: `ui/router.py`. Saliente: ninguna |
| **Criticidad** | 🟡 Importante |
| **Riesgos** | Ninguno |
| **Recomendación** | ✅ Mantener |

---

## `/data`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Persistencia de datos en formato JSON (demo/MVP). |
| **Responsabilidades** | - `formats_sample.json`: Formatos institucionales de ejemplo<br>- `prompts.json`: Prompts guardados<br>- `projects.json`: Historial de proyectos generados |
| **Dependencias** | Entrante: `JsonStore`, `FormatService`. Saliente: ninguna |
| **Criticidad** | 🟡 Importante |
| **Riesgos** | ⚠️ Sin backup, sin validación de schema |
| **Recomendación** | ✅ Mantener para MVP, migrar a BD si escala |

---

## `/docs`

| Atributo | Valor |
|----------|-------|
| **Propósito** | Documentación técnica y operativa del proyecto. |
| **Responsabilidades** | - Índice navegable<br>- Arquitectura y catálogos<br>- ADRs<br>- Runbooks |
| **Dependencias** | Ninguna |
| **Criticidad** | 🟢 Opcional (no afecta ejecución) |
| **Riesgos** | Ninguno |
| **Recomendación** | ✅ Mantener y actualizar |

---

## Resumen de Criticidades

| Nivel | Carpetas |
|-------|----------|
| 🔴 Crítica | `/app`, `/app/core`, `/app/core/services`, `/app/modules`, `/app/modules/api`, `/app/static` |
| 🟡 Importante | `/app/core/storage`, `/app/modules/ui`, `/app/templates`, `/data` |
| 🟢 Opcional | `/app/core/utils`, `/docs` |

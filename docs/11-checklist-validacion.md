# Checklist de Validacion

> Verificaciones para asegurar que el sistema funciona correctamente.

---

## 1. Levantar Local

| # | Check | Comando/Accion | Resultado Esperado |
|---|-------|----------------|-------------------|
| 1.1 | Python instalado | `python --version` | 3.10-3.13 |
| 1.2 | Venv creado | `.venv\Scripts\activate` | Prompt cambia |
| 1.3 | Deps instaladas | `pip list \| grep fastapi` | fastapi 0.115.6 |
| 1.4 | Servidor inicia | `uvicorn app.main:app --port 8001` | Sin errores |
| 1.5 | Health check | `Invoke-RestMethod http://127.0.0.1:8001/healthz` | `{"ok":true}` |
| 1.6 | UI carga | Abrir http://127.0.0.1:8001/ | Sidebar visible |
| 1.7 | Build info | `Invoke-RestMethod http://127.0.0.1:8001/api/_meta/build` | cwd correcto |

---

## 2. Build (N/A para MVP)

El proyecto no requiere paso de build. Validar en produccion con Docker o deploy directo.

---

## 3. Tests (Pendiente)

> [!WARNING]
> No hay tests automatizados implementados actualmente.

**Tests manuales:**

| # | Check | Accion | Resultado Esperado |
|---|-------|--------|-------------------|
| 3.1 | Listar prompts | `GET /api/prompts` | Array de prompts |
| 3.2 | Crear prompt | `POST /api/prompts` | Retorna nuevo prompt |
| 3.3 | Listar formatos | `GET /api/formats` | Objeto con `formats` array |
| 3.4 | Detalle formato | `GET /api/formats/{id}` | FormatDetail con definition |
| 3.5 | Version catalogo | `GET /api/formats/version` | current, cached, changed |
| 3.6 | Crear draft | `POST /api/projects/draft` | Retorna proyecto `draft` |
| 3.7 | Spec n8n | `GET /api/integrations/n8n/spec?projectId=...` | Spec completo |
| 3.8 | Simulacion | `POST /api/sim/n8n/run?projectId=...` | runId, aiResult, artifacts |
| 3.9 | Descarga DOCX | `GET /api/sim/download/docx?projectId=...` | Archivo .docx |
| 3.10 | Descarga PDF | `GET /api/sim/download/pdf?projectId=...` | Archivo .pdf |

---

## 4. Verificacion de Boundaries (Imports)

| # | Check | Comando | Resultado Esperado |
|---|-------|---------|-------------------|
| 4.1 | Core no importa adapters | `grep -r "from app.adapters" app/core/` | Sin resultados |
| 4.2 | Servicios usan interfaces | Revisar `prompt_service.py` | IDataStore inyectado |

> [!NOTE]
> Estos checks aplican despues de implementar el plan de desacoplo.

---

## 5. Verificacion de Integracion GicaTesis

| # | Check | Accion | Resultado Esperado |
|---|-------|--------|-------------------|
| 5.1 | GicaTesis accesible | `Invoke-RestMethod http://127.0.0.1:8000/healthz` | `{"ok":true}` |
| 5.2 | Formatos via BFF | `GET /api/formats` (con GicaTesis activo) | Formatos reales, `stale: false` |
| 5.3 | Cache funciona | `GET /api/formats` (tras primer call) | Usa cache local |
| 5.4 | Fallback sin GicaTesis | `GET /api/formats` (sin GicaTesis) | Usa cache stale o demo |
| 5.5 | Assets proxied | `GET /api/assets/{path}` | Imagen/logo de GicaTesis |

---

## 6. Flujos E2E

### Wizard Completo

| # | Paso | Accion | Resultado |
|---|------|--------|-----------|
| 6.1 | Dashboard | Abrir http://127.0.0.1:8001/ | Ver panel principal |
| 6.2 | Nuevo proyecto | Click "Nuevo Proyecto" | Ver paso 1 |
| 6.3 | Seleccionar formato | Click en tarjeta | Boton "Siguiente" activo |
| 6.4 | Seleccionar prompt | Click en tarjeta | Boton "Siguiente" activo |
| 6.5 | Llenar variables | Ingresar datos | Form completado |
| 6.6 | Guia n8n | Click "Ir a guia" | Ver secciones A-H |
| 6.7 | Simulacion | Click "Simular ejecucion n8n" | Estado simulated |
| 6.8 | Paso 5 | Continuar a descargas | Ver opciones DOCX/PDF |
| 6.9 | Descargar DOCX | Click "Descargar DOCX" | Descarga .docx |
| 6.10 | Descargar PDF | Click "Descargar PDF" | Descarga .pdf |

### CRUD Prompts

| # | Accion | Resultado |
|---|--------|-----------|
| 6.11 | Crear prompt | Prompt aparece en lista |
| 6.12 | Editar prompt | Cambios persisten |
| 6.13 | Eliminar prompt | Prompt desaparece |

---

## 7. Verificacion de Archivos

```powershell
if (Test-Path app/main.py) { "OK main.py" }
if (Test-Path app/core/config.py) { "OK config.py" }
if (Test-Path app/integrations/gicatesis/client.py) { "OK gicatesis client" }
if (Test-Path data) { "OK data/" }
if (Test-Path data/prompts.json) { "OK prompts.json" }
if (Test-Path data/projects.json) { "OK projects.json" }
```

---

## 8. Verificacion de Encoding

```powershell
python scripts/check_encoding.py
python scripts/check_mojibake.py
```

---

## Resultado

| Seccion | Checks | Estado |
|---------|--------|--------|
| Levantar local | 7 | - |
| Tests manuales | 10 | - |
| Boundaries | 2 | - |
| Integracion GicaTesis | 5 | - |
| Flujos E2E | 13 | - |
| Archivos | 6 | - |
| Encoding | 2 | - |

**Total: /45**

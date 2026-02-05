# Checklist de Validación

> Verificaciones para asegurar que el sistema funciona correctamente.

---

## 1. Levantar Local

| # | Check | Comando/Acción | Resultado Esperado | ✓ |
|---|-------|----------------|-------------------|---|
| 1.1 | Python instalado | `python --version` | 3.10-3.13 | ☐ |
| 1.2 | Venv creado | `.venv\Scripts\activate` | Prompt cambia | ☐ |
| 1.3 | Deps instaladas | `pip list \| grep fastapi` | fastapi 0.115.6 | ☐ |
| 1.4 | Servidor inicia | `uvicorn app.main:app` | Sin errores | ☐ |
| 1.5 | Health check | `curl /healthz` | `{"ok":true}` | ☐ |
| 1.6 | UI carga | Abrir browser | Sidebar visible | ☐ |

---

## 2. Build (N/A para MVP)

El proyecto no requiere paso de build. Validar en producción con Docker o deploy directo.

---

## 3. Tests (Pendiente)

> [!WARNING]
> No hay tests automatizados implementados actualmente.

**Tests manuales:**

| # | Check | Acción | Resultado Esperado | ✓ |
|---|-------|--------|-------------------|---|
| 3.1 | Listar prompts | `GET /api/prompts` | Array de prompts | ☐ |
| 3.2 | Crear prompt | `POST /api/prompts` | Retorna nuevo prompt | ☐ |
| 3.3 | Listar formatos | `GET /api/formats` | Array de formatos | ☐ |
| 3.4 | Generar proyecto | `POST /api/projects/generate` | Retorna proyecto | ☐ |
| 3.5 | Descargar DOCX | `GET /api/download/{id}` | Archivo .docx | ☐ |

---

## 4. Verificación de Boundaries (Imports)

| # | Check | Comando | Resultado Esperado | ✓ |
|---|-------|---------|-------------------|---|
| 4.1 | Core no importa adapters | `grep -r "from app.adapters" app/core/` | Sin resultados | ☐ |
| 4.2 | Servicios usan interfaces | Revisar `prompt_service.py` | IDataStore inyectado | ☐ |

> [!NOTE]
> Estos checks aplican después de implementar el plan de desacoplo.

---

## 5. Verificación de Integración GicaTesis

| # | Check | Acción | Resultado Esperado | ✓ |
|---|-------|--------|-------------------|---|
| 5.1 | Sin integración (actual) | Verificar sin `GICATESIS_*` | Usa formatos locales | ☐ |
| 5.2 | Fallback funciona | API GicaTesis no disponible | Usa `formats_sample.json` | ☐ |

---

## 6. Flujos E2E

### Wizard Completo

| # | Paso | Acción | Resultado | ✓ |
|---|------|--------|-----------|---|
| 6.1 | Dashboard | Abrir / | Ver panel principal | ☐ |
| 6.2 | Nuevo proyecto | Click "Nuevo Proyecto" | Ver paso 1 | ☐ |
| 6.3 | Seleccionar formato | Click en tarjeta | Botón "Siguiente" activo | ☐ |
| 6.4 | Seleccionar prompt | Click en tarjeta | Botón "Siguiente" activo | ☐ |
| 6.5 | Llenar variables | Ingresar datos | Form completado | ☐ |
| 6.6 | Generar | Click "Generar" | Spinner + éxito | ☐ |
| 6.7 | Descargar | Click "Descargar" | Descarga .docx | ☐ |

### CRUD Prompts

| # | Acción | Resultado | ✓ |
|---|--------|-----------|---|
| 6.8 | Crear prompt | Prompt aparece en lista | ☐ |
| 6.9 | Editar prompt | Cambios persisten | ☐ |
| 6.10 | Eliminar prompt | Prompt desaparece | ☐ |

---

## 7. Verificación de Archivos

```bash
# Verificar estructura mínima
[ -f app/main.py ] && echo "✓ main.py"
[ -f app/core/config.py ] && echo "✓ config.py"
[ -d data ] && echo "✓ data/"
[ -f data/prompts.json ] && echo "✓ prompts.json"
[ -f data/projects.json ] && echo "✓ projects.json"
```

---

## Resultado

| Sección | Checks | Pasados | Estado |
|---------|--------|---------|--------|
| Levantar local | 6 | ☐/6 | - |
| Tests manuales | 5 | ☐/5 | - |
| Boundaries | 2 | ☐/2 | - |
| Integración | 2 | ☐/2 | - |
| Flujos E2E | 10 | ☐/10 | - |

**Total: ☐/25**

# Plan de Cambios - Desacoplo

> Plan para mejorar la arquitectura de GicaGen siguiendo principios de ports/adapters.

## Estado

**Parcialmente Implementado** - La integracion GicaTesis fue completada con patron BFF en `integrations/gicatesis/`.

## Resumen de Problemas

| # | Problema | Archivo | Estado |
|---|----------|---------|--------|
| 1 | Servicios instanciados como globals | `app/modules/api/router.py` | Pendiente |
| 2 | PromptService importa JsonStore directamente | `app/core/services/prompt_service.py` | Pendiente |
| 3 | ProjectService importa JsonStore directamente | `app/core/services/project_service.py` | Pendiente |
| 4 | FormatService mezcla HTTP + fallback local | `format_service.py` + `integrations/gicatesis/` | **Implementado** |
| 5 | DocxBuilder usa python-docx directamente | `app/core/services/docx_builder.py` | Pendiente |
| 6 | N8NClient en core (deberia ser adapter) | `app/core/services/n8n_client.py` | Pendiente |

## Cambios Propuestos

### Fase 1: Inyeccion de dependencias (Bajo riesgo)

**Archivo a modificar:** `app/modules/api/router.py`

**Cambio:** Reemplazar instancias globales por `Depends()`

```python
# ANTES (lineas actuales del router)
formats = FormatService()
prompts = PromptService()
projects = ProjectService()
n8n = N8NClient()
n8n_specs = N8NIntegrationService()

# DESPUES
def get_format_service():
    return FormatService()

def get_prompt_service():
    return PromptService()

@router.get("/formats")
async def list_formats(
    formats: FormatService = Depends(get_format_service),
    ...
):
```

**Validacion:**
```powershell
python -m uvicorn app.main:app --port 8001 --reload
Invoke-RestMethod http://127.0.0.1:8001/api/formats
Invoke-RestMethod http://127.0.0.1:8001/api/prompts
```

---

### Fase 2: Crear interfaces (Riesgo medio)

**Archivos nuevos:**
- `app/core/ports/__init__.py`
- `app/core/ports/data_store.py`
- `app/core/ports/document_generator.py`
- `app/core/ports/format_provider.py`
- `app/core/ports/workflow_engine.py`

**Ejemplo `data_store.py`:**
```python
from typing import Protocol, List, Dict, Any

class IDataStore(Protocol):
    def read_list(self) -> List[Dict[str, Any]]: ...
    def write_list(self, items: List[Dict[str, Any]]) -> None: ...
```

---

### Fase 3: Mover a adapters (Riesgo medio)

**Reestructura:**
```
app/
+-- adapters/           # NUEVO
|   +-- __init__.py
|   +-- storage/
|   |   `-- json_store_adapter.py  # Mover de core/storage/
|   +-- documents/
|   |   `-- docx_adapter.py        # Mover de core/services/docx_builder.py
|   `-- workflows/
|       `-- n8n_adapter.py         # Mover de core/services/n8n_client.py
```

---

## Orden de Ejecucion

1. Fase 1: Inyeccion con Depends() - **Hacer primero**
2. Fase 2: Crear interfaces en `core/ports/`
3. Fase 3: Mover codigo a `adapters/`
4. Fase 4: Actualizar servicios para usar interfaces

## Checklist de Validacion Post-Cambios

- [ ] `python -m uvicorn app.main:app --port 8001` inicia sin errores
- [ ] `GET /healthz` retorna `{"ok": true}`
- [ ] Wizard completo funciona (pasos 1-5)
- [ ] CRUD prompts funciona
- [ ] Simulacion n8n funciona
- [ ] Descarga de DOCX/PDF funciona

## Referencias

- Ver arquitectura objetivo en [02-arquitectura.md](02-arquitectura.md#b-arquitectura-objetivo-propuesta)
- ADR relacionado: [ADR-0002-boundaries-desacoplo.md](adrs/ADR-0002-boundaries-desacoplo.md)

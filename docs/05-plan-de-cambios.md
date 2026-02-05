# Plan de Cambios - Desacoplo

> Plan para mejorar la arquitectura de GicaGen siguiendo principios de ports/adapters.

## Estado

**Propuesto** - Pendiente de implementación

## Resumen de Problemas

| # | Problema | Archivo | Líneas |
|---|----------|---------|--------|
| 1 | Servicios instanciados como globals | `app/modules/api/router.py` | 19-22 |
| 2 | PromptService importa JsonStore directamente | `app/core/services/prompt_service.py` | 4 |
| 3 | ProjectService importa JsonStore directamente | `app/core/services/project_service.py` | 7 |
| 4 | FormatService mezcla HTTP + fallback local | `app/core/services/format_api.py` | 22-49 |
| 5 | DocxBuilder usa python-docx directamente | `app/core/services/docx_builder.py` | 5 |
| 6 | N8NClient en core (debería ser adapter) | `app/core/services/n8n_client.py` | 1-20 |

## Cambios Propuestos

### Fase 1: Inyección de dependencias (Bajo riesgo)

**Archivo a modificar:** `app/modules/api/router.py`

**Cambio:** Reemplazar instancias globales por `Depends()`

```python
# ANTES (líneas 19-22)
formats = FormatService()
prompts = PromptService()
projects = ProjectService()
n8n = N8NClient()

# DESPUÉS
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

**Validación:**
```bash
python -m uvicorn app.main:app --reload
curl http://localhost:8000/api/formats
curl http://localhost:8000/api/prompts
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
├── adapters/           # NUEVO
│   ├── __init__.py
│   ├── storage/
│   │   └── json_store_adapter.py  # Mover de core/storage/
│   ├── documents/
│   │   └── docx_adapter.py        # Mover de core/services/docx_builder.py
│   ├── formats/
│   │   └── external_adapter.py    # Mover de core/services/format_api.py
│   └── workflows/
│       └── n8n_adapter.py         # Mover de core/services/n8n_client.py
```

---

## Orden de Ejecución

1. ✅ Fase 1: Inyección con Depends() - **Hacer primero**
2. Fase 2: Crear interfaces en `core/ports/`
3. Fase 3: Mover código a `adapters/`
4. Fase 4: Actualizar servicios para usar interfaces

## Checklist de Validación Post-Cambios

- [ ] `python -m uvicorn app.main:app` inicia sin errores
- [ ] `GET /healthz` retorna `{"ok": true}`
- [ ] Wizard completo funciona
- [ ] CRUD prompts funciona
- [ ] Descarga de DOCX funciona

## Referencias

- Ver arquitectura objetivo en [02-arquitectura.md](02-arquitectura.md#b-arquitectura-objetivo-propuesta)
- ADR relacionado: [ADR-0002-boundaries-desacoplo.md](adrs/ADR-0002-boundaries-desacoplo.md)

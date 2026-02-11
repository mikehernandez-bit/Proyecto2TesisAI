# ADR-0002: Boundaries y Desacoplo

## Estado

Propuesto

## Contexto

Durante el análisis del proyecto se identificaron acoplamientos que dificultan:
- Testing unitario
- Reemplazo de componentes
- Mantenibilidad a largo plazo

### Problemas Detectados

1. **Servicios como globals** en `api/router.py` (líneas 19-22)
2. **Core depende de infraestructura**: `PromptService` y `ProjectService` importan `JsonStore` directamente
3. **Adapters mezclados en core**: `format_api.py`, `n8n_client.py`, `docx_builder.py` contienen lógica de integración

## Decisión

### Adoptar Arquitectura Ports & Adapters

```
core/
+-- services/       # Lógica de negocio
`-- ports/          # Interfaces (Protocols)
adapters/           # Implementaciones concretas
infra/              # Config, utils técnicos
```

### Reglas de Dependencia

1. **Core no importa adapters/infra**
2. **Adapters implementan ports** (interfaces definidas en core)
3. **Composition root** (`main.py`) hace el wiring
4. **Inyección de dependencias** via FastAPI `Depends()`

### Ejemplo de Transformación

**Antes:**
```python
# prompt_service.py
from app.core.storage.json_store import JsonStore  # ❌ Import directo

class PromptService:
    def __init__(self):
        self.store = JsonStore("data/prompts.json")  # ❌ Hardcoded
```

**Después:**
```python
# core/ports/data_store.py
class IDataStore(Protocol):
    def read_list(self) -> List[Dict]: ...

# core/services/prompt_service.py
class PromptService:
    def __init__(self, store: IDataStore):  # ✅ Inyección
        self.store = store
```

## Consecuencias

### Positivas
- Servicios testeables con mocks
- Adapters reemplazables (ej: JSON → PostgreSQL)
- Integración con GicaTesis encapsulada en adapter
- Código más limpio y mantenible

### Negativas
- Más archivos/carpetas
- Curva de aprendizaje para el equipo
- Requiere refactoring del código existente

### Plan de Migración

Ver [02-arquitectura.md](../02-arquitectura.md#d-plan-de-desacoplo) para el plan detallado.

## Referencias

- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)

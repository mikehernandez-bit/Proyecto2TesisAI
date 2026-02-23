# ADR-0002: Boundaries y Desacoplo

## Estado

**Parcialmente Implementado**

- La integracion con GicaTesis fue implementada en `app/integrations/gicatesis/` con patron BFF.
- El desacoplo de servicios via ports/adapters sigue pendiente.

## Contexto

GicaGen presento acoplamiento entre core y servicios de infraestructura:

1. Servicios instanciados como globals en `api/router.py`
2. `PromptService` y `ProjectService` importan `JsonStore` directamente
3. `DocxBuilder` y `N8NClient` mezclan logica de negocio con librerias especificas
4. El acceso a formatos externos estaba acoplado al core

## Decision

Adoptar arquitectura Ports & Adapters:

### Estructura Propuesta

```
app/
+-- core/
|   +-- ports/              # Interfaces (Protocol)
|   |   +-- data_store.py   # IDataStore
|   |   +-- doc_gen.py      # IDocumentGenerator
|   |   +-- format_prov.py  # IFormatProvider
|   |   `-- workflow.py     # IWorkflowEngine
|   `-- services/            # Solo dependen de ports
+-- adapters/                # Implementaciones concretas
|   +-- storage/json_store_adapter.py
|   +-- documents/docx_adapter.py
|   `-- workflows/n8n_adapter.py
+-- integrations/            # IMPLEMENTADO - GicaTesis BFF
|   `-- gicatesis/
```

### Reglas de Dependencia

1. `core/services/` solo importa de `core/ports/`
2. `adapters/` implementa `core/ports/`
3. `main.py` hace el wiring (composition root)
4. `integrations/` puede ser usado por services directamente (BFF)

## Que se Implemento

- `app/integrations/gicatesis/client.py` - Cliente HTTP async
- `app/integrations/gicatesis/types.py` - DTOs tipados
- `app/integrations/gicatesis/errors.py` - Excepciones custom
- `app/integrations/gicatesis/cache/` - Cache ETag
- `app/core/services/format_service.py` orquesta la integracion

## Que Falta

1. Crear `core/ports/` con interfaces Protocol
2. Migrar `json_store.py` a `adapters/storage/`
3. Migrar `docx_builder.py` a `adapters/documents/`
4. Migrar `n8n_client.py` a `adapters/workflows/`
5. Usar `Depends()` en `api/router.py` para inyeccion

## Consecuencias

**Positivas:**
- Testing simplificado (mocks via interfaces)
- Servicios reemplazables (BD en vez de JSON, otro engine en vez de n8n)
- Boundaries claros

**Negativas:**
- Mas archivos y carpetas
- Complejidad adicional para MVP

## Ver Tambien

- [02-arquitectura.md](../02-arquitectura.md) - Arquitectura actual completa
- [05-plan-de-cambios.md](../05-plan-de-cambios.md) - Plan de ejecucion

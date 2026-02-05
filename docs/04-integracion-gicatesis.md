# Integración GicaTesis - Guía Rápida

## Resumen

GicaGen ahora se integra con la **Formats API v1** de GicaTesis usando patrón BFF (Backend-For-Frontend).

## Arquitectura

```
┌─────────────────────────────────────────────────┐
│ Browser → GicaGen (:8001) → GicaTesis (:8000)   │
└─────────────────────────────────────────────────┘
```

**Principio:** El frontend de GicaGen NO llama directamente a GicaTesis. 
Todas las llamadas van a través de los endpoints BFF en `:8001`.

## Endpoints BFF

| Endpoint | Descripción |
|----------|-------------|
| `GET /api/formats/version` | Check de versión del catálogo |
| `GET /api/formats` | Lista formatos (con cache ETag) |
| `GET /api/formats/{id}` | Detalle de formato |

## Archivos Nuevos

```
app/integrations/gicatesis/
├── __init__.py
├── types.py          # DTOs: FormatSummary, FormatDetail, etc.
├── client.py         # HTTP client con ETag
├── errors.py         # Excepciones personalizadas
└── cache/
    ├── __init__.py
    └── format_cache.py  # Persistencia JSON
```

## Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `app/core/config.py` | Agregadas variables GICATESIS_* |
| `app/core/services/format_service.py` | Nuevo (reemplaza format_api.py) |
| `app/modules/api/router.py` | Endpoints BFF agregados |
| `app/main.py` | Logs de startup |
| `.env.example` | Variables de configuración |

## Configuración

**.env o variables de entorno:**

```bash
GICATESIS_BASE_URL=http://localhost:8000/api/v1
GICAGEN_PORT=8001
GICATESIS_TIMEOUT=8
```

## Cómo Correr

**Terminal 1 - GicaTesis:**
```bash
cd C:\Users\jhoan\Documents\gicateca_tesis
.venv\Scripts\activate
uvicorn app.main:app --port 8000 --reload
```

**Terminal 2 - GicaGen:**
```bash
cd C:\Users\jhoan\Documents\gicagen_tesis-main
.venv\Scripts\activate
uvicorn app.main:app --port 8001 --reload
```

## Cache

El cache se guarda en `data/gicatesis_cache.json`:
- Versión del catálogo
- ETag para requests 304
- Lista de formatos
- Detalles por ID
- Timestamp de última sincronización

**Comportamiento:**
- Primera llamada: Descarga todo el catálogo
- Llamadas siguientes: Usa ETag, si 304 → usa cache
- Si GicaTesis cae: Usa cache existente con flag `stale: true`

## Verificación

```powershell
# Health check
Invoke-RestMethod http://localhost:8001/healthz

# Version
Invoke-RestMethod http://localhost:8001/api/formats/version

# Lista
Invoke-RestMethod http://localhost:8001/api/formats

# Detalle
Invoke-RestMethod http://localhost:8001/api/formats/unac-informe-cual
```

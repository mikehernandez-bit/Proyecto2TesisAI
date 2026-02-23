# Troubleshooting

Esta guía cubre los fallos más frecuentes en la ruta code-first de GicaGen.

## 1) Gemini responde 429 (quota exceeded)

### Síntoma

`POST /api/projects/{id}/generate` devuelve `429 Too Many Requests`.

### Comportamiento esperado del sistema

- El endpoint devuelve 429 con mensaje claro.
- Se incluye `Retry-After` cuando el proveedor lo reporta.
- El proyecto queda en `failed`.
- `ai_result` se limpia (`null`).

### Remediación

1. Revisa cuota y billing del proyecto de Gemini.
2. Verifica que la key pertenezca al proyecto correcto.
3. Reintenta después de `Retry-After`.

## 2) "No Cloud Projects Available" en AI Studio

### Causa

No hay proyecto de Google Cloud importado en AI Studio.

### Solución

1. Crea o selecciona proyecto en Google Cloud.
2. En AI Studio abre **Dashboard -> Projects -> Import projects**.
3. Importa el proyecto y crea la key.
4. Configura `.env` local:

```dotenv
GEMINI_API_KEY="<YOUR_GEMINI_API_KEY>"
```

Referencia:
- https://ai.google.dev/gemini-api/docs/api-key

## 3) GicaTesis no disponible (upstream down)

### Síntoma

Rutas de render/proxy devuelven 503 con hint de conexión.

### Causa

`GICATESIS_BASE_URL` no responde o GicaTesis está apagado.

### Solución

1. Levanta GicaTesis en `:8000`.
2. Verifica `GICATESIS_BASE_URL`.
3. Reinicia GicaGen.
4. Para pruebas de catálogo sin upstream, usa `GICAGEN_DEMO_MODE=true`.

## 4) n8n devuelve 404

n8n es legacy/deprecated en esta migración. El flujo soportado es Gemini
code-first. Si n8n falla, no usarlo como ruta principal.

## 5) Tests no ejecutan

Ejecuta en este orden:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest tests -v
```

## 6) Errores de encoding

```powershell
.venv\Scripts\python scripts/check_encoding.py
.venv\Scripts\python scripts/check_mojibake.py
```

## Known gaps / TODO

- P1: migrar SDK de Gemini a `google.genai`.
- P1: agregar lint/typecheck.
- P1: automatizar E2E de wizard.
- P2: agregar CI con quality gates.

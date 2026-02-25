# Desarrollo local

Esta guía te deja el entorno listo para ejecutar GicaGen y validar generación
code-first con Gemini.

## Prerrequisitos

- Python 3.10 a 3.14.
- Entorno virtual local.
- Opcional: instancia local de GicaTesis para validaciones live.

## Setup de GicaGen

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --port 8001 --reload
```

Abre `http://127.0.0.1:8001/`.

## Variables críticas

| Variable | Requerida | Default | Notas |
|---|---|---|---|
| `GEMINI_API_KEY` | Sí (IA real) | `""` | Sin key no hay generación real |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Modelo actual |
| `GICATESIS_BASE_URL` | No | `http://localhost:8000/api/v1` | API de formatos/render |
| `GICAGEN_DEMO_MODE` | No | `false` | Fallback de catálogo demo |

## Runbook: GicaTesis local

Usa este runbook cuando necesites validar rutas que dependen de GicaTesis
(render DOCX/PDF o catálogo live).

1. Levanta GicaTesis con su comando oficial de ese repo.
2. Verifica que responda en su health endpoint (puerto 8000).
3. Revisa que `GICATESIS_BASE_URL` apunte a `http://localhost:8000/api/v1`.
4. Reinicia GicaGen.

Si usas estructura local estándar de ambos repos:

```powershell
# terminal GicaTesis (repo gicatesis)
python -m uvicorn app.main:app --port 8000 --reload

# terminal GicaGen (este repo)
python -m uvicorn app.main:app --port 8001 --reload
```

## Alternativa: DEMO MODE

Si no tienes GicaTesis disponible, puedes usar:

```dotenv
GICAGEN_DEMO_MODE="true"
```

Qué cubre:
- catálogo demo (`data/formats_sample.json`).

Qué no cubre:
- render real proxy DOCX/PDF de GicaTesis.

## Verificación rápida

```powershell
Invoke-RestMethod http://127.0.0.1:8001/healthz
Invoke-RestMethod http://127.0.0.1:8001/api/ai/health
Invoke-RestMethod http://127.0.0.1:8001/api/_meta/build
```

## Error común: "No Cloud Projects Available"

Si AI Studio no muestra proyectos:

1. Crea/selecciona proyecto en Google Cloud.
2. En AI Studio usa **Dashboard -> Projects -> Import projects**.
3. Crea la API key e incorpórala en `.env`.

Referencia:
- https://ai.google.dev/gemini-api/docs/api-key

# Desarrollo Local - GicaGen

> Actualizado: 2026-03-23

---

## Prerrequisitos

- **Python**: 3.10 — 3.14 (recomendado 3.12)
- **GicaTesis** corriendo en port 8000 (o usar `GICAGEN_DEMO_MODE=true`)
- **API Keys**: al menos una de Gemini, Mistral u OpenRouter

---

## Instalacion

```powershell
# 1. Clonar/navegar al repo
cd C:\Users\jhoan\Documents\gicagen_tesis-main

# 2. Crear entorno virtual
python -m venv .venv

# 3. Activar (Windows)
.venv\Scripts\activate

# 4. Instalar dependencias
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Para tests y lint

# 5. Copiar y editar config
copy .env.example .env
# Editar .env con API keys y URLs
```

---

## Variables de Entorno Minimas (.env)

```dotenv
GEMINI_API_KEY="tu-api-key-aqui"
GEMINI_MODEL="gemini-2.0-flash"
MISTRAL_API_KEY=""          # Opcional (fallback)
OPENROUTER_API_KEY=""       # Opcional (fallback)
AI_PRIMARY_PROVIDER="gemini"
AI_FALLBACK_ON_QUOTA="true"
GICATESIS_BASE_URL="http://localhost:8000/api/v1"
GICAGEN_PORT="8001"
GICAGEN_DEMO_MODE="false"   # true si no tienes GicaTesis
```

---

## Levantar el Sistema

```powershell
# 1. Levantar GicaTesis primero (port 8000)
# (desde el directorio gicateca_tesis)
python -m uvicorn app.main:app --port 8000 --reload

# 2. Levantar GicaGen (port 8001)
python -m uvicorn app.main:app --port 8001 --reload
```

**Abrir:** http://127.0.0.1:8001/

---

## Verificacion Basica

| Check | URL/Comando | Esperado |
|-------|------------|----------|
| App inicia | Terminal | `Uvicorn running on http://127.0.0.1:8001` |
| Health | `GET /healthz` | `{"ok": true}` |
| UI carga | http://127.0.0.1:8001/ | Wizard 5 pasos |
| Tests pasan | `pytest tests -q` | `passed` |

---

## Comandos de Desarrollo

```powershell
# Tests
python -m pytest tests -v
python -m pytest tests/test_prompt_flow.py -v

# Quality gate (como CI)
python scripts/quality_gate.py all
python scripts/quality_gate.py lint
python scripts/quality_gate.py typecheck

# Verificar encoding
python scripts/check_encoding.py
python scripts/check_mojibake.py
```

---

## Obtener API Key de Gemini

1. Ir a https://ai.google.dev/gemini-api/docs/api-key
2. Crear o seleccionar proyecto en Google Cloud
3. Generar API key en AI Studio
4. Guardar SOLO en `.env` local (nunca commitear)

```dotenv
GEMINI_API_KEY="tu-key-aqui"
```

---

## Si GicaTesis no esta disponible

Opciones:
1. **Demo mode**: `GICAGEN_DEMO_MODE=true` — usa `data/formats_sample.json`
2. **Cache**: si ya se cargo antes, usa `data/gicatesis_cache.json`
3. Las rutas de render/proxy devuelven `503` con mensaje de remediacion

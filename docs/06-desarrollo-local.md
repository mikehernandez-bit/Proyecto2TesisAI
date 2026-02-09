# Desarrollo Local

## Requisitos
- Python 3.10 a 3.13 recomendado
- Git
- GicaTesis disponible en `http://localhost:8000` para integracion completa

## Instalacion
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Variables de entorno
```env
APP_NAME=TesisAI Gen
APP_ENV=dev

GICATESIS_BASE_URL=http://localhost:8000/api/v1
GICAGEN_PORT=8001
GICAGEN_BASE_URL=http://localhost:8001
GICATESIS_TIMEOUT=8
GICAGEN_DEMO_MODE=false

N8N_WEBHOOK_URL=
N8N_SHARED_SECRET=
```

## Ejecutar local
```bash
python -m uvicorn app.main:app --port 8001 --reload
```

## Verificaciones rapidas
```powershell
Invoke-RestMethod http://127.0.0.1:8001/healthz
Invoke-RestMethod http://127.0.0.1:8001/api/_meta/build
Invoke-RestMethod http://127.0.0.1:8001/api/formats
Invoke-RestMethod http://127.0.0.1:8001/api/projects
```

## Flujo Wizard 1-5
1. Paso 1 selecciona formato desde `GET /api/formats`.
2. Paso 2 selecciona prompt desde `GET /api/prompts`.
3. Paso 3 crea o actualiza draft con `POST/PUT /api/projects`.
4. Paso 4 consume `GET /api/integrations/n8n/spec` y muestra guia de simulacion.
5. Paso 4 permite ejecutar `POST /api/sim/n8n/run` para obtener output simulado y artifacts.
6. Paso 5 descarga placeholders con `GET /api/sim/download/docx|pdf`.

## Endpoints principales
- `GET /api/formats/version`
- `GET /api/formats`
- `GET /api/formats/{id}`
- `POST /api/projects/draft`
- `GET /api/projects/{project_id}`
- `PUT /api/projects/{project_id}`
- `GET /api/integrations/n8n/spec`
- `POST /api/integrations/n8n/callback`
- `POST /api/sim/n8n/run`
- `GET /api/sim/download/docx`
- `GET /api/sim/download/pdf`
- `GET /api/_meta/build`

## Validar instancia activa
Si existe una instancia vieja en `:8001`, revisa:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/_meta/build
```

Debe apuntar al `cwd` correcto del repo actual.

## Reglas de encoding
- Guardar archivos en UTF-8.
- No usar caracteres de box drawing en docs o código.
- No usar emojis en documentación.
- Ejecutar `python scripts/check_encoding.py` antes de commit.
- Ejecutar `python scripts/check_mojibake.py` antes de commit.

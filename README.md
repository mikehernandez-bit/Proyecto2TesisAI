# TesisAI Gen

UI + backend base para un sistema tipo “wizard” (mockup modularizado y funcional).

## Ejecutar

Se recomienda utilizar **Python 3.12** (o versiones 3.10-3.13) para asegurar compatibilidad de librerías.

### 1. Configurar entorno
```bash
# Crear entorno virtual
python -m venv .venv

# Activar en Windows
.venv\Scripts\activate

# Activar en Mac/Linux
source .venv/bin/activate
```

### 2. Instalar y correr
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
Abrir: http://127.0.0.1:8000/

## Dónde conectar servicios reales
- Formatos (API externa): `app/core/services/format_api.py` + .env
- n8n: `app/core/services/n8n_client.py` + callback `/api/n8n/callback/{project_id}`

## Qué ya funciona
- Dashboard con lista y descargas
- Wizard 4 pasos con filtros, selección de formato/prompt, form dinámico y generación (demo)
- CRUD de prompts en Admin
- Historial con búsqueda

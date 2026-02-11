# Documentacion GicaGen

GicaGen es un generador de documentos academicos con wizard UI, BFF para formatos y guia de simulacion n8n.

## Inicio rapido
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8001 --reload
```

Abrir `http://127.0.0.1:8001/`.

## Navegacion
- Indice general: `docs/00-indice.md`
- Integracion y contrato n8n: `docs/04-integracion-gicatesis.md`
- Desarrollo local: `docs/06-desarrollo-local.md`
- Runbook local: `docs/runbooks/levantar-local.md`

## Flujo funcional actual
1. Paso 1: formatos via `GET /api/formats`.
2. Paso 2: prompts via `GET /api/prompts`.
3. Paso 3: borrador via `POST /api/projects/draft`.
4. Paso 4: guia simulada via `GET /api/integrations/n8n/spec`.
5. Paso 4: ejecucion simulada via `POST /api/sim/n8n/run`.
6. Paso 5: descargas simuladas via `GET /api/sim/download/docx|pdf`.

## Reglas de encoding
- Guardar archivos en UTF-8.
- No usar caracteres de box drawing en docs o codigo.
- No usar emojis en documentacion.
- Ejecutar `python scripts/check_mojibake.py` antes de commit.

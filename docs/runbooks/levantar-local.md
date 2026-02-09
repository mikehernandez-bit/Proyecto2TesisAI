# Runbook: Levantar Local

## Objetivo
Levantar GicaTesis y GicaGen, y validar el flujo de simulacion n8n end-to-end.

## 1) Levantar GicaTesis
```powershell
cd C:\Users\jhoan\Documents\gicateca_tesis
.venv\Scripts\activate
python -m uvicorn app.main:app --port 8000 --reload
```

Validar:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/api/v1/formats
```

## 2) Levantar GicaGen
```powershell
cd C:\Users\jhoan\Documents\gicagen_tesis-main
.venv\Scripts\activate
python -m uvicorn app.main:app --port 8001 --reload
```

Validar:
```powershell
Invoke-RestMethod http://127.0.0.1:8001/healthz
Invoke-RestMethod http://127.0.0.1:8001/api/_meta/build
```

## 3) Verificar OpenAPI
Debe exponer:
- `POST /api/projects/draft`
- `GET /api/integrations/n8n/spec`
- `POST /api/integrations/n8n/callback`
- `POST /api/sim/n8n/run`
- `GET /api/sim/download/docx`
- `GET /api/sim/download/pdf`
- `GET /api/_meta/build`

Comando:
```powershell
Invoke-RestMethod http://127.0.0.1:8001/openapi.json
```

## 4) Pruebas HTTP de flujo simulado
Crear draft:
```powershell
$draft = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/projects/draft" -ContentType "application/json" -Body '{"title":"QA draft","formatId":"demo-format","promptId":"prompt_tesis_estandar","values":{"tema":"QA"}}'
$projectId = $draft.projectId
$projectId
```

Obtener spec:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/integrations/n8n/spec?projectId=$projectId" | ConvertTo-Json -Depth 50
```

Ejecutar simulacion:
```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/sim/n8n/run?projectId=$projectId" | ConvertTo-Json -Depth 50
```

Descargar simulados:
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8001/api/sim/download/docx?projectId=$projectId" -OutFile ".\\simulated.docx"
Invoke-WebRequest -Uri "http://127.0.0.1:8001/api/sim/download/pdf?projectId=$projectId" -OutFile ".\\simulated.pdf"
```

## 5) Verificacion UI
1. Abrir `http://127.0.0.1:8001/`.
2. Completar wizard paso 1 a paso 3.
3. Click `Ir a guia n8n`.
4. Confirmar secciones A-F + G-H y paneles `formatDefinition`, `promptDetail`, `simulationOutput`.
5. Click `Simular ejecucion n8n` y confirmar estado `simulated`.
5. Continuar a paso 5 y descargar DOCX/PDF simulados.

## 6) Si hay instancia vieja en :8001
Revisar:
```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/_meta/build
```
Si el `cwd` no coincide con este repo, cerrar ese proceso antes de seguir.

## 7) Check de encoding antes de commit
```powershell
python scripts/check_encoding.py
python scripts/check_mojibake.py
```

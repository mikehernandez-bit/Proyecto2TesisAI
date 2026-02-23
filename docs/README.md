# GicaGen - Documentacion

> Entrada rapida a la documentacion tecnica de GicaGen.

## Que es GicaGen?

Sistema de generacion de documentos academicos con wizard guiado, integracion BFF con GicaTesis, y simulacion n8n.

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8001 --reload
```

Abrir: http://127.0.0.1:8001/

## Navegacion

| Documento | Proposito |
|-----------|-----------|
| [00-indice.md](00-indice.md) | Indice completo |
| [01-vision-y-alcance.md](01-vision-y-alcance.md) | Que es y que no es GicaGen |
| [02-arquitectura.md](02-arquitectura.md) | Componentes, flujos, diagramas |
| [04-integracion-gicatesis.md](04-integracion-gicatesis.md) | Endpoints BFF, contratos |
| [06-desarrollo-local.md](06-desarrollo-local.md) | Setup completo |
| [09-troubleshooting.md](09-troubleshooting.md) | Errores comunes |

## Flujo Funcional Actual

1. **Wizard paso 1:** Seleccionar formato academico (BFF -> GicaTesis API v1)
2. **Wizard paso 2:** Seleccionar prompt (template con variables)
3. **Wizard paso 3:** Llenar variables del documento
4. **Wizard paso 4:** Guia de integracion n8n + simulacion
5. **Wizard paso 5:** Descargar DOCX/PDF generados/simulados

## Encoding

- Todos los archivos deben usar **UTF-8**
- Ver [STYLE_GUIDE.md](STYLE_GUIDE.md)
- Pre-commit: `python scripts/check_encoding.py && python scripts/check_mojibake.py`

## Puertos

| Servicio | Puerto |
|----------|--------|
| GicaTesis | 8000 |
| GicaGen | 8001 |

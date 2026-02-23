# GicaGen

> **Entrada rapida para agentes:** Todo lo que necesitas saber esta en [`/docs/00-indice.md`](docs/00-indice.md)

## Que es GicaGen?

GicaGen es un sistema generador de documentos academicos (tesis, articulos) usando plantillas y flujos de IA. Es un proyecto **relacionado pero independiente** de GicaTesis.

## Ejecutar rapido

```powershell
# Python 3.10-3.13 recomendado
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8001 --reload
```

Abrir: http://127.0.0.1:8001/

> **Nota:** Puerto 8001 para GicaGen, 8000 para GicaTesis.

## Estructura del proyecto

```
app/
+-- main.py                      # Entrypoint FastAPI
+-- core/                        # Logica de negocio
|   +-- config.py                # Settings desde env vars
|   +-- templates.py             # Jinja2 config
|   +-- clients/                 # Cliente HTTP legacy
|   +-- services/                # 8 servicios: FormatService, PromptService,
|   |                            #   ProjectService, DocxBuilder, N8NClient,
|   |                            #   N8NIntegrationService, DefinitionCompiler,
|   |                            #   SimulationArtifactService
|   +-- storage/                 # JsonStore (persistencia JSON)
|   `-- utils/                   # Generador de IDs
+-- integrations/
|   `-- gicatesis/               # Integracion BFF con GicaTesis
|       +-- client.py            # Cliente HTTP async
|       +-- types.py             # DTOs Pydantic
|       +-- errors.py            # Excepciones custom
|       `-- cache/               # Cache ETag de formatos
+-- modules/
|   +-- api/                     # Router API REST (21+ endpoints, 730 lineas)
|   |   `-- models.py            # Modelos Pydantic de request
|   `-- ui/                      # Router UI (Jinja)
+-- static/js/                   # Frontend SPA (898 lineas)
`-- templates/                   # HTML Jinja2 (464 lineas)
data/                            # JSON de datos (formatos, prompts, proyectos, cache)
docs/                            # Documentacion completa
scripts/                         # Utilidades de encoding
```

## Documentacion

Ver [`/docs/00-indice.md`](docs/00-indice.md) para el indice completo.

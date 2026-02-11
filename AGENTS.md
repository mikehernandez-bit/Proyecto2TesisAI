# GicaGen

> **Entrada rápida para agentes:** Todo lo que necesitas saber está en [`/docs/00-indice.md`](docs/00-indice.md)

## ¿Qué es GicaGen?

GicaGen es un sistema generador de documentos académicos (tesis, artículos) usando plantillas y flujos de IA. Es un proyecto **relacionado pero independiente** de GicaTesis.

## Ejecutar rápido

```bash
# Python 3.10-3.13 recomendado
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Abrir: http://127.0.0.1:8000/

## Estructura del proyecto

```
app/
+-- main.py              # Entrypoint FastAPI
+-- core/                # Lógica de negocio
|   +-- config.py        # Settings desde env vars
|   +-- services/        # FormatService, PromptService, ProjectService, DocxBuilder, N8NClient
|   +-- storage/         # JsonStore (persistencia JSON)
|   `-- utils/           # Generador de IDs
+-- modules/
|   +-- api/             # Router API REST
|   `-- ui/              # Router UI (Jinja)
+-- static/js/           # Frontend SPA
`-- templates/           # HTML Jinja2
data/                    # JSON de datos (formatos, prompts, proyectos)
docs/                    # Documentación completa
```

## Documentación

Ver [`/docs/00-indice.md`](docs/00-indice.md) para el índice completo.

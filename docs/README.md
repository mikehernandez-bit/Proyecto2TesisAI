# Documentación GicaGen

Bienvenido a la documentación del proyecto **GicaGen**.

## ¿Qué es GicaGen?

GicaGen es un sistema generador de documentos académicos (tesis, artículos científicos) mediante plantillas configurables y flujos de IA integrables.

## Navegación rápida

➡️ **[Ver índice completo →](00-indice.md)**

## Inicio rápido

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Abrir: http://127.0.0.1:8000/

## Estructura del repositorio

```
app/           # Código fuente principal
├── core/      # Lógica de negocio (services, storage, config)
├── modules/   # API REST y UI
├── static/    # JavaScript frontend
└── templates/ # HTML Jinja2
data/          # Datos JSON (formatos, prompts, proyectos)
docs/          # Esta documentación
```

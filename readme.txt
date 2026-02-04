# TesisAI Gen (Scaffold)

Aplicación **FastAPI + Jinja + JS** que implementa (ya operativo) el mockup de **TesisAI**:

- **Dashboard** (estadísticas + tabla de recientes)
- **Wizard “Nuevo Proyecto”** (Paso 1–4)
- **Gestión de Prompts** (CRUD desde UI)
- **Historial** (lista + búsqueda)
- **Generación demo**: crea un `.docx` placeholder y lo deja descargable
- **Integración lista para conectar**:
  - API externa de formatos (Paso 1)
  - n8n (flujo IA real) con callback

> Este repo es un **cascarón funcional**: corre, navega, guarda datos, y genera un Word demo.  
> Luego los equipos conectan APIs reales y lógica avanzada **sin romper la base**.

---

## Tech Stack

- **Backend**: FastAPI
- **Frontend**: Jinja (1 página) + JavaScript (SPA simple)
- **UI/Estilos**: Tailwind CDN + FontAwesome CDN
- **Storage demo**: JSON en `/data`
- **Docs demo**: python-docx (`/outputs/*.docx`)

---

## Estructura del proyecto


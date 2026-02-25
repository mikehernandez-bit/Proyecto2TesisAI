# Vision y Alcance - GicaGen

## Que es GicaGen?

**GicaGen** (GIgC Academic Generator) es un sistema de generacion de documentos academicos que permite crear tesis, articulos cientificos y otros documentos siguiendo formatos institucionales especificos. Consume formatos desde GicaTesis via patron BFF (Backend for Frontend).

## Caracteristicas Principales

- **Wizard guiado de 5 pasos:** Seleccion de formato -> Eleccion de prompt -> Variables del documento -> Guia de integracion n8n -> Descarga
- **Formatos institucionales via BFF:** Consumo de formatos desde GicaTesis API v1 con cache ETag
- **Prompts configurables:** Templates reutilizables con variables dinamicas
- **Simulacion n8n:** Genera output simulado (aiResult + artifacts) sin dependencia de IA real
- **Generacion de artifacts:** DOCX y PDF simulados estructurados desde definiciones de formato
- **Definition Compiler:** Compila definiciones JSON a IR (Intermediate Representation) para generacion
- **Dashboard y historial:** Seguimiento de documentos generados

## Que NO es GicaGen?

> [!IMPORTANT]
> GicaGen es un proyecto **relacionado pero independiente** de GicaTesis.

| GicaGen | GicaTesis |
|---------|-----------|
| Sistema de generacion de documentos | Sistema de gestion de formatos academicos |
| Consume formatos via API BFF | Expone API de formatos v1 |
| Proyecto nuevo, en desarrollo | Proyecto existente |
| No importa codigo de GicaTesis | No debe importar codigo de GicaGen |
| Integracion via `integrations/gicatesis/` | Expone `/api/v1/formats` y assets |

## Objetivos

1. **Corto plazo (MVP):**
   - Wizard funcional con simulacion n8n
   - CRUD de prompts desde UI
   - Historial de proyectos
   - BFF de formatos con cache

2. **Mediano plazo:**
   - Integracion real con n8n para generacion con IA
   - Multiples universidades configuradas
   - Generacion DOCX/PDF estructura real desde formato

3. **Largo plazo:**
   - Generacion PDF nativa mejorada
   - Sistema de templates avanzado
   - Multiples formatos de salida

## Stack Tecnologico

| Capa | Tecnologia |
|------|------------|
| Backend | FastAPI + Python 3.10-3.13 |
| Frontend | JavaScript SPA + Tailwind CSS (CDN) |
| Templates | Jinja2 |
| Documentos | python-docx |
| HTTP Client | httpx (async) |
| Persistencia | JSON files (MVP) |
| Configuracion | python-dotenv + dataclass frozen |
| Integracion | GicaTesis API v1 via `integrations/gicatesis/` |

## Audiencia

- **Desarrolladores:** Quienes mantienen y extienden el sistema
- **Usuarios finales:** Estudiantes y academicos que generan documentos

## Referencias

- [Indice de documentacion](00-indice.md)
- [Arquitectura](02-arquitectura.md)
- [Desarrollo local](06-desarrollo-local.md)

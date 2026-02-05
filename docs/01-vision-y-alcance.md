# Visión y Alcance - GicaGen

## ¿Qué es GicaGen?

**GicaGen** (GIgC Academic Generator) es un sistema de generación de documentos académicos que permite crear tesis, artículos científicos y otros documentos siguiendo formatos institucionales específicos.

## Características Principales

- **Wizard guiado de 4 pasos:** Selección de formato → Elección de prompt → Variables del documento → Generación
- **Formatos institucionales:** Soporte para múltiples universidades y carreras
- **Prompts configurables:** Templates reutilizables con variables dinámicas
- **Generación demo:** Modo offline que genera documentos placeholder
- **Integración n8n:** Flujo de trabajo conectado a IA real (opcional)
- **Dashboard y historial:** Seguimiento de documentos generados

## ¿Qué NO es GicaGen?

> [!IMPORTANT]
> GicaGen es un proyecto **relacionado pero independiente** de GicaTesis.

| GicaGen | GicaTesis |
|---------|-----------|
| Sistema de generación de documentos | Sistema de gestión de tesis (por confirmar) |
| Proyecto nuevo, en desarrollo | Proyecto existente |
| No importa código de GicaTesis | No debe importar código de GicaGen |
| Integración via API (adapters) | Expone API para integraciones |

## Objetivos

1. **Corto plazo (MVP):**
   - Wizard funcional con generación demo
   - CRUD de prompts desde UI
   - Historial de proyectos

2. **Mediano plazo:**
   - Integración con n8n para generación real
   - Conexión a API externa de formatos
   - Múltiples universidades configuradas

3. **Largo plazo:**
   - Integración con GicaTesis via adapters
   - Generación PDF nativa
   - Sistema de templates avanzado

## Stack Tecnológico

| Capa | Tecnología |
|------|------------|
| Backend | FastAPI + Python 3.10-3.13 |
| Frontend | JavaScript SPA + Tailwind CSS |
| Templates | Jinja2 |
| Documentos | python-docx |
| HTTP Client | httpx (async) |
| Persistencia | JSON files (MVP) |

## Audiencia

- **Desarrolladores:** Quienes mantienen y extienden el sistema
- **Usuarios finales:** Estudiantes y académicos que generan documentos

## Referencias

- [Índice de documentación](00-indice.md)
- [Arquitectura](02-arquitectura.md)
- [Desarrollo local](06-desarrollo-local.md)

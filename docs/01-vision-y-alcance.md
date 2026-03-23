# Vision y Alcance - GicaGen

> Actualizado: 2026-03-23

---

## Vision

GicaGen es un generador de documentos academicos con IA real que:

- Usa un **wizard de 5 pasos** para guiar al usuario desde la seleccion del formato hasta la descarga.
- Integra **Gemini, Mistral y OpenRouter** directamente en el backend (sin dependencia de n8n).
- Actua como **BFF** consumiendo GicaTesis para formatos, render DOCX/PDF y assets.
- Persiste proyectos y prompts en JSON local.

---

## Alcance Actual (Implementado)

### Funcionalidades

- Wizard funcional de 5 pasos con UI completa.
- Integracion BFF con GicaTesis (cache ETag, fallback demo, proxy de assets).
- **Generacion IA real** por seccion con Gemini/Mistral/OpenRouter.
- **Fallback automatico** entre proveedores si hay errores de quota o timeout.
- **Circuit breaker** para proteger ante fallos consecutivos.
- **Validador de completitud**: detecta y corrige placeholders en el output.
- **10 prompts reales** (UNAC + UNI) con instrucciones especificas por tipo de documento.
- CRUD de prompts y proyectos (persistencia JSON).
- Trace en vivo via SSE con progreso por seccion.
- Cancelacion de generacion en cualquier punto.
- CI/CD con GitHub Actions (lint + typecheck + pytest).
- 29 archivos de test con 200+ casos.

### Flujo Principal

```
ANTES: Browser -> GicaGen -> n8n (webhook) -> [IA externa] -> callback -> GicaGen
AHORA: Browser -> GicaGen -> Gemini/Mistral/OpenRouter (directo) -> GicaGen
```

---

## Fuera de Alcance (No implementado)

- Base de datos relacional (se usa JSON local)
- Autenticacion de usuarios
- Multi-tenant
- Observabilidad avanzada (OpenTelemetry, metricas Prometheus)
- Tests E2E con backend real (solo scaffold)

---

## TODO Prioritario

| Prioridad | Item |
|-----------|------|
| P1 | Migrar SDK `google-generativeai` a `google.genai` |
| P1 | Ampliar cobertura mypy |
| P1 | Tests E2E con fixtures de backend real |
| P2 | Inyeccion de dependencias via `Depends()` |
| P2 | Metricas y trazas (OpenTelemetry) |
| P2 | Migracion a base de datos |


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

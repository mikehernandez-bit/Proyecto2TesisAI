# Resumen Ejecutivo - GicaGen

> Actualizado: 2026-03-23.
> Para stakeholders y revisores externos.

---

## Que es

**GicaGen** es un sistema de generacion automatica de documentos academicos (tesis, proyectos de investigacion, informes) usando inteligencia artificial.

El usuario selecciona el tipo de documento, completa un formulario con los datos del proyecto, y el sistema genera el contenido seccion por seccion usando modelos de IA (Gemini, Mistral, OpenRouter). El documento final se descarga en formato DOCX o PDF.

---

## Estado del Proyecto (Marzo 2026)

| Area | Estado |
|------|--------|
| Generacion IA real | ✅ Implementado (Gemini + Mistral + OpenRouter) |
| Fallback multi-proveedor | ✅ Implementado |
| 10 plantillas de prompts reales | ✅ Implementado (UNAC + UNI) |
| Validador de completitud | ✅ Implementado |
| Wizard de 5 pasos con UI | ✅ Implementado |
| Trace en vivo (SSE) | ✅ Implementado |
| 29 archivos de tests | ✅ Implementado |
| CI/CD (GitHub Actions) | ✅ Implementado |
| Integracion GicaTesis | ✅ Implementado |
| Base de datos | ❌ Pendiente (usa JSON local) |
| Autenticacion de usuarios | ❌ Pendiente |

---

## Tecnologia

| Capa | Tecnologia |
|------|------------|
| Backend | Python + FastAPI |
| IA | Google Gemini (primario), Mistral (fallback), OpenRouter (fallback) |
| Frontend | JavaScript (SPA), HTML/CSS |
| Render documentos | GicaTesis (sistema hermano) |
| Tests | pytest (200+ casos) + GitHub Actions CI |

---

## Tipos de Documentos Soportados

| Universidad | Tipos |
|-------------|-------|
| UNAC | Maestria Cuantitativa, Maestria Cualitativa, Proyecto Cuantitativo, Proyecto Cualitativo, Informe Cuantitativo, Informe Cualitativo |
| UNI | Posgrado (Maestria/Doctorado), Plan de Trabajo de Tesis, Informe de Ingenieria |

---

## Como funciona la generacion

1. El usuario elige el formato (ej: "Informe de Tesis Cuantitativo UNAC")
2. Selecciona el prompt de IA correspondiente
3. Completa datos: tema, objetivo, hipotesis, metodologia, etc.
4. El sistema genera cada seccion del documento con IA
5. Si un proveedor falla, cambia automaticamente al siguiente
6. El resultado se descarga como DOCX o PDF

---

## Riegos Actuales

| Riesgo | Mitigacion |
|--------|-----------|
| Cuota de IA agotada | Fallback automatico a otros proveedores |
| GicaTesis no disponible | Cache local + modo demo |
| Output de IA incompleto | Validador de completitud + corrector post-generacion |
| Cambios rompiendo funcionalidad | CI/CD con 200+ tests automatizados |

---

## Proximas Mejoras Priorizadas

1. **P1**: Actualizar SDK de Gemini a version mas reciente
2. **P1**: Ampliar tests End-to-End con escenarios reales
3. **P2**: Implementar base de datos (dejar JSON local)
4. **P2**: Agregar autenticacion de usuarios
5. **P2**: Metricas y observabilidad (dashboards)

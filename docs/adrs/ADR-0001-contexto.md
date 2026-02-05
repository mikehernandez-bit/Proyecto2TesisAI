# ADR-0001: Contexto del Proyecto

## Estado

Aceptado

## Contexto

Se necesita documentar el contexto inicial del proyecto GicaGen para entender:
- Qué problema resuelve
- Por qué existe como proyecto separado de GicaTesis
- Qué decisiones técnicas iniciales se tomaron

## Decisión

### Alcance del Proyecto

GicaGen se desarrolla como un **proyecto independiente** de GicaTesis, aunque relacionado. La integración entre ambos sistemas se realizará exclusivamente a través de APIs/adapters, nunca mediante imports directos de código.

### Stack Tecnológico Inicial

| Componente | Tecnología | Justificación |
|------------|------------|---------------|
| Backend | FastAPI | Framework moderno, async, tipado, documentación automática |
| Frontend | JavaScript vanilla + Jinja2 | Simplicidad para MVP, sin overhead de frameworks |
| Estilos | Tailwind CSS (CDN) | Desarrollo rápido, consistencia visual |
| Persistencia | JSON files | MVP sin dependencia de base de datos |
| Generación DOCX | python-docx | Librería estándar de Python para documentos |

### Arquitectura Inicial

Se adoptó una arquitectura modular simple:
- `core/` - Lógica de negocio
- `modules/` - Puntos de entrada (API, UI)
- `data/` - Persistencia en archivos

## Consecuencias

### Positivas
- MVP funcional en poco tiempo
- Fácil de entender y modificar
- Sin dependencias de infraestructura externa

### Negativas
- Persistencia JSON no escala
- Acoplamiento entre servicios y storage
- Sin tests automatizados iniciales

### Neutral
- Requiere refactoring para producción
- Documentación debe mantenerse actualizada

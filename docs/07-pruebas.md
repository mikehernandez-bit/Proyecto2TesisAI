# Pruebas

> Guía de pruebas para GicaGen.

## Estado Actual

> [!WARNING]
> El proyecto actualmente **no tiene tests automatizados** implementados.

---

## Tipos de Pruebas Recomendadas

### 1. Pruebas Unitarias (Pendiente)

**Archivos a testear:**
- `app/core/services/prompt_service.py` - CRUD de prompts
- `app/core/services/project_service.py` - CRUD de proyectos
- `app/core/storage/json_store.py` - Lectura/escritura JSON
- `app/core/utils/id.py` - Generación de IDs

**Framework sugerido:** pytest

```bash
# Instalación (cuando se implemente)
pip install pytest pytest-asyncio httpx

# Ejecutar tests
pytest tests/ -v
```

### 2. Pruebas de Integración (Pendiente)

**Flujos a testear:**
- POST `/api/prompts` → GET `/api/prompts` → verificar prompt creado
- POST `/api/projects/generate` → GET `/api/projects/{id}` → verificar status
- Generación completa de DOCX demo

### 3. Pruebas E2E (Manual)

**Checklist manual:**

- [ ] Abrir http://127.0.0.1:8000/
- [ ] Navegar entre vistas (Dashboard, Wizard, Admin, Historial)
- [ ] Crear un prompt nuevo
- [ ] Editar un prompt existente
- [ ] Eliminar un prompt
- [ ] Completar wizard (pasos 1-4)
- [ ] Descargar DOCX generado
- [ ] Verificar que aparece en historial

---

## Criterios de Aceptación

### Prompt Service

| Criterio | Verificación |
|----------|--------------|
| Crear prompt | Retorna objeto con `id` generado |
| Listar prompts | Retorna array de prompts |
| Actualizar prompt | Campos actualizados persisten |
| Eliminar prompt | Prompt no aparece en lista |

### Project Service

| Criterio | Verificación |
|----------|--------------|
| Crear proyecto | Status inicial `processing` |
| Marcar completado | Status cambia a `completed`, `output_file` presente |
| Marcar fallido | Status cambia a `failed`, `error` presente |

### Generación Demo

| Criterio | Verificación |
|----------|--------------|
| Genera DOCX | Archivo existe en `outputs/` |
| DOCX válido | Se puede abrir con Word/LibreOffice |
| Contiene variables | Variables del form aparecen en documento |

---

## Estructura de Tests Propuesta

```
tests/
├── conftest.py              # Fixtures compartidas
├── unit/
│   ├── test_prompt_service.py
│   ├── test_project_service.py
│   ├── test_json_store.py
│   └── test_id_generator.py
├── integration/
│   ├── test_api_prompts.py
│   ├── test_api_projects.py
│   └── test_generation_flow.py
└── e2e/
    └── test_wizard_flow.py  # Playwright/Selenium
```

---

## Cómo Validar (Manual)

```bash
# 1. Levantar servidor
python -m uvicorn app.main:app --reload

# 2. Health check
curl http://localhost:8000/healthz
# Esperado: {"ok":true,"app":"TesisAI Gen","env":"dev"}

# 3. Listar prompts
curl http://localhost:8000/api/prompts
# Esperado: Array de prompts

# 4. Crear proyecto
curl -X POST http://localhost:8000/api/projects/generate \
  -H "Content-Type: application/json" \
  -d '{"format_id":"fmt_unt_sistemas_2025_1","prompt_id":"prompt_tesis_estandar","title":"Test","variables":{"tema":"IA"}}'
# Esperado: Objeto proyecto con status "processing"

# 5. Verificar DOCX creado
ls outputs/
# Esperado: proj_xxx.docx
```

---

## Próximos Pasos

1. Agregar `pytest` a `requirements.txt`
2. Crear carpeta `tests/`
3. Implementar tests unitarios básicos
4. Configurar CI/CD para ejecutar tests automáticamente

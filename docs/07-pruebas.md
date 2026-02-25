# Pruebas - GicaGen

Este documento resume la estrategia de validacion para el flujo code-first
(GicaGen -> IA -> GicaTesis render) y los gates de calidad.

## Suites y comandos base

| Suite | Comando | Objetivo |
|---|---|---|
| Lint + format check | `.venv\Scripts\python scripts/quality_gate.py lint` | Detectar errores estaticos y baseline de estilo |
| Typecheck | `.venv\Scripts\python scripts/quality_gate.py typecheck` | Validar tipos en modulos criticos |
| Unit + integration | `.venv\Scripts\python -m pytest tests -v` | Validar API y servicios |
| Encoding | `.venv\Scripts\python scripts/check_encoding.py` | Detectar archivos con encoding invalido |
| Mojibake | `.venv\Scripts\python scripts/check_mojibake.py` | Detectar corrupcion de caracteres |

## Flujo equivalente a CI en local

1. Instala dependencias.

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

2. Ejecuta quality gates.

```powershell
.venv\Scripts\python scripts/quality_gate.py all
```

3. Ejecuta pruebas funcionales.

```powershell
.venv\Scripts\python -m pytest tests -v
```

## Casos clave cubiertos

Cobertura relevante en:

- `tests/test_definition_compiler.py`
- `tests/test_gemini_client.py`
- `tests/test_ai_service.py`
- `tests/test_api_integration.py`
- `tests/test_output_validator.py`
- `tests/test_router_ai_adapter.py`

Escenarios criticos:

1. Cuota/fallback de proveedor en capa IA.
2. Endpoint `POST /api/projects/{id}/generate` acepta ejecucion (`202`) y
   no congela UI.
3. Endpoint `GET /api/projects/{id}/trace` devuelve timeline real.
4. Eventos de pipeline para secciones, payload a GicaTesis y render DOCX/PDF.
5. `GET /api/projects/{id}` incluye `progress` y `events` para polling.
6. La cola de eventos rota correctamente (maximo 200 eventos).

## Validacion manual del trace en vivo

1. Crea borrador desde wizard (pasos 1-3).
2. Dispara generacion en paso 4.
3. Verifica que `POST /api/projects/{id}/generate` responde `202`.
4. Consulta `GET /api/projects/{id}` y confirma:
   `status=generating`, avance en `progress.current/total` y eventos nuevos.
5. Consulta `GET /api/projects/{id}/trace` y confirma eventos de:
   `generation.request.received`, `ai.generate.section`,
   `gicatesis.payload`, `gicatesis.render.docx`, `gicatesis.render.pdf`.
6. Verifica estado final de proyecto y enlaces de descarga.

## Pruebas nuevas del contrato async

Archivo: `tests/test_api_integration.py`

- `test_generate_returns_accepted_quickly`
- `test_background_job_updates_progress`
- `test_fallback_event_recorded_on_quota_error`

Archivo: `tests/test_project_service_events.py`

- `test_append_event_truncates_to_200`

Archivo: `tests/test_definition_compiler.py`

- `test_section_index_excludes_preliminaries_indexes_and_keeps_body`
- `test_section_index_skips_figure_and_table_placeholder_nodes`

Archivo: `tests/test_output_validator.py`

- `test_sanitizes_markdown_and_placeholders`
- `test_index_path_forces_empty_content`
- `test_skip_section_token_is_normalized_to_empty`
- `test_abbreviations_are_normalized_to_tab_format`

## CI (GitHub Actions)

Archivo: `.github/workflows/ci.yml`.

Jobs bloqueantes de PR:

1. `lint`
2. `typecheck`
3. `pytest`

## Plan E2E runnable minimo (scaffold)

Se mantiene scaffold Playwright para UX del wizard:

- `e2e/tests/wizard.demo.spec.ts`
- `e2e/tests/wizard.quota.spec.ts`

Comandos:

```powershell
npm install
npm run e2e:install
npm run e2e
```

## Known gaps / TODO

- P1: extender pruebas de trace a SSE (`/trace/stream`) en cliente web.
- P1: convertir E2E mockeado a E2E con backend real y fixtures.
- P1: agregar reporte de cobertura pytest en pipeline.
- P2: evaluar job E2E no bloqueante en CI.

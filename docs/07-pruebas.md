# Pruebas - GicaGen

> Estado actual de testing del proyecto.
> Actualizado: 2026-03-23.

---

## Estado Actual

**29 archivos de test** con 200+ casos automatizados cubriendo todos los modulos criticos.

---

## Suite de Tests

### Capa IA

| Archivo | Cobertura |
|---------|-----------|
| `test_ai_service.py` | Pipeline completo de generacion: secciones, fallback, trace, cancelacion |
| `test_gemini_client.py` | Cliente Gemini: llamadas, errores, quota |
| `test_mistral_client.py` | Cliente Mistral |
| `test_openrouter_client.py` | Cliente OpenRouter |
| `test_resilience_router_openrouter.py` | Fallback entre proveedores |
| `test_circuit_breaker.py` | Apertura/cierre de circuit breaker |
| `test_output_validator.py` | Sanitizacion de output IA |
| `test_completeness_validator.py` | Deteccion y reparacion de placeholders |
| `test_prompt_renderer.py` | Renderizado de templates `{{variables}}` |
| `test_prompt_flow.py` | Flujo completo: carga prompt → render → llega al LLM (47 tests) |
| `test_ai_correction.py` | Pase de correccion post-generacion |
| `test_fallback.py` | Comportamiento con proveedor caido |
| `test_limiter.py` | Rate limiting |
| `test_retry_policy.py` | Politica de reintentos |
| `test_error_classifier.py` | Clasificacion de errores (quota, timeout, etc.) |
| `test_figure_recommendations.py` | Recomendaciones de figuras |
| `test_reference_proposals.py` | Propuestas de referencias |
| `test_pricing_service.py` | Calculo de costos por proveedor |
| `test_provider_indicator_semantics.py` | Semantica de indicadores de proveedor |
| `test_router_ai_adapter.py` | Adaptador del router IA |

### Capa Core

| Archivo | Cobertura |
|---------|-----------|
| `test_api_integration.py` | Tests de integracion de endpoints REST |
| `test_definition_compiler.py` | Compilador de definiciones |
| `test_indices_contract.py` | Contrato de exclusion de indices |
| `test_pipeline_toc_exclusion.py` | Exclusion de TOC en pipeline IA |
| `test_toc_detector.py` | Deteccion de secciones de indice |
| `test_project_service_events.py` | Eventos y trace de proyectos |
| `test_docx_toc.py` | TOC en documentos DOCX |
| `test_gicatesis_offline.py` | Comportamiento sin GicaTesis disponible |

---

## CI/CD (GitHub Actions)

3 checks automaticos en cada Pull Request:

```yaml
jobs:
  lint:    ruff check (imports, formato, style)
  typecheck: mypy (verificacion de tipos)
  pytest:  suite completa de tests
```

**Pasar lint + typecheck + pytest es requisito para merge.**

---

## Ejecutar Localmente

```powershell
# Instalar dependencias de dev
.venv\Scripts\activate
pip install -r requirements-dev.txt

# Todos los tests
python -m pytest tests -v

# Tests especificos
python -m pytest tests/test_prompt_flow.py -v
python -m pytest tests/test_ai_service.py -v

# Con cobertura
python -m pytest tests --cov=app --cov-report=term

# Quality gate completo (como CI)
python scripts/quality_gate.py all
python scripts/quality_gate.py lint
python scripts/quality_gate.py typecheck
```

---

## E2E (Scaffold - P1)

Existe scaffold de tests E2E con Playwright pero sin fixtures de backend real.

```powershell
npm install
npm run e2e:install
npm run e2e
```

Archivos:
- `playwright.config.ts`
- `e2e/tests/wizard.demo.spec.ts`
- `e2e/tests/wizard.quota.spec.ts`

# GicaGen context

GicaGen is the orchestration layer for institutional thesis generation. It
owns the wizard, prompt packages, AI provider selection, project history,
budget views, live trace, payload adaptation, and render proxy. GicaGen does
not own the institutional catalog or the final DOCX/PDF render rules. Those
remain in GicaTesis.

This document summarizes the current codebase after the institutional prompt
package refactor completed on April 1, 2026.

## What GicaGen owns

GicaGen owns the following responsibilities:

- Fetch institutional formats from GicaTesis over HTTP.
- Derive editable AI sections from `FormatDetail.definition`.
- Persist prompt packages and projects in local JSON stores.
- Let users select which sections to generate in the wizard.
- Build one AI prompt per selected section and run the AI pipeline.
- Proxy render requests to GicaTesis with a validated payload.

GicaGen does not import code from GicaTesis. Integration stays on HTTP plus
DTOs only.

## Current wizard

The active wizard has seven steps. Any older documentation that mentions five
steps is obsolete.

1. Select the institutional format.
2. Assign the institutional package and choose sections.
3. Enter project details.
4. Choose provider and model.
5. Review AI generation trace.
6. Build and render.
7. Download artifacts.

Step 2 now hydrates from the real institutional format. Users no longer create
chapters manually as the source of truth for prompt management.

## Prompt package model

Prompt packages are normalized around the institutional format instead of a
manual chapter list. The backend persists a package with this shape:

- `id`, `name`, `format_id`, `format_name`, `format_version`
- `doc_type`, `is_active`, `system_instruction`, `template`
- `variables`
- `sections[]`

Each `sections[]` entry includes:

- `section_id`
- `section_path`
- `section_title`
- `parent_section_path`
- `section_level`
- `optional`
- `default_selected`
- `source_hints`
- `blocks[]`

Each `blocks[]` entry includes:

- `block_id`
- `label`
- `instructions`
- `required_variables[]`
- `required`

Legacy prompt records are still read. GicaGen normalizes them into the new
shape when loading and persists the normalized structure on save.

## Institutional section extraction

The section tree now comes from the institutional format definition. GicaGen
uses these services:

- `InstitutionalSectionService`
- `DefinitionCompiler`
- `TocDetector`

The extraction rules:

- reuse the compiled section index from the real format definition
- exclude table-of-contents and index branches
- mark `resumen`, `dedicatoria`, and `agradecimiento` as optional
- default optional sections to not selected

This works for UNAC and UNI without hardcoding the tree in the view layer.

## Project persistence

Projects now persist more wizard state so generation stays consistent even when
the underlying package evolves.

New persisted fields:

- `prompt_snapshot`
- `selected_sections`

`prompt_snapshot` stores the package structure that the project used when the
user saved the wizard. `selected_sections` stores the exact section subset that
the user chose to generate.

Older projects still load. If these fields are missing, GicaGen reconstructs
them from `prompt_id`, `format_id`, and existing `ai_result` when possible.

## Generation planning

GicaGen now separates section planning from the AI call loop.

- `ProjectGenerationPlanner` merges `definition`, `prompt_snapshot`, and
  `selected_sections`.
- `AIService.generate()` receives `planned_sections`.
- The AI loop runs only the selected sections.
- Each selected section produces one visible prompt trace and one visible AI
  response, even if the section contains several prompt blocks internally.

The final render payload only includes generated sections. GicaTesis keeps the
institutional document structure and renders the missing branches as empty or
unchanged, depending on the format and render pipeline rules.

## Frontend structure

The frontend still exposes `window.TesisAI` for compatibility, but the
entrypoint is now thin. `app/static/js/app.js` is a bootstrap facade, while
the compatibility shell moved to `app/static/js/features/app-shell.js`.
That shell is now a coordinator and public facade. Feature logic lives in
smaller modules:

- `app/static/js/shared/api-client.js`
- `app/static/js/shared/dom.js`
- `app/static/js/state/wizard-store.js`
- `app/static/js/features/projects/project-ui.js`
- `app/static/js/features/dashboard/dashboard-controller.js`
- `app/static/js/features/history/history-controller.js`
- `app/static/js/features/budget/budget-controller.js`
- `app/static/js/features/providers/provider-controller.js`
- `app/static/js/features/wizard/wizard-controller.js`
- `app/static/js/features/wizard/format-step.js`
- `app/static/js/features/wizard/package-selection-step.js`
- `app/static/js/features/wizard/details-step.js`
- `app/static/js/features/wizard/provider-step.js`
- `app/static/js/features/wizard/generation-step.js`
- `app/static/js/features/wizard/build-step.js`
- `app/static/js/features/wizard/download-step.js`
- `app/static/js/features/generation/trace-state.js`
- `app/static/js/features/generation/generation-controller.js`
- `app/static/js/features/generation/trace-view.js`
- `app/static/js/features/n8n/n8n-guide-controller.js`
- `app/static/js/features/prompt-packages/admin-list.js`
- `app/static/js/features/prompt-packages/section-tree.js`
- `app/static/js/features/prompt-packages/editor.js`
- `app/static/js/features/prompt-admin-legacy/prompt-admin-controller.js`
- `app/static/js/app-modules.js`

The main page template changed as well. `app/templates/pages/app.html` is now
an assembler that includes partials for the sidebar, wizard stepper, each
wizard step, the admin prompt view, and modal containers under
`app/templates/pages/partials/`.

Within the shell, these non-wizard domains now have dedicated controllers:

- dashboard
- history
- budget
- providers
- generation
- n8n guide
- legacy prompt admin compatibility

The server-rendered UI also reflects the new step naming:

- `Paquete & Secciones` replaces the old prompt-only wording in step 2.

## Backend hotspots after the refactor

These files now carry the main behavior for the institutional package flow:

- `app/core/services/institutional_section_service.py`
- `app/core/services/project_generation_planner.py`
- `app/core/services/prompt_service.py`
- `app/core/services/project_service.py`
- `app/core/services/ai/ai_service.py`
- `app/modules/api/router.py`
- `app/modules/api/models.py`

## Validation status

The refactor was validated with:

- targeted `pytest` over prompt flow, definition compilation, TOC exclusion,
  project service, router adapter, and AI selection scope
- Playwright wizard scenarios for:
  - happy path with institutional package
  - quota error and retry path
  - section selection affecting details and AI trace
- targeted `ruff check` on the touched Python files
- targeted `mypy` on the touched Python files

The repository-wide `ruff check .` and `mypy .` still report unrelated
pre-existing issues outside this change set. Those were not introduced by this
refactor.

## GicaTesis impact

No GicaTesis code changes were required for this feature.

The reason is explicit:

- `FormatDetail.definition` already exposes enough structure to derive the
  institutional section tree.
- GicaTesis already accepts partial `aiResult.sections` payloads keyed by
  `path` and `sectionId`.
- The render contract stayed unchanged.

## Next steps

The main remaining cleanup is repository-wide quality debt outside this change:

- reduce legacy dynamic typing in `app/modules/api/router.py`
- keep shrinking the public compatibility facade in
  `app/static/js/features/app-shell.js`
- fix unrelated repo-wide lint and mypy findings so full-project checks can run
  green without scoping

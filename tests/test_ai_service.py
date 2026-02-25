"""Tests for app.core.services.ai.ai_service provider routing and fallback."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.services.ai.ai_service import AIService
from app.core.services.ai.errors import ProviderAuthError, QuotaExceededError


def _settings(
    primary: str = "gemini",
    fallback: bool = True,
    *,
    force_transient_fallback: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        AI_PRIMARY_PROVIDER=primary,
        AI_FALLBACK_ON_QUOTA=fallback,
        AI_FORCE_FALLBACK_ON_TRANSIENT=force_transient_fallback,
        AI_CORRECTION_ENABLED=False,
        GEMINI_MODEL="gemini-2.0-flash",
        MISTRAL_MODEL="mistral-medium-2505",
    )


class _InMemorySelectionStore:
    def __init__(self, provider: str = "gemini", mode: str = "auto") -> None:
        fallback = "mistral" if provider == "gemini" else "gemini"
        self._selection = {
            "provider": provider,
            "model": "gemini-2.0-flash" if provider == "gemini" else "mistral-medium-2505",
            "fallback_provider": fallback,
            "fallback_model": "mistral-medium-2505" if fallback == "mistral" else "gemini-2.0-flash",
            "mode": mode,
        }

    def get_selection(self):
        return dict(self._selection)

    def normalize(self, payload):
        merged = dict(self._selection)
        merged.update(payload or {})
        return dict(merged)

    def set_selection(self, payload):
        self._selection.update(payload or {})
        return dict(self._selection)


def _set_selection(svc: AIService, provider: str, *, mode: str = "auto") -> None:
    fallback = "mistral" if provider == "gemini" else "gemini"
    svc.set_provider_selection(
        {
            "provider": provider,
            "model": "gemini-2.0-flash" if provider == "gemini" else "mistral-medium-2505",
            "fallback_provider": fallback,
            "fallback_model": "mistral-medium-2505" if fallback == "mistral" else "gemini-2.0-flash",
            "mode": mode,
        }
    )


@pytest.fixture
def ai_svc():
    svc = AIService()
    svc._selection_store = _InMemorySelectionStore()
    svc._selection = svc._selection_store.get_selection()
    gemini = MagicMock()
    mistral = MagicMock()
    svc._clients = {"gemini": gemini, "mistral": mistral}
    return svc, gemini, mistral


class TestIsConfigured:
    def test_not_configured_when_no_provider_has_key(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = False

        with patch("app.core.services.ai.ai_service.settings", _settings()):
            assert svc.is_configured() is False

    def test_configured_when_any_provider_is_available(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral")):
            assert svc.is_configured() is True
            assert svc.available_providers() == ["mistral"]


class TestGenerate:
    def test_full_flow_with_primary_provider(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido generado por Gemini."

        project = {
            "id": "proj-test-001",
            "title": "Test Project",
            "variables": {"tema": "IA", "objetivo_general": "mejorar"},
            "values": {"tema": "IA", "objetivo_general": "mejorar"},
        }
        prompt = {"template": "Escribe sobre {{tema}} con objetivo {{objetivo_general}}."}
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Introduccion"},
                        {"titulo": "Marco teorico"},
                    ]
                }
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, prompt)

        assert "sections" in result
        assert len(result["sections"]) == 2
        assert svc.get_last_used_provider() == "gemini"
        assert gemini.generate.call_count == 2
        mistral.generate.assert_not_called()

    def test_fallback_to_secondary_provider_on_quota(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Gemini project quota/billing.",
            provider="gemini",
            error_type="exhausted",
        )
        mistral.generate.return_value = "Contenido generado por Mistral."

        project = {"id": "proj-fallback-001", "title": "Fallback", "variables": {"tema": "Fallback"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)),
            patch("app.core.services.ai.ai_service.time.sleep"),
        ):
            result = svc.generate(project, format_detail, None)

        assert result["sections"][0]["content"] == "Contenido generado por Mistral."
        assert svc.get_last_used_provider() == "mistral"
        assert gemini.generate.call_count == 1
        mistral.generate.assert_called_once()

    def test_fail_fast_when_quota_and_fallback_disabled(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Gemini project quota/billing.",
            provider="gemini",
            error_type="exhausted",
        )

        project = {"id": "proj-fail-001", "title": "Fail Fast", "variables": {"tema": "Test"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)),
            patch("app.core.services.ai.ai_service.time.sleep"),
        ):
            with pytest.raises(QuotaExceededError):
                svc.generate(project, format_detail, None)

        assert gemini.generate.call_count == 1
        mistral.generate.assert_not_called()

    def test_auth_error_without_retry_falls_back_immediately(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = ProviderAuthError(
            "Gemini authentication failed.",
            provider="gemini",
            status_code=401,
        )
        mistral.generate.return_value = "Contenido por fallback auth."

        project = {"id": "proj-auth-fallback", "title": "Auth", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, None)

        assert result["sections"][0]["content"] == "Contenido por fallback auth."
        assert gemini.generate.call_count == 1
        assert mistral.generate.call_count == 1

    def test_transient_error_retries_once_then_fallback(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = [RuntimeError("Read timed out"), RuntimeError("Read timed out")]
        mistral.generate.return_value = "Contenido por fallback transient."

        project = {"id": "proj-transient-fallback", "title": "Transient", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            result = svc.generate(project, format_detail, None)

        assert result["sections"][0]["content"] == "Contenido por fallback transient."
        assert gemini.generate.call_count == 2
        assert mistral.generate.call_count == 1

    def test_exhausted_provider_is_disabled_for_rest_of_job(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Gemini project quota/billing.",
            provider="gemini",
            error_type="exhausted",
        )
        mistral.generate.return_value = "Contenido de fallback por seccion."

        project = {"id": "proj-disabled-provider", "title": "Circuit", "variables": {"tema": "x"}}
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Capitulo 1"},
                        {"titulo": "Capitulo 2"},
                    ]
                }
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, None)

        assert len(result["sections"]) == 2
        assert gemini.generate.call_count == 1
        assert mistral.generate.call_count == 2

    def test_empty_prompt_uses_fallback_prompt(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido."

        project = {
            "id": "proj-noprompt",
            "title": "Sin Prompt",
            "variables": {},
        }

        with patch("app.core.services.ai.ai_service.settings", _settings()):
            result = svc.generate(project, None, None)

        assert "sections" in result
        called_prompt = gemini.generate.call_args[0][0]
        assert "Sin Prompt" in called_prompt

    def test_generate_uses_project_selection_override(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        mistral.generate.return_value = "Contenido con seleccion por proyecto."

        project = {
            "id": "proj-selection-override",
            "title": "Seleccion",
            "variables": {"tema": "Seleccion"},
        }
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}
        selection_override = {
            "provider": "mistral",
            "model": "mistral-medium-2505",
            "fallback_provider": "gemini",
            "fallback_model": "gemini-2.0-flash",
            "mode": "fixed",
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, None, selection_override=selection_override)

        assert result["sections"][0]["content"] == "Contenido con seleccion por proyecto."
        mistral.generate.assert_called_once()
        gemini.generate.assert_not_called()

    def test_generate_skips_index_branches_from_definition(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido academico de prueba para la seccion."

        project = {
            "id": "proj-index-skip",
            "title": "Proyecto con indice",
            "variables": {"tema": "Optimizacion"},
        }
        format_detail = {
            "definition": {
                "preliminares": {
                    "indices": [
                        {
                            "titulo": "INDICE",
                            "items": [{"texto": "I. PLANTEAMIENTO DEL PROBLEMA"}],
                        },
                        {"titulo": "INDICE DE TABLAS", "items": [{"texto": "Tabla 1.1"}]},
                    ],
                    "introduccion": {"titulo": "INTRODUCCION"},
                },
                "cuerpo": [
                    {
                        "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                        "contenido": [{"texto": "1.1 Realidad problematica"}],
                    }
                ],
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)):
            result = svc.generate(project, format_detail, None)

        paths = [section["path"] for section in result["sections"]]
        assert "I. PLANTEAMIENTO DEL PROBLEMA" in paths
        assert any(path.endswith("1.1 Realidad problematica") for path in paths)
        assert all(not path.startswith("INDICE") for path in paths)
        assert all("INDICE DE TABLAS" not in path for path in paths)

    def test_generate_resumes_from_partial_ai_result(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido nuevo para segunda seccion."

        project = {
            "id": "proj-resume-001",
            "title": "Resume",
            "variables": {"tema": "Reintento"},
            "ai_result": {
                "sections": [
                    {
                        "sectionId": "sec-0001",
                        "path": "Capitulo 1",
                        "content": "Contenido previo guardado.",
                    }
                ]
            },
        }
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Capitulo 1"},
                        {"titulo": "Capitulo 2"},
                    ]
                }
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, None, resume_from_partial=True)

        assert len(result["sections"]) == 2
        assert result["sections"][0]["content"] == "Contenido previo guardado."
        assert result["sections"][1]["content"] == "Contenido nuevo para segunda seccion."
        assert gemini.generate.call_count == 1

    def test_generate_resumes_from_seed_override(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido generado desde el punto de reanudacion."

        project = {
            "id": "proj-seed-override-001",
            "title": "Resume override",
            "variables": {"tema": "Reintento"},
        }
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Capitulo 1"},
                        {"titulo": "Capitulo 2"},
                    ]
                }
            }
        }
        seed_sections = [
            {
                "sectionId": "sec-0001",
                "path": "Capitulo 1",
                "content": "Contenido parcial externo",
            }
        ]

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(
                project,
                format_detail,
                None,
                resume_from_partial=True,
                seed_sections_override=seed_sections,
            )

        assert len(result["sections"]) == 2
        assert result["sections"][0]["content"] == "Contenido parcial externo"
        assert result["sections"][1]["content"] == "Contenido generado desde el punto de reanudacion."
        assert gemini.generate.call_count == 1

    def test_resume_does_not_replay_seeded_sections_in_progress(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido generado nuevo."

        project = {
            "id": "proj-seed-progress-001",
            "title": "Resume progress",
            "variables": {"tema": "Reintento"},
        }
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Capitulo 1"},
                        {"titulo": "Capitulo 2"},
                    ]
                }
            }
        }
        seed_sections = [
            {
                "sectionId": "sec-0001",
                "path": "Capitulo 1",
                "content": "Contenido parcial externo",
            }
        ]
        progress_events = []

        def _progress_cb(current, total, path, provider, *, stage="section_start"):
            progress_events.append((int(current), str(stage), str(path)))

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            svc.generate(
                project,
                format_detail,
                None,
                resume_from_partial=True,
                seed_sections_override=seed_sections,
                progress_cb=_progress_cb,
            )

        assert any(event[0] == 2 and event[1] == "section_start" for event in progress_events)
        assert not any(event[0] == 1 for event in progress_events)

    def test_fixed_mode_does_not_fallback_even_on_transient_ssl(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = RuntimeError(
            "HTTPSConnectionPool: SSLError(SSLError(1, '[SSL: SSLV3_ALERT_BAD_RECORD_MAC] bad record mac'))"
        )

        project = {"id": "proj-fixed-ssl", "title": "SSL", "variables": {"tema": "TLS"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            with pytest.raises(RuntimeError, match="bad record mac"):
                svc.generate(project, format_detail, None)

        assert mistral.generate.call_count == 2  # 1 intento + 1 retry transitorio
        gemini.generate.assert_not_called()

    def test_fixed_mode_does_not_emit_preemptive_contingency_warning(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        mistral.generate.return_value = "Contenido primario en modo fijo."

        project = {"id": "proj-fixed-clean", "title": "Fixed", "variables": {"tema": "TLS"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}
        trace_events = []

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)):
            result = svc.generate(project, format_detail, None, trace_hook=trace_events.append)

        assert result["sections"][0]["content"] == "Contenido primario en modo fijo."
        assert not any(
            "fallback de contingencia habilitado" in str(evt.get("title", "")).lower() for evt in trace_events
        )


class TestProviderStatus:
    def test_provider_status_exposes_selection_and_health(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True

        status = svc.providers_status_payload()
        assert status["selected_provider"] == "gemini"
        assert status["mode"] == "auto"
        providers = {item["id"]: item for item in status["providers"]}
        assert "gemini" in providers
        assert "mistral" in providers
        assert providers["gemini"]["health"] in {"OK", "UNKNOWN", "DEGRADED", "RATE_LIMITED", "EXHAUSTED"}

    def test_rate_limited_health_with_reset_seconds(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = QuotaExceededError(
            "Rate limited. Retry after 57 seconds.",
            provider="gemini",
            retry_after=57,
            error_type="rate_limited",
        )
        mistral.generate.return_value = "Contenido por fallback."

        project = {"id": "proj-rate-limit", "title": "Rate", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            svc.generate(project, format_detail, None)

        status = svc.providers_status_payload()
        gemini_status = next(item for item in status["providers"] if item["id"] == "gemini")
        assert gemini_status["health"] == "RATE_LIMITED"
        assert gemini_status["rate_limit"]["reset_seconds"] > 0

    def test_exhausted_health_when_quota_exceeded(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="fixed")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Gemini project quota/billing.",
            provider="gemini",
            error_type="exhausted",
        )

        project = {"id": "proj-exhausted", "title": "Quota", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            with pytest.raises(QuotaExceededError):
                svc.generate(project, format_detail, None)

        status = svc.providers_status_payload()
        gemini_status = next(item for item in status["providers"] if item["id"] == "gemini")
        assert gemini_status["health"] == "EXHAUSTED"

    def test_degraded_health_after_repeated_timeouts(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = RuntimeError("Read timed out")

        project = {"id": "proj-timeout", "title": "Timeout", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            for _ in range(3):
                with pytest.raises(RuntimeError):
                    svc.generate(project, format_detail, None)

        status = svc.providers_status_payload()
        mistral_status = next(item for item in status["providers"] if item["id"] == "mistral")
        assert mistral_status["health"] == "DEGRADED"
        assert mistral_status["stats"]["errors_last_15m"] >= 3

    def test_auto_mode_status_skips_exhausted_fallback_provider(self, ai_svc):
        svc, gemini, mistral = ai_svc
        openrouter = MagicMock()
        openrouter.is_configured.return_value = True
        svc._clients["openrouter"] = openrouter
        svc.set_provider_selection(
            {
                "provider": "mistral",
                "model": "mistral-medium-2505",
                "fallback_provider": "gemini",
                "fallback_model": "gemini-2.0-flash",
                "mode": "auto",
            }
        )
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        svc._metrics.record_exhausted("gemini", message="Quota exceeded")

        status = svc.providers_status_payload()

        assert status["fallback_provider"] == "openrouter"
        assert status["fallback_model"] == "openai/gpt-oss-120b:free"

    def test_auto_mode_generation_skips_exhausted_fallback_provider(self, ai_svc):
        svc, gemini, mistral = ai_svc
        openrouter = MagicMock()
        openrouter.is_configured.return_value = True
        openrouter.generate.return_value = "Contenido por OpenRouter."
        svc._clients["openrouter"] = openrouter
        svc.set_provider_selection(
            {
                "provider": "mistral",
                "model": "mistral-medium-2505",
                "fallback_provider": "gemini",
                "fallback_model": "gemini-2.0-flash",
                "mode": "auto",
            }
        )
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = [RuntimeError("Read timed out"), RuntimeError("Read timed out")]
        gemini.generate.return_value = "No debe usarse"
        svc._metrics.record_exhausted("gemini", message="Quota exceeded")

        project = {"id": "proj-skip-exhausted-fallback", "title": "Fallback", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=True)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            result = svc.generate(project, format_detail, None)

        assert result["sections"][0]["content"] == "Contenido por OpenRouter."
        assert mistral.generate.call_count == 2
        gemini.generate.assert_not_called()
        openrouter.generate.assert_called_once()

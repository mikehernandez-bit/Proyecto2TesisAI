from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.services.ai.ai_service import AIService
from app.core.services.ai.resilience_router import LLMResult
from app.core.services.ai.unac_quality_profile import (
    audit_unac_maintenance_sections,
    canonical_formula_for_key,
    load_unac_maintenance_profile,
)


PROFILE = load_unac_maintenance_profile()
REQUIREMENTS = {item.key: item for item in PROFILE.requirements}


def _sentence(prefix: str, start: int, size: int = 20) -> str:
    return prefix + " " + " ".join(f"concepto{start + offset}" for offset in range(size)) + "."


def _paragraph(prefix: str, start: int, *, sentences: int, size: int) -> dict[str, str]:
    return {
        "tipo": "parrafo",
        "texto": " ".join(
            _sentence(prefix if index == 0 else "Desarrollo técnico complementario", start + index * size, size)
            for index in range(sentences)
        ),
    }


def _audit(key: str, content):
    requirement = REQUIREMENTS[key]
    return next(
        item
        for item in audit_unac_maintenance_sections(
            [{"path": requirement.heading, "content": content}]
        )
        if item.key == key
    )


def _best_valid(key: str, candidates):
    requirement = REQUIREMENTS[key]
    valid = []
    for candidate in candidates:
        audit = _audit(key, candidate)
        if (
            requirement.min_words <= audit.words <= requirement.max_words
            and not audit.missing_topics
            and audit.duplicate_ratio <= PROFILE.duplicate_ratio_max
            and audit.formulas >= requirement.min_formulas
            and (
                not audit.paragraph_minimum
                or audit.paragraph_minimum <= audit.paragraphs <= audit.paragraph_maximum
            )
        ):
            valid.append((abs(audit.words - requirement.target_words), audit, candidate))
    assert valid, f"no deterministic candidate repaired {key}"
    return min(valid, key=lambda item: item[0])


def test_regression_repairs_reality_problem_1618_words_and_18_paragraphs():
    topics = [
        "El diagnóstico internacional muestra el problema",
        "La unidad minera define el diagnóstico local",
        "La brecha operativa requiere atención",
        "Las causas técnicas explican la situación",
        "Las consecuencias afectan la continuidad",
        "La solución propone mantenimiento planificado",
    ]
    content = [
        _paragraph(topics[index] if index < len(topics) else "Desarrollo del contexto", index * 500, sentences=4, size=20)
        for index in range(18)
    ]
    initial = _audit("1.1", content)
    assert initial.words > initial.maximum
    assert initial.paragraphs == 18
    assert "diagnostico nacional" in initial.missing_topics

    requirement = REQUIREMENTS["1.1"]
    candidates = AIService._deterministic_topic_completion_candidates(
        content, requirement, initial.missing_topics
    )
    _, repaired, _ = _best_valid("1.1", candidates)
    assert 12 <= repaired.paragraphs <= 14


def test_regression_splits_valid_1457_word_reality_problem_instead_of_rewriting():
    topic_prefixes = (
        "El diagnóstico internacional presenta el contexto del problema",
        "El diagnóstico nacional caracteriza el sector minero peruano",
        "El diagnóstico local examina la unidad minera de Sierra Central",
        "La brecha operativa requiere una intervención técnica",
        "Las causas explican el comportamiento observado",
        "Las consecuencias afectan la continuidad de los equipos",
        "La solución propone un plan de mantenimiento",
        "El contexto operativo delimita la evaluación",
        "La disponibilidad orienta el análisis técnico",
        "La confiabilidad y mantenibilidad estructuran la propuesta",
    )
    content = []
    for paragraph_index, prefix in enumerate(topic_prefixes):
        sentences = []
        for sentence_index in range(6):
            sentence_prefix = prefix if sentence_index == 0 else (
                f"Desarrollo específico {paragraph_index} {sentence_index}"
            )
            sentences.append(
                _sentence(
                    sentence_prefix,
                    100000 + paragraph_index * 1000 + sentence_index * 30,
                    4 if paragraph_index == 9 and sentence_index == 5 else 20,
                )
            )
        content.append({"tipo": "parrafo", "texto": " ".join(sentences)})

    initial = _audit("1.1", content)
    assert initial.minimum <= initial.words <= initial.maximum
    assert initial.paragraphs == 10
    assert not initial.missing_topics

    candidates = AIService._deterministic_paragraph_rebalance_candidates(
        content,
        REQUIREMENTS["1.1"],
    )
    _, repaired, _ = _best_valid("1.1", candidates)
    assert repaired.words == initial.words
    assert repaired.paragraphs == 12


def test_semantic_generation_does_not_rewrite_valid_words_for_paragraph_shortage():
    topic_prefixes = (
        "El diagnóstico internacional presenta el contexto del problema",
        "El diagnóstico nacional caracteriza el sector minero peruano",
        "El diagnóstico local examina la unidad minera de Sierra Central",
        "La brecha operativa requiere una intervención técnica",
        "Las causas explican el comportamiento observado",
        "Las consecuencias afectan la continuidad de los equipos",
        "La solución propone un plan de mantenimiento",
        "El contexto operativo delimita la evaluación",
        "La disponibilidad orienta el análisis técnico",
        "La confiabilidad y mantenibilidad estructuran la propuesta",
    )
    paragraphs = []
    for paragraph_index, prefix in enumerate(topic_prefixes):
        sentences = [
            _sentence(
                prefix if sentence_index == 0 else f"Desarrollo específico {paragraph_index} {sentence_index}",
                200000 + paragraph_index * 1000 + sentence_index * 30,
                4 if paragraph_index == 9 and sentence_index == 5 else 20,
            )
            for sentence_index in range(6)
        ]
        paragraphs.append(" ".join(sentences))

    provider = MagicMock(
        return_value=LLMResult(
            content="\n\n".join(paragraphs),
            provider="mistral",
            status="ok",
            attempts=[],
        )
    )
    service = AIService()
    service._generate_with_provider_fallback = provider
    result = service._generate_unac_semantic_units(
        section_prompt="Contrato base",
        requirements=(REQUIREMENTS["1.1"],),
        preferred_provider="mistral",
        section_current=3,
        section_total=25,
        section_path="I/1.1 Descripción de la realidad problemática",
        section_id="sec-0003",
        selection={"provider": "mistral", "mode": "fixed"},
        disabled_for_job=set(),
    )

    assert provider.call_count == 1
    repaired = _audit("1.1", result.content)
    assert repaired.words == 1457
    assert repaired.paragraphs == 12


def test_regression_1231_words_and_10_paragraphs_is_completed_without_repair_calls():
    topic_prefixes = (
        "El diagnóstico internacional presenta el contexto del problema",
        "El diagnóstico nacional caracteriza el sector minero peruano",
        "El diagnóstico local examina la unidad minera de Sierra Central",
        "La brecha operativa requiere una intervención técnica",
        "Las causas explican el comportamiento observado",
        "Las consecuencias afectan la continuidad de los equipos",
        "La solución propone un plan de mantenimiento",
        "El contexto operativo delimita la evaluación",
        "La disponibilidad orienta el análisis técnico",
        "La confiabilidad y mantenibilidad estructuran la propuesta",
    )
    content = []
    for paragraph_index, prefix in enumerate(topic_prefixes):
        sentences = [
            _sentence(
                prefix if sentence_index == 0 else f"Desarrollo verificable {paragraph_index} {sentence_index}",
                300000 + paragraph_index * 1000 + sentence_index * 30,
                18,
            )
            for sentence_index in range(5)
        ]
        content.append({"tipo": "parrafo", "texto": " ".join(sentences)})
    current_words = _audit("1.1", content).words
    assert current_words < 1231
    content[-1]["texto"] = (
        content[-1]["texto"].rstrip(".")
        + " "
        + " ".join(f"ajuste_unico_{index}" for index in range(1231 - current_words))
        + "."
    )
    initial = _audit("1.1", content)
    assert initial.words == 1231
    assert initial.paragraphs == 10

    provider = MagicMock(
        return_value=LLMResult(
            content="\n\n".join(str(block["texto"]) for block in content),
            provider="mistral",
            status="ok",
            attempts=[],
        )
    )
    service = AIService()
    service._generate_with_provider_fallback = provider
    result = service._generate_unac_semantic_units(
        section_prompt="Contrato base",
        requirements=(REQUIREMENTS["1.1"],),
        preferred_provider="mistral",
        section_current=3,
        section_total=25,
        section_path="I/1.1 Descripción de la realidad problemática",
        section_id="sec-0003",
        selection={"provider": "mistral", "mode": "fixed"},
        disabled_for_job=set(),
        project_values={
            "variable_independiente": "Mantenimiento Centrado en Confiabilidad",
            "variable_dependiente": "Disponibilidad inherente",
            "objeto_estudio": "motoniveladoras CAT 24M",
            "lugar": "Sierra Central",
            "temporal": "2025",
        },
    )

    assert provider.call_count == 1
    repaired = _audit("1.1", result.content)
    assert repaired.minimum <= repaired.words <= repaired.maximum
    assert 12 <= repaired.paragraphs <= 14


@pytest.mark.parametrize(
    "key",
    [item.key for item in PROFILE.requirements if not item.expected_items],
)
def test_every_narrative_profile_unit_has_a_deterministic_deficit_safety_net(key: str):
    requirement = REQUIREMENTS[key]
    topic_text = ". ".join(requirement.topics)
    topic_words = len(topic_text.split())
    seed_word_target = max(8, requirement.min_words // 2)
    unique_words = [
        f"base_{key.replace('.', '_')}_{index}"
        for index in range(max(1, seed_word_target - topic_words))
    ]
    paragraph_count = max(1, requirement.min_paragraphs)
    chunks = [[] for _ in range(paragraph_count)]
    for index, word in enumerate(unique_words):
        chunks[index % paragraph_count].append(word)
    content = []
    for index, chunk in enumerate(chunks):
        prefix = topic_text + ". " if index == 0 and topic_text else ""
        content.append(
            {
                "tipo": "parrafo",
                "texto": (prefix + " ".join(chunk) + ".").strip(),
            }
        )
    formula = canonical_formula_for_key(key)
    if formula:
        content.append(formula)

    initial = _audit(key, content)
    assert initial.words < initial.minimum
    candidates = AIService._deterministic_deficit_completion_candidates(
        content,
        requirement,
        values={
            "variable_independiente": "Mantenimiento Centrado en Confiabilidad",
            "variable_dependiente": "Disponibilidad inherente",
            "objeto_estudio": "motoniveladoras CAT 24M",
            "lugar": "Sierra Central",
            "temporal": "2025",
        },
    )
    _, repaired, _ = _best_valid(key, candidates)
    assert repaired.minimum <= repaired.words <= repaired.maximum


@pytest.mark.parametrize(
    "key",
    [item.key for item in PROFILE.requirements if not item.expected_items],
)
def test_every_narrative_profile_unit_has_a_deterministic_excess_safety_net(key: str):
    requirement = REQUIREMENTS[key]
    paragraph_count = (
        requirement.max_paragraphs + 2
        if requirement.max_paragraphs
        else max(2, requirement.min_paragraphs)
    )
    sentence_count = paragraph_count * 6
    desired_words = requirement.max_words + max(60, requirement.max_words // 4)
    topics = ". ".join(requirement.topics)
    sentences: list[str] = []
    for index in range(sentence_count):
        prefix = topics if index == 0 and topics else f"Desarrollo tecnico {key} {index}"
        token_count = max(5, desired_words // sentence_count - len(prefix.split()))
        tokens = " ".join(
            f"exceso_{key.replace('.', '_')}_{index}_{offset}"
            for offset in range(token_count)
        )
        sentences.append(f"{prefix} {tokens}.")
    per_paragraph = len(sentences) // paragraph_count
    content = [
        {
            "tipo": "parrafo",
            "texto": " ".join(
                sentences[index * per_paragraph : (index + 1) * per_paragraph]
            ),
        }
        for index in range(paragraph_count)
    ]
    formula = canonical_formula_for_key(key)
    if formula:
        content.append(formula)

    initial = _audit(key, content)
    assert initial.words > initial.maximum
    candidates = AIService._deterministic_compression_candidates(content, requirement)
    _, repaired, _ = _best_valid(key, candidates)
    assert repaired.minimum <= repaired.words <= repaired.maximum


def test_regression_repairs_oversized_methodology_units_without_llm():
    cases = {
        "4.4": [
            _paragraph(
                "La ubicación del lugar de estudio comprende la operación y el entorno operativo",
                10000,
                sentences=8,
                size=20,
            )
        ],
        "4.6": [
            _paragraph(prefix, 20000 + index * 1000, sentences=4, size=20)
            for index, prefix in enumerate(
                (
                    "El procesamiento organiza los datos",
                    "El análisis interpreta la información",
                    "Los indicadores orientan la evaluación",
                    "Los resultados se presentarán objetivamente",
                )
            )
        ],
    }
    for key, content in cases.items():
        initial = _audit(key, content)
        assert initial.words > initial.maximum
        _, repaired, _ = _best_valid(
            key,
            AIService._deterministic_compression_candidates(content, REQUIREMENTS[key]),
        )
        assert repaired.words <= repaired.maximum


def test_repetitive_reality_problem_is_cleaned_and_refilled_without_llm():
    requirement = REQUIREMENTS["1.1"]
    topic_prefixes = (
        "El diagnóstico internacional presenta el contexto técnico",
        "El diagnóstico nacional caracteriza el sector minero peruano",
        "El diagnóstico local examina la unidad de estudio",
        "La brecha operativa requiere una intervención técnica",
        "Las causas explican la condición observada",
        "Las consecuencias afectan la continuidad operacional",
        "La solución propone mantenimiento planificado",
        "El contexto delimita el análisis",
        "La disponibilidad orienta la evaluación",
        "La confiabilidad estructura la propuesta",
        "La mantenibilidad completa el diagnóstico",
        "La operación define el alcance técnico",
    )
    repeated = (
        "La evaluación técnica mantiene una secuencia uniforme para organizar "
        "la información del proyecto y orientar las decisiones posteriores."
    )
    content = [
        {
            "tipo": "parrafo",
            "texto": prefix
            + ". "
            + " ".join(
                f"evidencia_unica_{paragraph_index}_{word_index}"
                for word_index in range(45)
            )
            + ". "
            + " ".join(repeated for _ in range(4)),
        }
        for paragraph_index, prefix in enumerate(topic_prefixes)
    ]
    initial = _audit("1.1", content)
    assert initial.duplicate_ratio > PROFILE.duplicate_ratio_max

    candidates = AIService._deterministic_repetition_repair_candidates(
        content,
        requirement,
        values={
            "variable_independiente": "Mantenimiento Centrado en Confiabilidad",
            "variable_dependiente": "Disponibilidad inherente",
            "objeto_estudio": "motoniveladoras CAT 24M",
            "lugar": "Sierra Central",
            "temporal": "2025",
        },
    )
    _, repaired, _ = _best_valid("1.1", candidates)
    assert repaired.duplicate_ratio <= PROFILE.duplicate_ratio_max
    assert 12 <= repaired.paragraphs <= 14


def test_regression_inserts_ethics_and_compresses_4_7_in_one_local_pass():
    content = [
        _paragraph(prefix, 40000 + index * 1000, sentences=4, size=24)
        for index, prefix in enumerate(
            (
                "La confidencialidad protege la información",
                "La integridad conserva el registro fiel",
                "El consentimiento informado respeta la participación voluntaria",
            )
        )
    ]
    initial = _audit("4.7", content)
    assert "etica" in initial.missing_topics
    requirement = REQUIREMENTS["4.7"]
    candidates = AIService._deterministic_topic_completion_candidates(
        content, requirement, initial.missing_topics
    )
    _, repaired, _ = _best_valid("4.7", candidates)
    assert not repaired.missing_topics

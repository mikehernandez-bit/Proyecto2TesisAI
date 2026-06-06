"""Tests for app.core.services.ai.output_validator."""

import logging

import pytest

from app.core.services.ai.output_validator import OutputValidator, ValidationError


@pytest.fixture
def validator():
    return OutputValidator()


def _reality_problem_figure(title: str) -> dict:
    return {
        "tipo": "figura",
        "titulo": title,
        "caption": title,
        "ruta_placeholder": "assets/placeholder_figura.png",
        "fuente": "Elaboración propia.",
        "nota": "Guía para elaborar la figura: usar datos reales depurados.",
        "nota_color": "0000FF",
    }


def _valid_reality_problem_content() -> list[dict]:
    paragraphs = [
        (
            "En el contexto operativo de la minería a cielo abierto, la continuidad operativa constituye un "
            "factor determinante para alcanzar los objetivos de producción. Las vías de acarreo sostienen la "
            "cadena de valor porque permiten el tránsito seguro de camiones y equipos auxiliares, mientras que "
            "las motoniveladoras CAT 24M conservan la geometría de esas rutas. Cuando aparecen fallas funcionales "
            "imprevistas, la baja disponibilidad afecta ciclos de acarreo, seguridad y costo correctivo. Por ello, "
            "el problema requiere una estrategia técnica basada en confiabilidad y no una respuesta reactiva."
        ),
        (
            "En la India, Jakkula et al. (2021) analizaron confiabilidad, disponibilidad y mantenibilidad en "
            "equipos Load-Haul-Dump de minería subterránea, identificando subsistemas con baja confiabilidad y "
            "paradas que elevaban costos de mantenimiento. En Irán, Nouri et al. (2023) estudiaron un camión "
            "Komatsu en la mina de cobre Sungun y relacionaron condiciones severas con menor disponibilidad, "
            "mayor MTTR e interrupciones productivas. Estos antecedentes internacionales muestran que los equipos "
            "móviles mineros requieren identificar subsistemas críticos, frecuencia de fallas y consecuencias "
            "operacionales antes de definir tareas de mantenimiento."
        ),
        (
            "En Latinoamérica, Roa et al. (2023), en Colombia, desarrollaron una mejora de mantenimiento para "
            "cargadores frontales Caterpillar 962H con disponibilidad inferior a la meta corporativa. El trabajo "
            "aplicó Mantenimiento Centrado en Confiabilidad, análisis taxonómico alineado con ISO 14224 y revisión "
            "de correctivos frecuentes. El antecedente evidencia que la falta de planes basados en confiabilidad "
            "mantiene alta recurrencia de fallas y limita la productividad."
        ),
        (
            "En el Perú, Flores (2024) aplicó RCM a camiones Caterpillar 785 y reportó una mejora de disponibilidad "
            "inherente de 84,82 % a 88,25 %, demostrando la utilidad de la metodología en maquinaria de gran "
            "tonelaje. Chavez (2024), al estudiar perforadoras Everdigm T450, abordó una disponibilidad crítica "
            "promedio del 61 %, identificó riesgos funcionales y proyectó mejora del MTBF. Estos casos confirman "
            "que el RCM permite ordenar modos de falla, evaluar mantenibilidad y orientar decisiones de mantenimiento."
        ),
        (
            "A nivel local, la flota de motoniveladoras CAT 24M de Sierra Central registra una Disponibilidad "
            "Inherente promedio de 85 %, frente a un KPI estratégico de 90 %, lo que configura una brecha negativa "
            "de 5 %. El historial de fallas evidencia que el Sistema de Implementos o Mando de Círculo, el Tren de "
            "Potencia y el Sistema Hidráulico concentran 75 % de los eventos de parada. Esta concentración incrementa "
            "correctivos, prolonga MTTR, reduce MTBF y compromete la continuidad de vías de acarreo."
        ),
        (
            "Para determinar el origen técnico de esta desviación y evitar dispersión de recursos, se aplicó un "
            "Diagrama de Pareto al historial de fallas. La herramienta jerarquiza eventos por frecuencia, permite "
            "reconocer pocos vitales bajo la regla 80/20 y orienta la focalización del mantenimiento, tal como se "
            "presenta en la Figura 1.1."
        ),
        (
            "La Figura 1.1 evidencia que el Sistema de Implementos o Mando de Círculo, el Tren de Potencia y el "
            "Sistema Hidráulico agrupan 75 % de los eventos de parada, por lo que constituyen pocos vitales del "
            "problema. La concentración no solo describe frecuencia, sino impacto sobre Disponibilidad Inherente: "
            "cada falla repetitiva reduce MTBF y eleva MTTR por diagnóstico, espera de repuestos y reparación. "
            "Esta lectura justifica focalizar el plan en sistemas críticos."
        ),
        (
            "Una vez identificados los sistemas de mayor criticidad, se examinó la causa raíz mediante un Diagrama "
            "de Causa-Efecto. El análisis ordena factores técnicos, humanos, metodológicos, de maquinaria, "
            "materiales, medición y medio ambiente para explicar la recurrencia de fallas, como se observa en la "
            "Figura 1.2."
        ),
        (
            "La Figura 1.2 muestra que el problema es sistémico y que la causa raíz principal se ubica en Métodos. "
            "El mantenimiento actual es rígido, basado en horas motor, y no incorpora condición real, carga dinámica "
            "ni fallas incipientes. A ello se suma un medio ambiente con polvo, sílice abrasiva, altitud, variación "
            "térmica y carga mecánica que acelera desgaste. Por tanto, cambiar componentes no corrige la recurrencia; "
            "se requiere rediseñar la estrategia mediante RCM. La lectura causal obliga a pasar de tareas uniformes "
            "a tareas diferenciadas por criticidad, consecuencia operacional y condición observable del activo."
        ),
        (
            "Ante esta evidencia causal, se evaluaron alternativas como renovación de flota, sustitución de "
            "componentes, monitoreo en línea, optimización de stock y RCM. La Matriz de Relevancia compara "
            "viabilidad técnica, costo de implementación, sostenibilidad y alineamiento con la causa raíz, como se "
            "muestra en la Figura 1.3."
        ),
        (
            "La Figura 1.3 permite distinguir alternativas de contención y alternativas estructurales. La renovación "
            "anticipada se descarta por alto CAPEX; la sustitución masiva corrige síntomas inmediatos, pero no reduce "
            "recurrencia; el monitoreo en línea exige inversión tecnológica y capacitación; y la optimización de stock "
            "reduce esperas, pero no baja frecuencia de fallas. El RCM resulta estructural porque interviene modos de "
            "falla, criticidad y tareas preventivas, por lo que justifica pasar a la priorización final."
        ),
        (
            "Finalmente, las alternativas viables fueron sometidas a una Matriz de Priorización ponderada. Dado que "
            "la brecha principal es la baja disponibilidad, se asignó mayor peso al impacto en disponibilidad, además "
            "del costo de implementación, sostenibilidad y retorno operativo, como se presenta en la Figura 1.4."
        ),
        (
            "La Figura 1.4 valida cuantitativamente la selección del RCM. El criterio Impacto en Disponibilidad "
            "recibe un peso de 50 %, mientras que Costo de Implementación alcanza 30 %. Bajo esa ponderación, el RCM "
            "obtiene puntaje global 7.9 y supera a la optimización de stock, que alcanza 4.6. El stock puede reducir "
            "MTTR por menor espera logística, pero no evita recurrencia de fallas; el RCM sí mejora MTBF y MTTR al "
            "actuar sobre criticidad, modos de falla, tareas preventivas y causas raíz. Por ello, la decisión no se "
            "basa solo en disponibilidad inmediata, sino en sostenibilidad técnica del control de fallas."
        ),
        (
            "En consecuencia, la Variable Independiente corresponde al Plan de Mantenimiento Centrado en "
            "Confiabilidad, desarrollado bajo SAE JA1011:2024, ISO 14224, taxonomía de activos, análisis de "
            "criticidad, AMEF e implementación del plan. Esta estrategia impacta en la Variable Dependiente, "
            "Disponibilidad Inherente, mediante los indicadores MTBF, MTTR y disponibilidad. El objetivo técnico es "
            "cerrar la brecha entre 85 % y 90 %, transitando de un modelo correctivo o preventivo rígido hacia un "
            "modelo proactivo basado en criticidad, modos de falla y consecuencias operacionales."
        ),
    ]
    filler = (
        " El argumento se mantiene vinculado al caso operativo, conserva la trazabilidad técnica y evita una "
        "redacción resumida."
    )
    while len(" ".join(paragraphs).split()) < 1325:
        paragraphs[0] += filler
    return [
        {"tipo": "parrafo", "texto": paragraphs[0]},
        {"tipo": "parrafo", "texto": paragraphs[1]},
        {"tipo": "parrafo", "texto": paragraphs[2]},
        {"tipo": "parrafo", "texto": paragraphs[3]},
        {"tipo": "parrafo", "texto": paragraphs[4]},
        {"tipo": "parrafo", "texto": paragraphs[5]},
        _reality_problem_figure("Diagrama de Pareto de modos de falla en flota CAT 24M"),
        {"tipo": "parrafo", "texto": paragraphs[6]},
        {"tipo": "parrafo", "texto": paragraphs[7]},
        _reality_problem_figure("Análisis de Causa-Efecto de Baja Disponibilidad (Ishikawa)"),
        {"tipo": "parrafo", "texto": paragraphs[8]},
        {"tipo": "parrafo", "texto": paragraphs[9]},
        _reality_problem_figure("Matriz de Relevancia para el filtrado de alternativas de solución"),
        {"tipo": "parrafo", "texto": paragraphs[10]},
        {"tipo": "parrafo", "texto": paragraphs[11]},
        _reality_problem_figure("Matriz de Priorización de soluciones factibles"),
        {"tipo": "parrafo", "texto": paragraphs[12]},
        {"tipo": "parrafo", "texto": paragraphs[13]},
    ]


class TestValidate:
    def test_valid_ai_result(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "Introduccion",
                    "content": "Contenido de la introduccion con suficiente texto.",
                },
                {
                    "sectionId": "sec-0002",
                    "path": "Marco Teorico",
                    "content": "Contenido del marco teorico con suficiente texto.",
                },
            ]
        }
        result = validator.validate(ai_result)
        assert len(result["sections"]) == 2
        assert result["sections"][0]["sectionId"] == "sec-0001"

    def test_missing_sections_raises(self, validator):
        with pytest.raises(ValidationError, match="non-empty list"):
            validator.validate({"sections": []})

    def test_not_a_dict_raises(self, validator):
        with pytest.raises(ValidationError, match="must be a dict"):
            validator.validate("not a dict")

    def test_missing_section_id_auto_assigned(self, validator):
        ai_result = {
            "sections": [
                {"path": "Intro", "content": "Texto suficientemente largo para pasar."},
            ]
        }
        result = validator.validate(ai_result)
        assert result["sections"][0]["sectionId"].startswith("sec-auto-")

    def test_empty_content_warning(self, validator):
        ai_result = {
            "sections": [
                {"sectionId": "sec-0001", "path": "Intro", "content": ""},
            ]
        }
        result = validator.validate(ai_result)
        assert result["sections"][0]["content"] == ""

    def test_sanitizes_markdown_and_placeholders(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "I. PLANTEAMIENTO/1.1 Realidad",
                    "content": (
                        "### Titulo interno\n"
                        "**Texto** con  |  tabla markdown\n"
                        "- item con vineta\n\n"
                        "FIGURA DE EJEMPLO\n"
                        "TITULO DEL PROYECTO"
                    ),
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert "###" not in content
        assert "**" not in content
        assert "|" not in content
        assert "FIGURA DE EJEMPLO" not in content
        assert "TITULO DEL PROYECTO" not in content
        assert "item con vineta" in content

    def test_preserves_structured_content_lists(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-structured",
                    "path": "V. RESULTADOS/5.1 Analisis de resultados",
                    "content": [
                        {"tipo": "parrafo", "texto": "Parrafo academico suficientemente largo para pasar validacion."},
                        {
                            "tipo": "tabla",
                            "titulo": "Tabla 1. Variables",
                            "encabezados": ["Variable", "Definicion", "Indicador"],
                            "filas": [["A", "[COMPLETAR]", "I1"]],
                        },
                        {
                            "tipo": "figura",
                            "titulo": "Figura 1. Modelo",
                            "caption": "Figura 1. Modelo conceptual propuesto.",
                            "nota": "Guía para elaborar la figura: usar datos reales.",
                            "nota_color": "0000FF",
                        },
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert content[0]["tipo"] == "parrafo"
        assert content[1]["tipo"] == "tabla"
        assert content[1]["filas"][0][1] == "[COMPLETAR]"
        assert content[2]["tipo"] == "figura"
        assert content[2]["ruta_placeholder"] == "assets/placeholder_figura.png"
        assert content[2]["nota"] == "Guía para elaborar la figura: usar datos reales."
        assert content[2]["nota_color"] == "0000FF"

    def test_chapter_two_text_only_sections_drop_structured_blocks_and_generic_closure(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-antecedentes",
                    "path": "II. MARCO TEORICO/2.1 Antecedentes",
                    "content": [
                        {
                            "tipo": "parrafo",
                            "texto": (
                                "Burhannudin y Anshori (2022) analizaron una excavadora minera con resultados "
                                "numericos y aporte metodologico al mantenimiento RCM."
                            ),
                        },
                        {
                            "tipo": "tabla",
                            "titulo": "Tabla ajena",
                            "encabezados": ["Tema"],
                            "filas": [["sistema de bombeo"]],
                        },
                        {"tipo": "figura", "caption": "Figura 2.1 Arquitectura conceptual aplicada al titulo."},
                        {"tipo": "formula", "texto": "NPR = S x O x D", "numero": "(1)"},
                        {
                            "tipo": "parrafo",
                            "texto": "Los antecedentes revisados confirman la utilidad general del metodo.",
                        },
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]

        assert isinstance(content, list)
        assert [block["tipo"] for block in content] == ["parrafo"]
        assert "Burhannudin" in content[0]["texto"]
        assert "antecedentes revisados confirman" not in content[0]["texto"].lower()

    def test_chapter_two_bases_allow_formulas_and_controlled_figures_but_no_tables(self, validator):
        concept_paragraph = (
            "El modelo teorico principal se desarrolla antes del soporte visual para explicar sus componentes, "
            "su funcion dentro del proyecto, la relacion con las dimensiones registradas y el criterio tecnico "
            "que justifica presentar un esquema despues del texto academico, evitando que la figura aparezca "
            "como relleno aislado o sin una explicacion previa suficiente."
        )
        formula_paragraph = (
            "El indicador se define como una relacion cuantitativa entre variables observables del estudio, "
            "por lo que primero se precisan sus entradas, su unidad de medida, su sentido de lectura y su utilidad."
        )
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-bases",
                    "path": "II. MARCO TEORICO/2.2 Bases teoricas",
                    "content": [
                        {"tipo": "figura", "caption": "Figura 2.0 Figura al inicio que debe caer"},
                        {"tipo": "parrafo", "texto": concept_paragraph},
                        {
                            "tipo": "tabla",
                            "titulo": "Matriz de Consistencia de Implementacion",
                            "encabezados": ["Problema"],
                            "filas": [["sistema de bombeo"]],
                        },
                        {
                            "tipo": "figura",
                            "caption": "Figura 2.1 Proceso teorico del estudio",
                            "fuente": "Placeholder tecnico controlado. Reemplazar por la figura validada por el autor.",
                        },
                        {"tipo": "figura", "caption": "Figura 2.2 Figura consecutiva que debe caer"},
                        {
                            "tipo": "formula",
                            "id": "eq_2_1_npr",
                            "texto": "NPR = S x O x D",
                            "latex": "NPR = S \\\\times O \\\\times D",
                            "numero": "(1)",
                        },
                        {"tipo": "parrafo", "texto": formula_paragraph},
                        {"tipo": "formula", "texto": "Disponibilidad = TO / (TO + TIM)", "numero": "(2)"},
                        {
                            "tipo": "parrafo",
                            "texto": (
                                "La lectura del indicador permite comparar escenarios y evitar que la formula "
                                "quede como un elemento aislado dentro de las bases teoricas."
                            ),
                        },
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        block_types = [block["tipo"] for block in content]

        assert "tabla" not in block_types
        assert block_types == ["parrafo", "figura", "parrafo", "formula", "parrafo"]
        assert content[3]["texto"] == "Disponibilidad = TO / (TO + TIM)"
        assert all("Placeholder tecnico" not in str(block) for block in content)

    def test_chapter_three_hypotheses_drop_visual_blocks(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-hipotesis",
                    "path": "III. HIPOTESIS Y VARIABLES/3.1 Hipotesis",
                    "content": [
                        {
                            "tipo": "parrafo",
                            "texto": (
                                "Hipotesis general e hipotesis especificas en orden "
                                "confiabilidad y mantenibilidad."
                            ),
                        },
                        {
                            "tipo": "figura",
                            "caption": "Flujo metodologico del estudio sobre el titulo completo.",
                        },
                        {
                            "tipo": "tabla",
                            "titulo": "Tabla ajena",
                            "encabezados": ["A"],
                            "filas": [["B"]],
                        },
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert [block["tipo"] for block in content] == ["parrafo"]

    def test_chapter_four_design_allows_only_formula_schema_not_tables_or_figures(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-diseno",
                    "path": "IV. METODOLOGIA DEL PROYECTO/4.1 Diseno metodologico",
                    "content": [
                        {
                            "tipo": "parrafo",
                            "texto": "El esquema del diseno se representa de la siguiente manera.",
                        },
                        {
                            "tipo": "tabla",
                            "titulo": "Tabla 4.1 Matriz de consistencia metodologica",
                            "encabezados": ["Elemento"],
                            "filas": [["Diseno"]],
                        },
                        {"tipo": "formula", "texto": "M O1 X O2", "alineacion": "center"},
                        {"tipo": "figura", "caption": "Figura 4.1 Esquema del diseno preexperimental"},
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert [block["tipo"] for block in content] == ["parrafo", "formula"]
        assert content[1]["texto"] == "M O1 X O2"

    def test_chapter_four_text_sections_drop_tables_figures_and_placeholder_lines(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-procesamiento",
                    "path": "IV. METODOLOGIA DEL PROYECTO/4.6 Analisis y procesamiento de datos",
                    "content": [
                        {
                            "tipo": "parrafo",
                            "texto": "Se depuraran registros y se calcularan MTBF, MTTR y disponibilidad inicial.",
                        },
                        {
                            "tipo": "parrafo",
                            "texto": "Figura 4.6 Flujo metodologico del estudio sobre el titulo completo.",
                        },
                        {
                            "tipo": "parrafo",
                            "texto": "La combinacion de estos elementos asegura un enfoque riguroso y sistematico.",
                        },
                        {
                            "tipo": "tabla",
                            "titulo": "Tabla 4.3 Flujo de procesamiento de datos",
                            "encabezados": ["Etapa"],
                            "filas": [["Preparacion"]],
                        },
                        {
                            "tipo": "figura",
                            "caption": "Flujo metodologico del estudio sobre el titulo completo.",
                            "fuente": "Placeholder tecnico controlado. Reemplazar por la figura validada por el autor.",
                        },
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert [block["tipo"] for block in content] == ["parrafo"]
        assert "Placeholder tecnico" not in str(content)
        assert "Figura 4.6" not in str(content)
        assert "combinacion de estos elementos" not in str(content).lower()

    def test_chapter_four_length_gap_is_warning_not_validation_error(self, validator, caplog):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-poblacion",
                    "path": "IV. METODOLOGIA DEL PROYECTO/4.3 Poblacion y muestra",
                    "content": [{"tipo": "parrafo", "texto": " ".join(["poblacion"] * 150)}],
                }
            ]
        }

        with caplog.at_level(logging.WARNING):
            result = validator.validate(ai_result)

        assert result["sections"][0]["sectionId"] == "sec-poblacion"
        assert "Capitulo IV fuera de extension" in caplog.text
        assert "maximo 130" in caplog.text

    @pytest.mark.skip(reason="Legacy test replaced by dynamic table contract tests.")
    def test_schedule_section_keeps_dynamic_structured_table(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-cronograma",
                    "path": "V. CRONOGRAMA DE ACTIVIDADES",
                    "content": [
                        {
                            "tipo": "tabla",
                            "id": "tab-crono-dinamica",
                            "titulo": "Tabla de cronograma dinamica",
                            "encabezados": ["Actividad", "Ene", "Feb"],
                            "filas": [
                                ["1.1. Levantamiento", "", "âœ–", "", "", "", "", "", "", "", "", "", ""],
                                ["8.4. Cierre", "", "", "", "", "", "", "", "", "", "", "", "âœ–"],
                            ],
                            "orientacion": "landscape",
                            "simbolo_marca": "âœ–",
                        }
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]

        assert isinstance(content, list)
        assert len(content) == 1
        table = content[0]
        assert table["tipo"] == "tabla"
        assert table["id"] == "tab-pres-dinamica"
        assert table["titulo"] == "Tabla de presupuesto dinamica"
        assert table["orientacion"] == "portrait"
        assert table["encabezados"] == ["Concepto", "Cantidad", "Costo"]
        assert table["filas"] == [["Analisis", "1", "1200"], ["Viaticos", "3", "900"]]
        return
        assert table["id"] == "tab-crono-dinamica"
        assert table["titulo"] == "Tabla de cronograma dinamica"
        assert table["orientacion"] == "landscape"
        assert table["encabezados"] == ["Actividad", "Ene", "Feb"]
        assert table["filas"][0][0].startswith("1.1.")
        assert table["simbolo_marca"] == "✖"
        assert any(row[0].startswith("1.1.") and row[2] == "✖" for row in table["filas"])
        assert any(row[0].startswith("8.4.") and row[12] == "✖" for row in table["filas"])

    def test_schedule_section_without_structured_table_raises(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-cronograma",
                    "path": "V. CRONOGRAMA DE ACTIVIDADES",
                    "content": "Cronograma narrativo sin tabla estructurada.",
                }
            ]
        }

        with pytest.raises(ValidationError, match="tabla estructurada valida de cronograma"):
            validator.validate(ai_result)

    @pytest.mark.skip(reason="Legacy test replaced by dynamic table contract tests.")
    def test_budget_section_keeps_dynamic_structured_table(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-presupuesto",
                    "path": "VI. PRESUPUESTO",
                    "content": [
                        {
                            "tipo": "tabla",
                            "id": "tab-pres-dinamica",
                            "titulo": "Tabla de presupuesto dinamica",
                            "encabezados": ["Concepto", "Cantidad", "Costo"],
                            "filas": [["Analisis", "1", "1200"], ["Viaticos", "3", "900"]],
                            "orientacion": "portrait",
                        }
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]

        assert isinstance(content, list)
        assert len(content) == 1
        table = content[0]
        assert table["tipo"] == "tabla"
        assert table["titulo"] == "Tabla 6.1 Presupuesto de investigación"
        assert table["id"] == "tab-pres-dinamica"
        assert table["titulo"] == "Tabla 6.1 Presupuesto de investigaciÃ³n"
        assert table["orientacion"] == "portrait"
        assert table["subtipo"] == "presupuesto_investigacion"
        assert table["encabezados"] == [
            "N°",
            "DESCRIPCIÓN DEL GASTO",
            "CANTIDAD",
            "COSTO UNIT. (S/.)",
            "COSTO TOTAL (S/.)",
        ]
        assert table["filas"][0] == ["1. RECURSOS HUMANOS", "", "", "", "2,000.00"]
        assert table["filas"][13] == ["TOTAL GENERAL", "", "", "", "S/. 7,779.00"]
        assert table["filas_categoria"] == [0, 2, 7, 11]
        assert table["fila_total"] == 13
        assert {"fila": 0, "col_inicio": 0, "col_fin": 3, "texto": "1. RECURSOS HUMANOS"} in table["celdas_combinadas"]
        assert {"fila": 13, "col_inicio": 0, "col_fin": 3, "texto": "TOTAL GENERAL"} in table["celdas_combinadas"]
        assert {"fila": 0, "col": 0, "filas_span": 1, "cols_span": 4, "texto": "1. RECURSOS HUMANOS", "bold": True, "alignment": "left"} in table["celdas_fusionadas"]
        assert {"fila": 13, "col": 0, "filas_span": 1, "cols_span": 4, "texto": "TOTAL GENERAL", "bold": True, "alignment": "center"} in table["celdas_fusionadas"]
        assert table["estilo"]["titulo_exacto"] is True
        assert all(block["tipo"] != "parrafo" for block in content)

    def test_budget_section_without_structured_table_raises(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-presupuesto",
                    "path": "VI. PRESUPUESTO",
                    "content": [{"tipo": "tabla", "titulo": "Tabla incompleta", "encabezados": ["A"], "filas": []}],
                }
            ]
        }

        with pytest.raises(ValidationError, match="tabla estructurada valida de presupuesto"):
            validator.validate(ai_result)

    def test_operationalization_section_drops_structured_blocks_even_with_variant_path(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-op",
                    "path": "III. VARIABLES/3.2 Operacionalización de variable",
                    "content": [
                        {
                            "tipo": "parrafo",
                            "texto": "Puente metodologico de operacionalizacion.",
                        },
                        {
                            "tipo": "tabla",
                            "id": "tab-3-1",
                            "titulo": "Tabla 3.1 Operacionalización de variable independiente",
                            "encabezados": [
                                "Variable",
                                "Definición conceptual",
                                "Definición operacional",
                                "Dimensión",
                                "Indicador",
                                "Índice",
                                "Técnica e instrumentos",
                            ],
                            "filas": [
                                [
                                    "RCM",
                                    "Def.",
                                    "Op.",
                                    "Taxonomía",
                                    "Nivel",
                                    "Escala",
                                    "Ficha",
                                ]
                            ],
                            "orientacion": "landscape",
                        },
                        {
                            "tipo": "formula",
                            "texto": "X = Y",
                        },
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert [item["tipo"] for item in content] == ["parrafo"]
        assert "puente metodologico" in content[0]["texto"].lower()

    def test_figure_title_is_derived_from_caption_when_missing(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-figure",
                    "path": "V. RESULTADOS/5.1 Presentacion de resultados",
                    "content": [
                        {
                            "tipo": "figura",
                            "caption": "Figura 2. Modelo predictivo de mantenimiento.",
                        }
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        figure = result["sections"][0]["content"][0]
        assert figure["titulo"] == "Modelo predictivo de mantenimiento."

    def test_reality_problem_quality_gap_is_warning_not_validation_error(self, validator, caplog):
        figures = [
            {
                "tipo": "figura",
                "titulo": f"Figura {index}",
                "caption": f"Figura {index}. Guia tecnica.",
            }
            for index in range(1, 6)
        ]
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-problem",
                    "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                    "content": figures,
                }
            ]
        }

        caplog.set_level(logging.WARNING, logger="app.core.services.ai.output_validator")
        result = validator.validate(ai_result)

        assert result["sections"][0]["sectionId"] == "sec-problem"
        assert "minimo 1300" in caplog.text

    def test_reality_problem_accepts_full_quality_contract(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-problem",
                    "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                    "content": _valid_reality_problem_content(),
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert len([block for block in content if block["tipo"] == "figura"]) == 4

    def test_reality_problem_drops_table_blocks(self, validator, caplog):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-problem",
                    "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                    "content": [
                        {"tipo": "parrafo", "texto": "Diagnostico tecnico suficiente para el problema."},
                        {
                            "tipo": "tabla",
                            "titulo": "Tabla 1.1 Diagrama de Pareto",
                            "encabezados": ["Sistema", "Frecuencia"],
                            "filas": [["Tren de potencia", "42"]],
                        },
                    ],
                }
            ]
        }

        caplog.set_level(logging.WARNING, logger="app.core.services.ai.output_validator")
        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]

        assert all(block["tipo"] != "tabla" for block in content)
        assert "minimo 1300" in caplog.text

    def test_justification_requires_numbered_subheadings(self, validator, caplog):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-justificacion",
                    "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.4 Justificacion",
                    "content": "La justificacion se redacta en parrafos corridos sin subtitulos internos.",
                }
            ]
        }

        caplog.set_level(logging.WARNING, logger="app.core.services.ai.output_validator")
        validator.validate(ai_result)

        assert "faltan subtitulos obligatorios" in caplog.text
        assert "1.4.1 Justificacion normativa" in caplog.text

    def test_delimitations_requires_numbered_subheadings(self, validator, caplog):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-delimitaciones",
                    "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.5 Delimitaciones de la investigacion",
                    "content": "La investigacion se delimita teorica, temporal y espacialmente.",
                }
            ]
        }

        caplog.set_level(logging.WARNING, logger="app.core.services.ai.output_validator")
        validator.validate(ai_result)

        assert "faltan subtitulos obligatorios" in caplog.text
        assert "1.5.1 Delimitacion teorica" in caplog.text

    def test_strips_raw_structured_repr_from_plain_text(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-raw",
                    "path": "I. PLANTEAMIENTO/1.1 Problema",
                    "content": (
                        "Parrafo limpio antes.\n"
                        "[{'tipo': 'tabla', 'id': 'tab_001', 'titulo': 'Tabla rota'}]\n"
                        "{'tipo': 'figura', 'id': 'fig_001', 'caption': 'Figura rota'}\n"
                        "Parrafo limpio despues."
                    ),
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert "tipo" not in content
        assert "tab_001" not in content
        assert "fig_001" not in content
        assert "Parrafo limpio antes." in content
        assert "Parrafo limpio despues." in content

    def test_index_path_forces_empty_content(self, validator):
        """TOC sections are now DROPPED entirely, not just emptied."""
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "INDICE",
                    "content": "No debe aparecer en el indice",
                },
                {
                    "sectionId": "sec-0002",
                    "path": "I. PLANTEAMIENTO",
                    "content": "Contenido valido del capitulo",
                },
            ]
        }

        result = validator.validate(ai_result)
        # sec-0001 was dropped
        assert len(result["sections"]) == 1
        assert result["sections"][0]["sectionId"] == "sec-0002"

    def test_skip_section_token_is_normalized_to_empty(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "I. PLANTEAMIENTO/1.1 Realidad",
                    "content": "<<SKIP_SECTION>>",
                }
            ]
        }
        result = validator.validate(ai_result)
        assert result["sections"][0]["content"] == ""

    def test_abbreviations_are_normalized_to_tab_format(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "PRELIMINARES/ABREVIATURAS",
                    "content": (
                        "IA: Inteligencia Artificial\n"
                        "ERP - Planificacion de recursos empresariales\n"
                        "Organizacion Mundial de la Salud (OMS)"
                    ),
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert "IA\tInteligencia Artificial" in content
        assert "ERP\tPlanificacion de recursos empresariales" in content
        assert "OMS\tOrganizacion Mundial de la Salud" in content

    def test_index_of_abbreviations_forces_empty_content(self, validator):
        """ÍNDICE DE ABREVIATURAS is a TOC heading — dropped entirely."""
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "INDICE DE ABREVIATURAS",
                    "content": "IA: Inteligencia Artificial",
                },
                {
                    "sectionId": "sec-0002",
                    "path": "I. CAPITULO",
                    "content": "Contenido del capitulo real",
                },
            ]
        }

        result = validator.validate(ai_result)
        assert len(result["sections"]) == 1
        assert result["sections"][0]["sectionId"] == "sec-0002"


class TestBuildAiResult:
    def test_build_and_validate(self, validator):
        sections = [
            {"sectionId": "s1", "path": "Cap 1", "content": "Contenido capitulo uno largo."},
        ]
        result = validator.build_ai_result(sections)
        assert "sections" in result
        assert result["sections"][0]["sectionId"] == "s1"

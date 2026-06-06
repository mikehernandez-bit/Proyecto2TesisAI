from app.core.services.institutional_section_service import InstitutionalSectionService


def test_extract_sections_marks_optional_sections_and_excludes_indices():
    service = InstitutionalSectionService()
    definition = {
        "preliminares": {
            "indices": [{"titulo": "INDICE", "items": [{"texto": "I. PLANTEAMIENTO DEL PROBLEMA"}]}],
            "resumen": {"titulo": "RESUMEN"},
            "dedicatoria": {"titulo": "DEDICATORIA"},
            "agradecimientos": {"titulo": "AGRADECIMIENTOS"},
            "introduccion": {"titulo": "INTRODUCCION"},
        },
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Realidad problematica"},
                ],
            },
            {
                "titulo": "ANEXOS",
                "contenido": [
                    {"texto": "Anexo 1"},
                ],
            },
        ],
    }

    sections = service.extract_sections(definition)
    by_path = {item["section_path"]: item for item in sections}

    assert "INDICE" not in by_path
    assert "RESUMEN" in by_path
    assert "DEDICATORIA" in by_path
    assert "AGRADECIMIENTOS" in by_path
    assert "INTRODUCCION" in by_path
    assert "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica" in by_path
    assert "ANEXOS" in by_path
    assert "ANEXOS/Anexo 1" not in by_path
    assert by_path["RESUMEN"]["optional"] is True
    assert by_path["RESUMEN"]["default_selected"] is False
    assert by_path["DEDICATORIA"]["optional"] is True
    assert by_path["AGRADECIMIENTOS"]["optional"] is True
    assert by_path["ANEXOS"]["optional"] is True
    assert by_path["ANEXOS"]["default_selected"] is False
    assert by_path["INTRODUCCION"]["default_selected"] is True
    assert by_path["RESUMEN"]["section_order"] < by_path["INTRODUCCION"]["section_order"]
    assert by_path["INTRODUCCION"]["section_order"] < by_path["ANEXOS"]["section_order"]


def test_build_tree_links_parent_and_children():
    service = InstitutionalSectionService()
    sections = [
        {
            "section_id": "sec-1",
            "section_path": "I. PLANTEAMIENTO DEL PROBLEMA",
            "section_title": "I. PLANTEAMIENTO DEL PROBLEMA",
            "parent_section_path": "",
            "section_level": 1,
            "section_order": 2,
            "optional": False,
            "default_selected": True,
            "source_hints": "",
            "blocks": [],
        },
        {
            "section_id": "sec-2",
            "section_path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
            "section_title": "1.1 Realidad problematica",
            "parent_section_path": "I. PLANTEAMIENTO DEL PROBLEMA",
            "section_level": 2,
            "section_order": 3,
            "optional": False,
            "default_selected": True,
            "source_hints": "",
            "blocks": [],
        },
    ]

    tree = service.build_tree(sections)

    assert len(tree) == 1
    assert tree[0]["section_path"] == "I. PLANTEAMIENTO DEL PROBLEMA"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["section_path"].endswith("1.1 Realidad problematica")


def test_build_tree_preserves_stable_institutional_order():
    service = InstitutionalSectionService()
    sections = [
        {
            "section_id": "sec-0",
            "section_path": "TÍTULO + INFORMACIÓN BÁSICA",
            "section_title": "TÍTULO + INFORMACIÓN BÁSICA",
            "parent_section_path": "",
            "section_level": 1,
            "section_order": -100,
            "optional": False,
            "default_selected": True,
            "source_hints": "",
            "blocks": [],
        },
        {
            "section_id": "sec-2",
            "section_path": "CAPITULO I",
            "section_title": "CAPITULO I",
            "parent_section_path": "",
            "section_level": 1,
            "section_order": 2,
            "optional": False,
            "default_selected": True,
            "source_hints": "",
            "blocks": [],
        },
        {
            "section_id": "sec-1",
            "section_path": "INTRODUCCION",
            "section_title": "INTRODUCCION",
            "parent_section_path": "",
            "section_level": 1,
            "section_order": 1,
            "optional": False,
            "default_selected": True,
            "source_hints": "",
            "blocks": [],
        },
        {
            "section_id": "sec-4",
            "section_path": "CAPITULO I/1.2 Formulacion del problema",
            "section_title": "1.2 Formulacion del problema",
            "parent_section_path": "CAPITULO I",
            "section_level": 2,
            "section_order": 4,
            "optional": False,
            "default_selected": True,
            "source_hints": "",
            "blocks": [],
        },
        {
            "section_id": "sec-3",
            "section_path": "CAPITULO I/1.1 Realidad problematica",
            "section_title": "1.1 Realidad problematica",
            "parent_section_path": "CAPITULO I",
            "section_level": 2,
            "section_order": 3,
            "optional": False,
            "default_selected": True,
            "source_hints": "",
            "blocks": [],
        },
    ]

    tree = service.build_tree(sections)

    assert [item["section_path"] for item in tree] == [
        "TÍTULO + INFORMACIÓN BÁSICA",
        "INTRODUCCION",
        "CAPITULO I",
    ]
    assert [item["section_path"] for item in tree[2]["children"]] == [
        "CAPITULO I/1.1 Realidad problematica",
        "CAPITULO I/1.2 Formulacion del problema",
    ]


def test_extract_sections_excludes_misplaced_chapter_two_matrix_children():
    service = InstitutionalSectionService()
    definition = {
        "cuerpo": [
            {
                "titulo": "II. MARCO TEORICO",
                "contenido": [
                    {
                        "titulo": "2.2 Bases teoricas",
                        "contenido": [
                            {"texto": "Matriz de Consistencia de Implementacion"},
                            {"texto": "Matriz de Operacionalizacion de Diseno"},
                        ],
                    }
                ],
            }
        ]
    }

    sections = service.extract_sections(definition)
    paths = [item["section_path"] for item in sections]

    assert "II. MARCO TEORICO/2.2 Bases teoricas" in paths
    assert all("Matriz de Consistencia" not in path for path in paths)
    assert all("Matriz de Operacionalizacion" not in path for path in paths)


def test_extract_sections_excludes_static_cronograma_resumido_table():
    service = InstitutionalSectionService()
    definition = {
        "cuerpo": [
            {
                "titulo": "IV. METODOLOGIA DEL PROYECTO",
                "contenido": [
                    {"texto": "4.7 Aspectos eticos en Investigacion"},
                    {
                        "tipo": "tabla",
                        "titulo": "Cronograma Resumido de Actividades",
                        "encabezados": ["Actividad", "Mes 1", "Mes 2"],
                        "filas": [["Revision", "X", ""]],
                    },
                ],
            },
            {
                "titulo": "V. CRONOGRAMA DE ACTIVIDADES",
                "contenido": [
                    {"texto": "Cronograma de ejecucion"},
                ],
            },
        ]
    }

    sections = service.extract_sections(definition)
    paths = [item["section_path"] for item in sections]

    assert "IV. METODOLOGIA DEL PROYECTO" in paths
    assert "V. CRONOGRAMA DE ACTIVIDADES" in paths
    assert all(not path.startswith("V. CRONOGRAMA DE ACTIVIDADES/") for path in paths)
    assert all("Cronograma Resumido de Actividades" not in path for path in paths)


def test_extract_sections_sets_source_content_type_from_definition_nodes():
    service = InstitutionalSectionService()
    definition = {
        "cuerpo": [
            {
                "titulo": "V. CRONOGRAMA DE ACTIVIDADES",
                "contenido": [
                    {"texto": "Cronograma de ejecucion"},
                    {
                        "tipo": "tabla",
                        "titulo": "Cronograma Detallado de Actividades",
                        "encabezados": ["Actividad", "Mes 1"],
                        "filas": [["Revision", "X"]],
                    },
                ],
            },
            {
                "titulo": "VI. PRESUPUESTO",
                "contenido": [
                    {"texto": "Recursos y Presupuesto"},
                    {
                        "tipo": "tabla",
                        "titulo": "Presupuesto del Proyecto",
                        "encabezados": ["Rubro", "Costo"],
                        "filas": [["Materiales", "100"]],
                    },
                ],
            },
        ]
    }

    sections = service.extract_sections(definition)
    by_path = {item["section_path"]: item for item in sections}

    assert "V. CRONOGRAMA DE ACTIVIDADES" in by_path
    assert "VI. PRESUPUESTO" in by_path
    assert by_path["V. CRONOGRAMA DE ACTIVIDADES"]["source_content_type"] in {"texto", "tabla"}
    assert by_path["VI. PRESUPUESTO"]["source_content_type"] in {"texto", "tabla"}
    assert all(not key.startswith("V. CRONOGRAMA DE ACTIVIDADES/") for key in by_path)
    assert all(not key.startswith("VI. PRESUPUESTO/") for key in by_path)

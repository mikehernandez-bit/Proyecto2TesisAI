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
            }
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
    assert by_path["RESUMEN"]["optional"] is True
    assert by_path["RESUMEN"]["default_selected"] is False
    assert by_path["DEDICATORIA"]["optional"] is True
    assert by_path["AGRADECIMIENTOS"]["optional"] is True
    assert by_path["INTRODUCCION"]["default_selected"] is True


def test_build_tree_links_parent_and_children():
    service = InstitutionalSectionService()
    sections = [
        {
            "section_id": "sec-1",
            "section_path": "I. PLANTEAMIENTO DEL PROBLEMA",
            "section_title": "I. PLANTEAMIENTO DEL PROBLEMA",
            "parent_section_path": "",
            "section_level": 1,
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

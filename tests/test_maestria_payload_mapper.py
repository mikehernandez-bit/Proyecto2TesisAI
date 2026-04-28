from __future__ import annotations

from app.core.services.maestria_payload_mapper import is_maestria_format


def test_is_maestria_format_accepts_unac_proyecto_de_tesis_category() -> None:
    format_obj = {
        "id": "unac-proyecto-cuant",
        "university": "unac",
        "category": "Proyecto de Tesis",
    }

    assert is_maestria_format(format_obj) is True


def test_is_maestria_format_rejects_non_unac_proyecto_category() -> None:
    format_obj = {
        "id": "otro-proyecto-cuant",
        "university": "otro",
        "category": "Proyecto de Tesis",
    }

    assert is_maestria_format(format_obj) is False

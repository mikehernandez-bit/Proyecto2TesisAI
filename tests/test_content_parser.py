from app.core.services.ai.content_parser import parse_ai_content


def test_parse_ai_content_extracts_formula_json_block():
    content = (
        "Texto previo.\n\n"
        "<<<FORMULA_JSON\n"
        '{"tipo":"formula","id":"eq_2_1_npr","texto":"NPR = S x O x D",'
        '"latex":"NPR = S \\\\times O \\\\times D","numero":"(1)"}\n'
        "FORMULA_JSON>>>\n\n"
        "Texto posterior."
    )

    parsed = parse_ai_content(content)

    assert isinstance(parsed, list)
    assert [block["tipo"] for block in parsed] == ["parrafo", "formula", "parrafo"]
    assert parsed[1]["id"] == "eq_2_1_npr"
    assert parsed[1]["alineacion"] == "center"


def test_parse_ai_content_strips_outer_fences_and_normalizes_schedule_marks():
    content = (
        "```json\n"
        "<<<TABLE_JSON\n"
        '{"tipo":"tabla","id":"tabla_5_1_cronograma_actividades","titulo":"Tabla 5.1 Cronograma de actividades",'
        '"encabezados":["FASES Y ACTIVIDADES","2025","","","","","","","","","","",""],'
        '"filas":[["","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Set","Oct","Nov","Dic"],'
        '["1. Fase de prueba","","â—","X","","","","","","","","",""],'
        '["1.1. Actividad tecnica","","x","•","","","","","","","","",""]],'
        '"orientacion":"landscape","subtipo":"cronograma_actividades","anio":"2025","meses":["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Set","Oct","Nov","Dic"],'
        '"filas_fase":[1,5,9,13,17,21,26,30],"celdas_combinadas":[{"fila":-1,"col_inicio":1,"col_fin":12,"texto":"2025"}],'
        '"celdas_fusionadas":[{"fila":-1,"col":0,"filas_span":2,"cols_span":1,"texto":"FASES Y ACTIVIDADES"}]}\n'
        "TABLE_JSON>>>\n"
        "```"
    )

    parsed = parse_ai_content(content)

    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["tipo"] == "tabla"
    assert parsed[0]["filas"][1][2] == "●"
    assert parsed[0]["filas"][1][3] == "●"
    assert parsed[0]["filas"][2][2] == "●"
    assert parsed[0]["filas"][2][3] == "●"

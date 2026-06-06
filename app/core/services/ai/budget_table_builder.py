"""Deterministic builder for UNAC project budget tables."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence

CANONICAL_TABLE_ID = "tabla_6_1_presupuesto_investigacion"
CANONICAL_TABLE_TITLE = "Tabla 6.1 Presupuesto de investigacion"
CANONICAL_CHAPTER_TITLE = "VI. PRESUPUESTO"
DEFAULT_SUBTYPE = "presupuesto_plan"
_BLUEPRINT_SUBTYPES = {"presupuesto_plan", "budget_plan"}
_MONEY_RE = re.compile(r"[\d,.]+")

DEFAULT_BUDGET_PLAN: Dict[str, Any] = {
    "tipo": "tabla",
    "subtipo": DEFAULT_SUBTYPE,
    "categorias": [
        {
            "numero": 1,
            "titulo": "RECURSOS HUMANOS",
            "items": [
                {
                    "numero": "1.1",
                    "descripcion": "Investigador (dedicacion/asistencia de investigacion)",
                    "cantidad": "1",
                    "costo_unitario": "2,000.00",
                    "costo_total": "2,000.00",
                }
            ],
        },
        {
            "numero": 2,
            "titulo": "RECURSOS DE INVESTIGACION",
            "items": [
                {
                    "numero": "2.1",
                    "descripcion": "Equipo de computo para procesamiento y analisis (Laptop)",
                    "cantidad": "1",
                    "costo_unitario": "2,999.00",
                    "costo_total": "2,999.00",
                },
                {
                    "numero": "2.2",
                    "descripcion": "Servicio de Internet (Datos)",
                    "cantidad": "12",
                    "costo_unitario": "50.00",
                    "costo_total": "600.00",
                },
                {
                    "numero": "2.3",
                    "descripcion": "Movilidad y Viaticos (Lima-Junín)",
                    "cantidad": "4",
                    "costo_unitario": "250.00",
                    "costo_total": "1,000.00",
                },
                {
                    "numero": "2.4",
                    "descripcion": "Software / licencias (Office / almacenamiento nube o equivalente)",
                    "cantidad": "1",
                    "costo_unitario": "250.00",
                    "costo_total": "250.00",
                },
            ],
        },
        {
            "numero": 3,
            "titulo": "RECURSOS CONSUMIBLES",
            "items": [
                {
                    "numero": "3.1",
                    "descripcion": "Material de escritorio (papel, boligrafos, etc.)",
                    "cantidad": "1",
                    "costo_unitario": "150.00",
                    "costo_total": "150.00",
                },
                {
                    "numero": "3.2",
                    "descripcion": "Impresiones y anillados (incluye version final)",
                    "cantidad": "1",
                    "costo_unitario": "350.00",
                    "costo_total": "350.00",
                },
                {
                    "numero": "3.3",
                    "descripcion": "Dispositivo de almacenamiento (USB)",
                    "cantidad": "1",
                    "costo_unitario": "60.00",
                    "costo_total": "60.00",
                },
            ],
        },
        {
            "numero": 4,
            "titulo": "CONTINGENCIA / IMPREVISTOS",
            "items": [
                {
                    "numero": "4.1",
                    "descripcion": "Imprevistos (5% del subtotal)",
                    "cantidad": "1",
                    "costo_unitario": "370.00",
                    "costo_total": "370.00",
                }
            ],
        },
    ],
}

EXPECTED_ITEM_COUNTS = (1, 4, 3, 1)
EXPECTED_SUBTOTALS = ["2,000.00", "4,849.00", "560.00", "370.00"]
EXPECTED_TOTAL = "S/. 7,779.00"
HEADER_ROW = ["N°", "DESCRIPCION DEL GASTO", "CANTIDAD", "COSTO UNIT. (S/.)", "COSTO TOTAL (S/.)"]


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_money(value: Any, *, with_prefix: bool = False) -> str:
    text = _text(value)
    if not text:
        return EXPECTED_TOTAL if with_prefix else "0.00"
    match = _MONEY_RE.search(text.replace(" ", ""))
    if not match:
        return EXPECTED_TOTAL if with_prefix else "0.00"
    amount = match.group(0)
    if amount.count(",") == 0 and amount.count(".") > 1:
        amount = amount.replace(".", "")
    if amount.count(",") > 0 and amount.count(".") == 0:
        amount = amount.replace(",", ".")
    try:
        numeric = float(amount.replace(",", ""))
    except ValueError:
        numeric = 0.0
    rendered = f"{numeric:,.2f}"
    return f"S/. {rendered}" if with_prefix else rendered


def build_synthetic_budget_plan(values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return deepcopy(DEFAULT_BUDGET_PLAN)


def extract_budget_plan_from_content(content: Any) -> Optional[Dict[str, Any]]:
    blocks: Sequence[Any] = content if isinstance(content, list) else [content]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = _text(block.get("tipo")).lower()
        block_subtype = _text(block.get("subtipo")).lower()
        if block_type == DEFAULT_SUBTYPE or block_subtype in _BLUEPRINT_SUBTYPES:
            return deepcopy(block)
    return None


def validate_budget_plan(plan: Dict[str, Any]) -> List[str]:
    if not isinstance(plan, dict):
        return ["presupuesto_plan_invalido"]
    categories = plan.get("categorias")
    if not isinstance(categories, list) or len(categories) != 4:
        return ["faltan_categorias"]
    errors: List[str] = []
    for idx, (category, expected_count) in enumerate(zip(categories, EXPECTED_ITEM_COUNTS), start=1):
        if not isinstance(category, dict):
            errors.append("categoria_invalida")
            continue
        if not _text(category.get("titulo")):
            errors.append("categoria_sin_titulo")
        items = category.get("items")
        if not isinstance(items, list) or len(items) != expected_count:
            errors.append("cantidad_items_invalida")
            continue
        for item in items:
            if not isinstance(item, dict):
                errors.append("item_invalido")
                continue
            if not _text(item.get("descripcion")):
                errors.append("item_sin_descripcion")
    return list(dict.fromkeys(errors))


def _normalized_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    errors = validate_budget_plan(plan)
    if errors:
        raise ValueError(", ".join(errors))
    categories: List[Dict[str, Any]] = []
    for idx, (category, expected_count, subtotal) in enumerate(
        zip(plan["categorias"], EXPECTED_ITEM_COUNTS, EXPECTED_SUBTOTALS),
        start=1,
    ):
        items_out: List[Dict[str, Any]] = []
        for item_idx, item in enumerate(category["items"][:expected_count], start=1):
            number = f"{idx}.{item_idx}"
            default_item = DEFAULT_BUDGET_PLAN["categorias"][idx - 1]["items"][item_idx - 1]
            items_out.append(
                {
                    "numero": number,
                    "descripcion": _text(item.get("descripcion")),
                    "cantidad": _text(item.get("cantidad") or default_item["cantidad"]),
                    "costo_unitario": _normalize_money(item.get("costo_unitario") or default_item["costo_unitario"]),
                    "costo_total": _normalize_money(item.get("costo_total") or default_item["costo_total"]),
                }
            )
        categories.append(
            {
                "numero": idx,
                "titulo": f"{idx}. {_text(category.get('titulo'))}",
                "subtotal": subtotal,
                "items": items_out,
            }
        )
    return {"tipo": "tabla", "subtipo": DEFAULT_SUBTYPE, "categorias": categories}


def build_budget_table_from_plan(plan: Dict[str, Any], *, values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    normalized = _normalized_plan(plan)
    rows: List[List[str]] = []
    category_rows: List[int] = []
    merged_cells: List[Dict[str, Any]] = []
    fused_cells: List[Dict[str, Any]] = []

    row_index = 0
    for category in normalized["categorias"]:
        rows.append([category["titulo"], "", "", "", category["subtotal"]])
        category_rows.append(row_index)
        merged_cells.append({"fila": row_index, "col_inicio": 0, "col_fin": 3, "texto": category["titulo"]})
        fused_cells.append(
            {
                "fila": row_index,
                "col": 0,
                "filas_span": 1,
                "cols_span": 4,
                "texto": category["titulo"],
                "bold": True,
                "alignment": "left",
            }
        )
        row_index += 1
        for item in category["items"]:
            rows.append(
                [
                    item["numero"],
                    item["descripcion"],
                    item["cantidad"],
                    item["costo_unitario"],
                    item["costo_total"],
                ]
            )
            row_index += 1

    rows.append(["TOTAL GENERAL", "", "", "", EXPECTED_TOTAL])
    merged_cells.append({"fila": 13, "col_inicio": 0, "col_fin": 3, "texto": "TOTAL GENERAL"})
    fused_cells.append(
        {
            "fila": 13,
            "col": 0,
            "filas_span": 1,
            "cols_span": 4,
            "texto": "TOTAL GENERAL",
            "bold": True,
            "alignment": "center",
        }
    )

    return {
        "tipo": "tabla",
        "id": CANONICAL_TABLE_ID,
        "titulo": CANONICAL_TABLE_TITLE,
        "encabezados": list(HEADER_ROW),
        "filas": rows,
        "orientacion": "portrait",
        "subtipo": "presupuesto_investigacion",
        "filas_categoria": list(category_rows),
        "fila_total": 13,
        "celdas_combinadas": merged_cells,
        "celdas_fusionadas": fused_cells,
        "estilo": {
            "modelo_referencia": "presupuesto_investigacion_vertical.docx",
            "titulo_capitulo": CANONICAL_CHAPTER_TITLE,
            "titulo_exacto": True,
            "titulo_tamano_pt": 10,
            "titulo_space_after_pt": 10,
            "ancho_tabla": "100%",
            "ancho_columnas": [1.4, 8, 2, 3.2, 3.2],
            "orientacion_pagina": "portrait",
            "encabezados_negrita": True,
            "categorias_negrita": True,
            "total_negrita": True,
            "alineacion_descripcion": "left",
            "alineacion_numeros": "center",
            "alineacion_costos": "right",
            "bordes": "grid",
            "fuente_tamano_pt": 9,
            "fuente_encabezado_pt": 8.5,
            "fuente_categoria_pt": 9,
            "fuente_total_pt": 9,
        },
    }


def salvage_budget_plan_from_legacy_table(
    table: Dict[str, Any], *, values: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    rows = table.get("filas")
    if not isinstance(rows, list) or not rows:
        return None
    plan = build_synthetic_budget_plan(values)
    # Reuse any non-empty legacy descriptions to avoid losing topic-specific wording.
    descriptions: List[str] = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        if len(row) >= 2:
            desc = _text(row[1])
        else:
            desc = _text(row[0])
        if desc and "total" not in desc.lower() and "categoria" not in desc.lower():
            descriptions.append(desc)
    if not descriptions:
        return plan

    flat_items = [item for category in plan["categorias"] for item in category["items"]]
    for item, desc in zip(flat_items, descriptions):
        item["descripcion"] = desc
    return plan

"""
Definition Compiler - Compiles format definitions into document IR.

This module extracts the hierarchical structure from format definitions
and produces an intermediate representation (IR) suitable for generating
DOCX and PDF documents.

EXCLUDED keys (instruction/guidance, NOT document content):
- nota, instruccion, instruccion_detallada, guia, ejemplo, comentario

INCLUDED keys (structural):
- titulo, title, texto (section headings)
- cuerpo, preliminares, finales, capitulos, contenido, secciones, subsecciones
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.core.services.indices_normalizer import normalize_definition
from app.core.services.toc_detector import is_toc_title as _shared_is_toc_title


class IRNodeType(Enum):
    """Types of IR nodes for document generation."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE_PLACEHOLDER = "table_placeholder"
    FIGURE_PLACEHOLDER = "figure_placeholder"
    TOC_PLACEHOLDER = "toc_placeholder"
    LIST_TABLES = "list_tables"
    LIST_FIGURES = "list_figures"
    LIST_ABBREVIATIONS = "list_abbreviations"
    PAGE_BREAK = "page_break"


@dataclass
class IRNode:
    """A node in the document intermediate representation."""

    node_type: IRNodeType
    text: str = ""
    level: int = 1  # Heading level (1-6)
    number: int = 0  # For table/figure numbering
    caption: str = ""  # For table/figure captions


@dataclass
class DocumentIR:
    """Complete document intermediate representation."""

    title: str = ""
    nodes: List[IRNode] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)  # Table titles for list
    figures: List[str] = field(default_factory=list)  # Figure titles for list


# Keys that contain guidance/instructions - NOT printed in final doc
EXCLUDED_KEYS = frozenset(
    {
        "nota",
        "nota_capitulo",
        "instruccion",
        "instruccion_detallada",
        "guia",
        "ejemplo",
        "comentario",
        "placeholder",
        "tipo_vista",
        "vista_previa",
        "_meta",
        "version",
        "descripcion",
    }
)

# Keys that might contain structural content
STRUCTURAL_KEYS = frozenset(
    {
        "cuerpo",
        "preliminares",
        "finales",
        "capitulos",
        "contenido",
        "secciones",
        "subsecciones",
        "children",
        "items",
        "anexos",
        "lista",
    }
)

# Keys that indicate headings/titles
TITLE_KEYS = frozenset(
    {
        "titulo",
        "title",
        "titulo_seccion",
        "texto",
    }
)

# Keys that indicate tables
TABLE_KEYS = frozenset(
    {
        "tabla",
        "tablas",
        "tablas_especiales",
        "matriz",
        "cuadro",
    }
)

# Figure keys
FIGURE_KEYS = frozenset(
    {
        "figura",
        "figuras",
        "imagen",
        "imagenes",
        "grafico",
    }
)

# Structural keys used to discover real section hierarchy (ordered traversal)
SECTION_CONTAINER_KEYS = frozenset(
    {
        "preliminares",
        "cuerpo",
        "finales",
        "capitulos",
        "contenido",
        "items",
        "secciones",
        "subsecciones",
        "lista",
        "anexos",
        "indices",
    }
)

# Branches that should never be sent to AI content generation.
# They are rendered by Word/GicaTesis itself (TOC/lists/media placeholders).
NON_GENERATIVE_BRANCH_KEYS = frozenset(
    {
        "indices",
        "indice",
        "indice_de_tablas",
        "indice_de_figuras",
        "tabla_de_contenido",
        "toc",
        "tabla",
        "tablas",
        "figura",
        "figuras",
        "imagen",
        "imagenes",
        "grafico",
    }
)

NON_GENERATIVE_SECTION_TITLES = frozenset(
    {
        "indice",
        "indice de contenido",
        "indice de contenidos",
        "indice de tablas",
        "indice de figuras",
        "indice de abreviaturas",
        "tabla de contenido",
        "tabla de contenidos",
        "table of contents",
        "toc",
    }
)


def _is_excluded_key(key: str) -> bool:
    """Check if a key should be excluded from output."""
    key_lower = key.lower()
    return key_lower in EXCLUDED_KEYS or key_lower.startswith("_")


def _extract_title(obj: Dict[str, Any]) -> Optional[str]:
    """Extract title from an object, checking various keys."""
    for key in TITLE_KEYS:
        if key in obj:
            val = obj[key]
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _normalize_token(value: str) -> str:
    """Normalize labels for accent-insensitive comparisons."""
    lowered = (value or "").strip().lower()
    if not lowered:
        return ""
    ascii_only = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split())


def _is_non_generative_branch(ancestor_keys: List[str]) -> bool:
    return any(key in NON_GENERATIVE_BRANCH_KEYS for key in ancestor_keys)


def _is_non_generative_title(title: str) -> bool:
    normalized = _normalize_token(title)
    if not normalized:
        return False
    if normalized in NON_GENERATIVE_SECTION_TITLES:
        return True
    # Shared detector covers accent variants and extra patterns (e.g. "toc").
    if _shared_is_toc_title(title):
        return True
    # Skip media/list rows that often appear as auto-generated placeholders.
    if normalized.startswith("tabla ") or normalized.startswith("figura "):
        return True
    return False


def _compile_section(
    obj: Any,
    nodes: List[IRNode],
    tables: List[str],
    figures: List[str],
    level: int = 1,
    table_counter: List[int] = None,
    figure_counter: List[int] = None,
) -> None:
    """Recursively compile a section into IR nodes."""
    if table_counter is None:
        table_counter = [0]
    if figure_counter is None:
        figure_counter = [0]

    if isinstance(obj, dict):
        # Extract title if present
        title = _extract_title(obj)
        if title:
            nodes.append(
                IRNode(
                    node_type=IRNodeType.HEADING,
                    text=title,
                    level=min(level, 6),
                )
            )
            # Add AI placeholder below heading
            nodes.append(
                IRNode(
                    node_type=IRNodeType.PARAGRAPH,
                    text="[Contenido generado por IA - simulacion]",
                )
            )

        # Process child keys
        for key, value in obj.items():
            key_lower = key.lower()

            # Skip excluded keys
            if _is_excluded_key(key):
                continue

            # Skip title keys (already processed)
            if key_lower in TITLE_KEYS:
                continue

            # Check for tables
            if key_lower in TABLE_KEYS:
                table_counter[0] += 1
                table_title = f"Tabla {table_counter[0]}: {key.title()}"
                tables.append(table_title)
                nodes.append(
                    IRNode(
                        node_type=IRNodeType.TABLE_PLACEHOLDER,
                        number=table_counter[0],
                        caption=f"{table_title} [SIMULACION]",
                    )
                )
                continue

            # Check for figures
            if key_lower in FIGURE_KEYS:
                figure_counter[0] += 1
                figure_title = f"Figura {figure_counter[0]}: {key.title()}"
                figures.append(figure_title)
                nodes.append(
                    IRNode(
                        node_type=IRNodeType.FIGURE_PLACEHOLDER,
                        number=figure_counter[0],
                        caption=f"{figure_title} [SIMULACION]",
                    )
                )
                continue

            # Recurse into structural keys
            if key_lower in STRUCTURAL_KEYS or isinstance(value, (dict, list)):
                _compile_section(
                    value,
                    nodes,
                    tables,
                    figures,
                    level=level + 1,
                    table_counter=table_counter,
                    figure_counter=figure_counter,
                )

    elif isinstance(obj, list):
        for item in obj:
            _compile_section(
                item,
                nodes,
                tables,
                figures,
                level=level,
                table_counter=table_counter,
                figure_counter=figure_counter,
            )


_DIRECTIVE_TYPE_TO_IR: Dict[str, IRNodeType] = {
    "toc": IRNodeType.TOC_PLACEHOLDER,
    "toc_tables": IRNodeType.LIST_TABLES,
    "toc_figures": IRNodeType.LIST_FIGURES,
    "toc_abbreviations": IRNodeType.LIST_ABBREVIATIONS,
}


def _emit_toc_directives(directives: List[Dict[str, Any]], nodes: List[IRNode]) -> None:
    """Convert normalised TOC directive blocks into IR nodes."""
    for directive in directives:
        dtype = directive.get("type", "toc")
        title = directive.get("title", "")
        node_type = _DIRECTIVE_TYPE_TO_IR.get(dtype, IRNodeType.TOC_PLACEHOLDER)
        nodes.append(IRNode(node_type=node_type, text=title))


def compile_definition_to_ir(definition: Dict[str, Any]) -> DocumentIR:
    """
    Compile a format definition dictionary into document IR.

    Runs the indices normalizer first so that legacy ``indices`` shapes
    (dict or array-with-pag) are converted into ``{type: "toc", ...}``
    directive blocks before compilation.

    Args:
        definition: The raw format definition (JSON loaded from file).

    Returns:
        DocumentIR with structured content for document generation.
    """
    # --- normalise legacy indices → {type: "toc"} directives ---
    definition = normalize_definition(definition)

    ir = DocumentIR()
    table_counter = [0]
    figure_counter = [0]

    # Extract document title from _meta if available
    meta = definition.get("_meta", {})
    ir.title = meta.get("title", "Documento Simulado")

    # --- Emit TOC / list nodes from normalised directives ----------------
    preliminares = definition.get("preliminares")
    indices_directives: Optional[List[Dict[str, Any]]] = None
    if isinstance(preliminares, dict):
        raw_indices = preliminares.get("indices")
        if (
            isinstance(raw_indices, list)
            and raw_indices
            and isinstance(raw_indices[0], dict)
            and "type" in raw_indices[0]
        ):
            indices_directives = raw_indices

    if indices_directives:
        _emit_toc_directives(indices_directives, ir.nodes)
    else:
        # Fallback: always emit at least a default TOC placeholder
        ir.nodes.append(
            IRNode(
                node_type=IRNodeType.TOC_PLACEHOLDER,
                text="TABLA DE CONTENIDO",
            )
        )

    # Process preliminares (skip indices — already processed above)
    if isinstance(preliminares, dict):
        for key, value in preliminares.items():
            if key.lower() == "indices":
                continue  # already handled
            if _is_excluded_key(key):
                continue
            _compile_section(
                value,
                ir.nodes,
                ir.tables,
                ir.figures,
                level=2,
                table_counter=table_counter,
                figure_counter=figure_counter,
            )

    # Process cuerpo (main body - array of chapters)
    cuerpo = definition.get("cuerpo")
    if isinstance(cuerpo, list):
        for chapter in cuerpo:
            _compile_section(
                chapter,
                ir.nodes,
                ir.tables,
                ir.figures,
                level=1,
                table_counter=table_counter,
                figure_counter=figure_counter,
            )

    # Process finales
    finales = definition.get("finales")
    if finales:
        _compile_section(
            finales,
            ir.nodes,
            ir.tables,
            ir.figures,
            level=1,
            table_counter=table_counter,
            figure_counter=figure_counter,
        )

    # If tables/figures were discovered in the body but no LIST_TABLES /
    # LIST_FIGURES directive existed, inject them after the TOC nodes.
    existing_types = {n.node_type for n in ir.nodes}
    _TOC_IR_TYPES = (
        IRNodeType.TOC_PLACEHOLDER,
        IRNodeType.LIST_TABLES,
        IRNodeType.LIST_FIGURES,
        IRNodeType.LIST_ABBREVIATIONS,
    )
    insert_pos = 0
    for i, n in enumerate(ir.nodes):
        if n.node_type in _TOC_IR_TYPES:
            insert_pos = i + 1
        else:
            break

    if ir.tables and IRNodeType.LIST_TABLES not in existing_types:
        ir.nodes.insert(
            insert_pos,
            IRNode(
                node_type=IRNodeType.LIST_TABLES,
                text="LISTA DE TABLAS (simulacion)",
            ),
        )
        insert_pos += 1

    if ir.figures and IRNodeType.LIST_FIGURES not in existing_types:
        ir.nodes.insert(
            insert_pos,
            IRNode(
                node_type=IRNodeType.LIST_FIGURES,
                text="LISTA DE FIGURAS (simulacion)",
            ),
        )

    return ir


def get_heading_titles(ir: DocumentIR) -> List[str]:
    """Extract all heading titles from the IR for logging/debugging."""
    return [node.text for node in ir.nodes if node.node_type == IRNodeType.HEADING]


def _normalize_text(value: Any) -> str:
    """Normalize section text for stable section paths."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _extract_section_title(section: Dict[str, Any]) -> str:
    """Extract the canonical title for a structural section node."""
    for key in ("titulo", "title", "titulo_seccion", "texto"):
        text = _normalize_text(section.get(key))
        if text:
            return text
    return ""


def _build_section_index_recursive(
    obj: Any,
    out: List[Dict[str, Any]],
    path_stack: List[str],
    level: int,
    in_structure: bool,
    ancestor_keys: List[str],
) -> None:
    """Traverse a definition and emit ordered section index entries."""
    if isinstance(obj, list):
        for item in obj:
            _build_section_index_recursive(
                item,
                out=out,
                path_stack=path_stack,
                level=level,
                in_structure=in_structure,
                ancestor_keys=ancestor_keys,
            )
        return

    if not isinstance(obj, dict):
        return

    title = _extract_section_title(obj) if in_structure else ""
    next_stack = path_stack
    next_level = level

    in_non_generative_branch = _is_non_generative_branch(ancestor_keys)
    should_emit = bool(title) and not in_non_generative_branch and not _is_non_generative_title(title)

    if should_emit:
        next_stack = path_stack + [title]
        section_id = f"sec-{len(out) + 1:04d}"

        # Collect guidance fields for AI context (excluded from final doc
        # but invaluable for generating accurate section content).
        hints: List[str] = []
        for hint_key in ("instruccion_detallada", "nota", "nota_capitulo"):
            val = obj.get(hint_key)
            if isinstance(val, str) and val.strip():
                hints.append(val.strip())

        out.append(
            {
                "sectionId": section_id,
                "path": "/".join(next_stack),
                "level": max(1, min(level, 6)),
                "kind": "heading",
                "title": title,
                "hints": "\n".join(hints) if hints else "",
            }
        )
        next_level = min(level + 1, 6)
    elif title:
        # Keep stack level stable for skipped headings; children preserve parent path.
        next_stack = path_stack

    for key, value in obj.items():
        key_lower = key.lower()

        if _is_excluded_key(key) or key_lower in TITLE_KEYS:
            continue
        if not isinstance(value, (dict, list)):
            continue

        # Skip non-generative branches entirely (TOC, media placeholders, etc.).
        if key_lower in NON_GENERATIVE_BRANCH_KEYS:
            continue

        child_in_structure = in_structure or key_lower in SECTION_CONTAINER_KEYS
        child_ancestor_keys = ancestor_keys + [key_lower]
        _build_section_index_recursive(
            value,
            out=out,
            path_stack=next_stack,
            level=next_level if child_in_structure else level,
            in_structure=child_in_structure,
            ancestor_keys=child_ancestor_keys,
        )


def compile_definition_to_section_index(definition: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Compile a format definition into an ordered section index.

    Runs the indices normalizer first. Output entries are stable and
    mapped by path/sectionId, never by title alone.
    """
    definition = normalize_definition(definition)
    out: List[Dict[str, Any]] = []
    _build_section_index_recursive(
        definition,
        out=out,
        path_stack=[],
        level=1,
        in_structure=False,
        ancestor_keys=[],
    )
    return out

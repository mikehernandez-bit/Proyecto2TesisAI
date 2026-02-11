"""
Simulation Artifact Service - Generates structured DOCX/PDF from format definitions.

This module builds simulated documents that respect the format's hierarchical
structure. It extracts headings, sections, and placeholders from the format
definition rather than using generic placeholder content.

IMPORTANT: This does NOT print instruction/guidance content (nota, instruccion_detallada, etc.)
Those keys are for human guidance, not document content.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

from app.core.services.definition_compiler import (
    compile_definition_to_ir,
    get_heading_titles,
    DocumentIR,
    IRNode,
    IRNodeType,
)


def _project_values(project: Dict[str, Any]) -> Dict[str, Any]:
    values = project.get("values")
    if isinstance(values, dict):
        return values
    values = project.get("variables")
    if isinstance(values, dict):
        return values
    return {}


def _safe_project_id(project: Dict[str, Any]) -> str:
    return str(project.get("id") or "unknown")


def _output_dir() -> Path:
    out = Path("outputs") / "simulation"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _get_format_definition(project: Dict[str, Any]) -> Dict[str, Any]:
    """Extract format definition from project data."""
    # Try format_detail first (populated by router)
    format_detail = project.get("format_detail")
    if isinstance(format_detail, dict):
        definition = format_detail.get("definition")
        if isinstance(definition, dict) and definition:
            return definition

    # Fallback to direct definition field
    definition = project.get("definition")
    if isinstance(definition, dict) and definition:
        return definition

    return {}


def _heading_level_to_style(level: int) -> str:
    """Map heading level to Word style name."""
    if level == 1:
        return "Heading 1"
    elif level == 2:
        return "Heading 2"
    elif level == 3:
        return "Heading 3"
    else:
        return "Heading 4"


def _render_ir_to_docx(doc: Document, ir: DocumentIR, tables_list: List[str], figures_list: List[str]) -> None:
    """Render IR nodes to a python-docx Document."""
    for node in ir.nodes:
        if node.node_type == IRNodeType.TOC_PLACEHOLDER:
            doc.add_heading(node.text, level=1)
            doc.add_paragraph("(Actualizar tabla de contenido en Word)")
            doc.add_paragraph("")  # Spacing

        elif node.node_type == IRNodeType.LIST_TABLES:
            doc.add_heading(node.text, level=1)
            for i, table_title in enumerate(tables_list, 1):
                doc.add_paragraph(f"{table_title}.....pag X", style="List Number")
            doc.add_paragraph("")

        elif node.node_type == IRNodeType.LIST_FIGURES:
            doc.add_heading(node.text, level=1)
            for i, fig_title in enumerate(figures_list, 1):
                doc.add_paragraph(f"{fig_title}.....pag X", style="List Number")
            doc.add_paragraph("")

        elif node.node_type == IRNodeType.HEADING:
            doc.add_heading(node.text, level=min(node.level, 4))

        elif node.node_type == IRNodeType.PARAGRAPH:
            p = doc.add_paragraph(node.text)
            p.paragraph_format.first_line_indent = Inches(0.5)

        elif node.node_type == IRNodeType.TABLE_PLACEHOLDER:
            # Add caption before table
            caption = doc.add_paragraph(node.caption)
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # Add placeholder table (2x2)
            table = doc.add_table(rows=2, cols=2)
            table.style = "Table Grid"
            for row in table.rows:
                for cell in row.cells:
                    cell.text = "[Datos simulados]"
            doc.add_paragraph("")  # Spacing

        elif node.node_type == IRNodeType.FIGURE_PLACEHOLDER:
            # Add figure placeholder paragraph
            fig_para = doc.add_paragraph()
            fig_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = fig_para.add_run("[Figura simulada - insertar imagen aqui]")
            run.italic = True
            # Add caption below
            caption = doc.add_paragraph(node.caption)
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.add_paragraph("")  # Spacing

        elif node.node_type == IRNodeType.PAGE_BREAK:
            doc.add_page_break()


def build_simulated_docx(project: Dict[str, Any], run_id: Optional[str] = None) -> Path:
    """
    Build a structured DOCX file based on the format definition.

    The document will include:
    - Headings from the format structure
    - AI placeholder text under each heading
    - Table and figure placeholders with captions
    - List of tables and figures
    """
    project_id = _safe_project_id(project)
    output = _output_dir() / f"simulated-{project_id}.docx"
    run_id_value = run_id or str(project.get("run_id") or "sim-local")
    definition = _get_format_definition(project)

    doc = Document()

    # If we have a definition, compile it to IR and render
    if definition:
        ir = compile_definition_to_ir(definition)

        # Title page
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_para.add_run(ir.title or "Documento Simulado")
        run.bold = True
        run.font.size = Pt(16)

        doc.add_paragraph("")
        meta_para = doc.add_paragraph()
        meta_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta_para.add_run("SIMULACION GicaGen\n")
        meta_para.add_run(f"projectId: {project_id}\n")
        meta_para.add_run(f"runId: {run_id_value}")

        doc.add_page_break()

        # Render document structure from IR
        _render_ir_to_docx(doc, ir, ir.tables, ir.figures)

    else:
        # Fallback: generic placeholder document
        doc.add_heading("GicaGen - Simulacion", level=1)
        doc.add_paragraph("Documento placeholder (sin definition disponible).")
        doc.add_paragraph(f"projectId: {project_id}")
        doc.add_paragraph(f"runId: {run_id_value}")

        # Add values section
        doc.add_heading("Valores", level=2)
        values = _project_values(project)
        if not values:
            doc.add_paragraph("Sin valores.")
        for key, value in values.items():
            doc.add_paragraph(f"{key}: {value}", style="List Bullet")

    doc.save(str(output))
    return output


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_structured_pdf(ir: DocumentIR, project_id: str, run_id: str) -> bytes:
    """Build a PDF with structure from IR."""
    lines: List[str] = []

    # Title
    lines.append(ir.title or "Documento Simulado")
    lines.append("")
    lines.append("SIMULACION GicaGen")
    lines.append(f"projectId: {project_id}")
    lines.append(f"runId: {run_id}")
    lines.append("")
    lines.append("=" * 40)
    lines.append("")

    # Render nodes
    for node in ir.nodes:
        if node.node_type == IRNodeType.TOC_PLACEHOLDER:
            lines.append(f"== {node.text} ==")
            lines.append("(Actualizar en Word)")
            lines.append("")

        elif node.node_type == IRNodeType.LIST_TABLES:
            lines.append(f"== {node.text} ==")
            for i, table in enumerate(ir.tables, 1):
                lines.append(f"  {i}. {table}")
            lines.append("")

        elif node.node_type == IRNodeType.LIST_FIGURES:
            lines.append(f"== {node.text} ==")
            for i, fig in enumerate(ir.figures, 1):
                lines.append(f"  {i}. {fig}")
            lines.append("")

        elif node.node_type == IRNodeType.HEADING:
            prefix = "#" * min(node.level, 4)
            lines.append(f"{prefix} {node.text}")

        elif node.node_type == IRNodeType.PARAGRAPH:
            lines.append(f"    {node.text}")
            lines.append("")

        elif node.node_type == IRNodeType.TABLE_PLACEHOLDER:
            lines.append(f"  [{node.caption}]")
            lines.append("  +-----+-----+")
            lines.append("  |Dato1|Dato2|")
            lines.append("  +-----+-----+")
            lines.append("")

        elif node.node_type == IRNodeType.FIGURE_PLACEHOLDER:
            lines.append(f"  [{node.caption}]")
            lines.append("")

    return _build_minimal_pdf(lines)


def _build_minimal_pdf(lines: List[str]) -> bytes:
    """Build a minimal valid PDF file."""
    content_lines: List[str] = [
        "BT",
        "/F1 10 Tf",
        "50 790 Td",
    ]
    first = True
    for raw in lines:
        line = _pdf_escape(str(raw)[:80])  # Limit line length
        if first:
            content_lines.append(f"({line}) Tj")
            first = False
        else:
            content_lines.append("0 -14 Td")
            content_lines.append(f"({line}) Tj")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: List[bytes] = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(
        b"5 0 obj << /Length " + str(len(content)).encode("ascii") + b" >> stream\n" + content + b"\nendstream endobj\n"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)

    xref_start = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    out.extend(
        (
            "trailer << /Size {size} /Root 1 0 R >>\n"
            "startxref\n"
            "{xref}\n"
            "%%EOF\n"
        ).format(size=len(objects) + 1, xref=xref_start).encode("ascii")
    )
    return bytes(out)


def build_simulated_pdf(project: Dict[str, Any], run_id: Optional[str] = None) -> Path:
    """
    Build a structured PDF file based on the format definition.

    The PDF mirrors the DOCX structure with headings and placeholders.
    """
    project_id = _safe_project_id(project)
    output = _output_dir() / f"simulated-{project_id}.pdf"
    run_id_value = run_id or str(project.get("run_id") or "sim-local")
    definition = _get_format_definition(project)

    if definition:
        ir = compile_definition_to_ir(definition)
        pdf_bytes = _build_structured_pdf(ir, project_id, run_id_value)
    else:
        # Fallback: simple placeholder
        values = _project_values(project)
        lines = [
            "GicaGen - Simulacion",
            "",
            f"projectId: {project_id}",
            f"runId: {run_id_value}",
            "",
            "values:",
        ]
        if not values:
            lines.append("- (sin valores)")
        else:
            for key, value in list(values.items())[:10]:  # Limit values shown
                lines.append(f"- {key}: {value}")

        pdf_bytes = _build_minimal_pdf(lines)

    output.write_bytes(pdf_bytes)
    return output


# Utility function for debugging
def get_format_headings(definition: Dict[str, Any]) -> List[str]:
    """Get list of headings from a format definition (for debugging)."""
    ir = compile_definition_to_ir(definition)
    return get_heading_titles(ir)

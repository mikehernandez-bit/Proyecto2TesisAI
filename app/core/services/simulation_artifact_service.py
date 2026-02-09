from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from docx import Document


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


def _simulation_sections(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    ai_result = project.get("ai_result")
    if isinstance(ai_result, dict):
        sections = ai_result.get("sections")
        if isinstance(sections, list):
            normalized: List[Dict[str, Any]] = []
            for item in sections:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "title": str(item.get("title") or "Seccion"),
                        "content": str(item.get("content") or ""),
                    }
                )
            if normalized:
                return normalized
    return [
        {"title": "Introduccion", "content": "Resultado simulado sin secciones de IA persistidas."},
    ]


def build_simulated_docx(project: Dict[str, Any], run_id: Optional[str] = None) -> Path:
    project_id = _safe_project_id(project)
    output = _output_dir() / f"simulated-{project_id}.docx"
    run_id_value = run_id or str(project.get("run_id") or "sim-local")

    doc = Document()
    doc.add_heading("GicaGen - Simulacion", level=1)
    doc.add_paragraph("Archivo placeholder para validar flujo end-to-end.")

    doc.add_heading("Proyecto", level=2)
    doc.add_paragraph(f"projectId: {project_id}")
    doc.add_paragraph(f"formatId: {project.get('format_id') or ''}")
    doc.add_paragraph(f"promptId: {project.get('prompt_id') or ''}")
    doc.add_paragraph(f"runId: {run_id_value}")
    doc.add_paragraph(f"status: {project.get('status') or ''}")

    doc.add_heading("Valores", level=2)
    values = _project_values(project)
    if not values:
        doc.add_paragraph("Sin valores.")
    for key, value in values.items():
        doc.add_paragraph(f"{key}: {value}", style="List Bullet")

    doc.add_heading("Secciones simuladas", level=2)
    for section in _simulation_sections(project):
        doc.add_paragraph(section["title"], style="Heading 3")
        doc.add_paragraph(section["content"])

    doc.save(str(output))
    return output


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_minimal_pdf(lines: Iterable[str]) -> bytes:
    content_lines: List[str] = [
        "BT",
        "/F1 12 Tf",
        "50 790 Td",
    ]
    first = True
    for raw in lines:
        line = _pdf_escape(str(raw))
        if first:
            content_lines.append(f"({line}) Tj")
            first = False
        else:
            content_lines.append("0 -16 Td")
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
    project_id = _safe_project_id(project)
    output = _output_dir() / f"simulated-{project_id}.pdf"
    values = _project_values(project)
    run_id_value = run_id or str(project.get("run_id") or "sim-local")

    lines = [
        "GicaGen - Simulacion",
        "",
        f"projectId: {project_id}",
        f"formatId: {project.get('format_id') or ''}",
        f"promptId: {project.get('prompt_id') or ''}",
        f"runId: {run_id_value}",
        "values:",
    ]
    if not values:
        lines.append("- (sin valores)")
    else:
        for key, value in values.items():
            lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("secciones:")
    for section in _simulation_sections(project):
        lines.append(f"* {section['title']}")
        lines.append(f"  {section['content']}")

    output.write_bytes(_build_minimal_pdf(lines))
    return output

"""
GicaTesis Integration - DTOs (Data Transfer Objects)

Pydantic models mirroring the GicaTesis Formats API v1 contracts.
These are read-only types used for type safety and validation.

Source: GicaTesis /docs/GICAGEN_INTEGRATION_GUIDE.md
"""

from __future__ import annotations

from typing import Annotated, Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class FormatSummary(BaseModel):
    """Summary of a format, returned in list endpoint."""

    id: str
    title: str
    university: str
    category: str
    documentType: Optional[str] = None
    version: str


class FormatField(BaseModel):
    """Field definition for wizard form generation."""

    name: str
    label: str
    type: str  # text, textarea, number, date, select, boolean
    required: bool = False
    default: Optional[Any] = None
    options: Optional[List[str]] = None
    validation: Optional[dict] = None
    order: Optional[int] = None
    section: Optional[str] = None


class AssetRef(BaseModel):
    """Reference to an asset (logo, image, etc.)."""

    id: str
    kind: str  # logo, image, signature
    url: str


class TemplateRef(BaseModel):
    """Reference to a document template."""

    kind: str  # docx, html, etc.
    uri: str


class FormatDetail(FormatSummary):
    """Full format details including fields for wizard."""

    templateRef: Optional[TemplateRef] = None
    fields: List[FormatField] = []
    assets: List[AssetRef] = []
    rules: Optional[dict] = None
    definition: Optional[dict] = None


class CatalogVersionResponse(BaseModel):
    """Response from /formats/version endpoint."""

    version: str
    generatedAt: str


_CANONICAL_PLACEHOLDER_PATH = "assets/placeholder_figura.png"


class ParagraphBlock(BaseModel):
    tipo: Literal["parrafo"]
    texto: str

    @field_validator("texto")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("Paragraph text cannot be empty")
        return text


class TableBlock(BaseModel):
    tipo: Literal["tabla"]
    encabezados: list[str] = Field(..., min_length=1)
    filas: list[list[str]] = Field(..., min_length=1)
    id: Optional[str] = None
    titulo: Optional[str] = None
    nota_pie: Optional[str] = None
    orientacion: Optional[Literal["portrait", "landscape"]] = None
    subtipo: Optional[str] = None
    anio: Optional[str] = None
    meses: Optional[list[str]] = None
    titulo_proyecto: Optional[str] = None
    simbolo_marca: Optional[str] = None
    filas_fase: Optional[list[int]] = None
    filas_categoria: Optional[list[int]] = None
    fila_total: Optional[int] = None
    celdas_combinadas: Optional[list[dict[str, Any]]] = None
    celdas_fusionadas: Optional[list[dict[str, Any]]] = None
    estilos: Optional[dict[str, Any]] = None
    estilo: Optional[dict[str, Any]] = None

    @field_validator("encabezados")
    @classmethod
    def _validate_headers(cls, value: list[str]) -> list[str]:
        headers = [str(item or "").strip() for item in value]
        if not any(item for item in headers):
            raise ValueError("Table must define at least one non-empty header")
        return headers

    @field_validator("filas")
    @classmethod
    def _validate_rows(cls, value: list[list[str]]) -> list[list[str]]:
        rows: list[list[str]] = []
        for row in value:
            if not isinstance(row, (list, tuple)):
                raise ValueError("Each table row must be a list")
            rows.append([str(cell or "").strip() for cell in row])
        if not rows:
            raise ValueError("Table must define at least one row")
        return rows

    @model_validator(mode="after")
    def _normalize_rows(self) -> "TableBlock":
        header_count = len(self.encabezados)
        normalized: list[list[str]] = []
        for row in self.filas:
            cells = list(row[:header_count])
            if len(cells) < header_count:
                cells.extend([""] * (header_count - len(cells)))
            if any(cell.strip() for cell in cells):
                normalized.append(cells)
        if not normalized:
            raise ValueError("Table must keep at least one non-empty row after normalization")
        self.filas = normalized
        if self.orientacion is None:
            self.orientacion = "landscape" if header_count > 5 else "portrait"
        return self


class FigureBlock(BaseModel):
    tipo: Literal["figura"]
    caption: str
    ruta_placeholder: Optional[str] = None
    id: Optional[str] = None
    titulo: Optional[str] = None
    fuente: Optional[str] = None
    nota: Optional[str] = None
    nota_color: Optional[str] = None
    diagram_type: Optional[str] = None
    diagram_data: Optional[dict[str, Any]] = None
    numbered: bool = True

    @field_validator("caption")
    @classmethod
    def _validate_caption(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("Figure caption cannot be empty")
        return text

    @field_validator("ruta_placeholder", mode="before")
    @classmethod
    def _normalize_placeholder_path(cls, value: Any) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        if text.lower() == "placeholder":
            return _CANONICAL_PLACEHOLDER_PATH
        return text

    @model_validator(mode="after")
    def _validate_visual_source(self) -> "FigureBlock":
        if not self.ruta_placeholder and not self.diagram_type:
            raise ValueError("Figure must define an image path or a deterministic diagram")
        return self


class FormulaBlock(BaseModel):
    tipo: Literal["formula"]
    id: Optional[str] = None
    texto: Optional[str] = None
    latex: Optional[str] = None
    numero: Optional[str] = None
    alineacion: Literal["center", "left", "right"] = "center"

    @model_validator(mode="after")
    def _validate_formula_text(self) -> "FormulaBlock":
        text = str(self.texto or "").strip()
        latex = str(self.latex or "").strip()
        if not text and not latex:
            raise ValueError("Formula must define texto or latex")
        self.texto = text or None
        self.latex = latex or None
        if self.numero is not None:
            self.numero = str(self.numero or "").strip() or None
        return self


RenderAIBlock = Annotated[
    Union[ParagraphBlock, TableBlock, FigureBlock, FormulaBlock],
    Field(discriminator="tipo"),
]
RenderAIContent = Union[str, list[RenderAIBlock]]


class RenderAISection(BaseModel):
    sectionId: Optional[str] = None
    path: Optional[str] = None
    content: RenderAIContent

    @model_validator(mode="after")
    def validate_locator(self) -> "RenderAISection":
        if not (self.sectionId or self.path):
            raise ValueError("RenderAISection requires at least one locator: path or sectionId")
        return self


class RenderAIResult(BaseModel):
    sections: list[RenderAISection] = Field(default_factory=list)


class RenderRequest(BaseModel):
    formatId: str = Field(..., min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="simulation")
    aiResult: RenderAIResult = Field(default_factory=RenderAIResult)
    selectedSections: list[dict[str, Any]] = Field(default_factory=list)


class RenderPayloadValidationError(Exception):
    """Raised when the outbound payload does not satisfy GicaTesis render contract."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__("Render payload does not satisfy GicaTesis contract")


def validate_render_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize the outbound render payload locally."""
    try:
        request = RenderRequest.model_validate(payload)
    except ValidationError as exc:
        raise RenderPayloadValidationError([dict(item) for item in exc.errors()]) from exc
    return request.model_dump(exclude_none=True)

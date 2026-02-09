"""
GicaTesis Integration - DTOs (Data Transfer Objects)

Pydantic models mirroring the GicaTesis Formats API v1 contracts.
These are read-only types used for type safety and validation.

Source: GicaTesis /docs/GICAGEN_INTEGRATION_GUIDE.md
"""
from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, List, Any


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

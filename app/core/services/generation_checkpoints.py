"""Typed internal checkpoint contracts for resumable generation/construction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GenerationCheckpoint:
    input_fingerprint: str
    profile_version: str
    saved_sections_count: int
    resume_from_index: int
    current_path: str = ""
    failed_section_id: str = ""
    failed_section_index: int = 0
    completed_section_ids: tuple[str, ...] = ()
    token_usage: dict[str, Any] = field(default_factory=dict)
    cost_usage: dict[str, Any] = field(default_factory=dict)
    failed_stage: str = ""
    failed_quality_keys: tuple[str, ...] = ()
    validated_sections_count: int = 0
    quality_attempts_by_key: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConstructionCheckpoint:
    input_fingerprint: str
    stage: str
    completed_tasks: tuple[str, ...] = ()
    docx_path: str = ""
    pdf_path: str = ""
    field_stabilization_cycle: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

class PromptIn(BaseModel):
    name: str = Field(..., min_length=1)
    doc_type: str = "Tesis Completa"
    is_active: bool = True
    template: str = ""
    variables: List[str] = []

class ProjectGenerateIn(BaseModel):
    format_id: str
    prompt_id: str
    title: Optional[str] = None
    variables: Dict[str, Any] = {}


class ProjectDraftIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    format_id: Optional[str] = None
    prompt_id: Optional[str] = None
    title: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    format_name: Optional[str] = None
    format_version: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        """Accept camelCase payloads from external callers."""
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data

        remapped = dict(data)
        aliases = {
            "formatId": "format_id",
            "promptId": "prompt_id",
            "values": "variables",
            "formatName": "format_name",
            "formatVersion": "format_version",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class ProjectUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    format_id: Optional[str] = None
    prompt_id: Optional[str] = None
    title: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    format_name: Optional[str] = None
    format_version: Optional[str] = None
    status: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        aliases = {
            "formatId": "format_id",
            "promptId": "prompt_id",
            "values": "variables",
            "formatName": "format_name",
            "formatVersion": "format_version",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class N8NCallbackIn(BaseModel):
    projectId: str
    runId: Optional[str] = None
    status: Optional[str] = "success"
    aiResult: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

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

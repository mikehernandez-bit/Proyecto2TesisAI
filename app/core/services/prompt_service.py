from __future__ import annotations

from typing import Any, Dict, List, Optional
from app.core.storage.json_store import JsonStore
from app.core.utils.id import new_id

class PromptService:
    """CRUD for prompt templates."""

    def __init__(self, path: str = "data/prompts.json"):
        self.store = JsonStore(path)

    def list_prompts(self) -> List[Dict[str, Any]]:
        return self.store.read_list()

    def get_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        for p in self.store.read_list():
            if p.get("id") == prompt_id:
                return p
        return None

    def create_prompt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        items = self.store.read_list()
        prompt = {
            "id": new_id("prompt"),
            "name": payload.get("name", "Nuevo Prompt"),
            "doc_type": payload.get("doc_type", "Tesis Completa"),
            "is_active": bool(payload.get("is_active", True)),
            "template": payload.get("template", ""),
            "variables": payload.get("variables", []),
        }
        items.insert(0, prompt)
        self.store.write_list(items)
        return prompt

    def update_prompt(self, prompt_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        items = self.store.read_list()
        for i, p in enumerate(items):
            if p.get("id") == prompt_id:
                p.update({
                    "name": payload.get("name", p.get("name")),
                    "doc_type": payload.get("doc_type", p.get("doc_type")),
                    "is_active": bool(payload.get("is_active", p.get("is_active", True))),
                    "template": payload.get("template", p.get("template", "")),
                    "variables": payload.get("variables", p.get("variables", [])),
                })
                items[i] = p
                self.store.write_list(items)
                return p
        return None

    def delete_prompt(self, prompt_id: str) -> bool:
        items = self.store.read_list()
        new_items = [p for p in items if p.get("id") != prompt_id]
        if len(new_items) == len(items):
            return False
        self.store.write_list(new_items)
        return True

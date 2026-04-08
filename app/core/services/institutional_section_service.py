from __future__ import annotations

import unicodedata
from typing import Any, Dict, List

from app.core.services.definition_compiler import compile_definition_to_section_index

_OPTIONAL_SECTION_MARKERS = {
    "dedicatoria",
    "agradecimiento",
    "agradecimientos",
    "resumen",
    "abstract",
    "anexo",
    "anexos",
}

_ANNEX_SECTION_MARKERS = {
    "anexo",
    "anexos",
}


def _normalize_label(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()


class InstitutionalSectionService:
    """Derive reusable generative sections from a GicaTesis definition."""

    def extract_sections(self, definition: Dict[str, Any] | None) -> List[Dict[str, Any]]:
        if not isinstance(definition, dict):
            return []

        raw_sections = compile_definition_to_section_index(definition)
        sections: List[Dict[str, Any]] = []
        for raw_order, item in enumerate(raw_sections, start=1):
            if not isinstance(item, dict):
                continue
            section_id = str(item.get("sectionId") or "").strip()
            section_path = str(item.get("path") or "").strip()
            if not section_id or not section_path:
                continue
            if self._is_non_generative_annex_child(section_path):
                continue
            section_title = str(item.get("title") or section_path.split("/")[-1]).strip()
            parent_section_path = self._parent_path(section_path)
            optional = self._is_optional_section(section_path, section_title)
            sections.append(
                {
                    "section_id": section_id,
                    "section_path": section_path,
                    "section_title": section_title,
                    "parent_section_path": parent_section_path,
                    "section_level": max(1, int(item.get("level") or self._path_level(section_path))),
                    "section_order": raw_order,
                    "optional": optional,
                    "default_selected": not optional,
                    "source_hints": str(item.get("hints") or "").strip(),
                    "kind": str(item.get("kind") or "").strip(),
                    "blocks": [],
                }
            )
        return sections

    def build_tree(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        nodes: Dict[str, Dict[str, Any]] = {}
        roots: List[Dict[str, Any]] = []

        for raw in sections:
            if not isinstance(raw, dict):
                continue
            node = dict(raw)
            node["children"] = []
            section_path = str(node.get("section_path") or "").strip()
            if not section_path:
                continue
            nodes[section_path] = node

        for section_path, node in nodes.items():
            parent_path = str(node.get("parent_section_path") or "").strip()
            parent = nodes.get(parent_path)
            if parent is None:
                roots.append(node)
                continue
            parent.setdefault("children", []).append(node)

        for node in nodes.values():
            children = node.get("children")
            if isinstance(children, list):
                children.sort(
                    key=lambda item: (
                        int(item.get("section_order") or 10**9),
                        int(item.get("section_level") or 0),
                        str(item.get("section_path") or ""),
                    )
                )
        roots.sort(
            key=lambda item: (
                int(item.get("section_order") or 10**9),
                int(item.get("section_level") or 0),
                str(item.get("section_path") or ""),
            )
        )
        return roots

    @staticmethod
    def _parent_path(path: str) -> str:
        parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
        if len(parts) <= 1:
            return ""
        return "/".join(parts[:-1])

    @staticmethod
    def _path_level(path: str) -> int:
        parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
        return max(1, len(parts))

    def _is_optional_section(self, section_path: str, section_title: str) -> bool:
        normalized_candidates = {
            _normalize_label(section_title),
            _normalize_label(section_path.split("/")[-1]),
            _normalize_label(section_path),
        }
        return any(marker in candidate for candidate in normalized_candidates for marker in _OPTIONAL_SECTION_MARKERS)

    def _is_non_generative_annex_child(self, section_path: str) -> bool:
        parts = [part.strip() for part in str(section_path or "").split("/") if part.strip()]
        if len(parts) <= 1:
            return False
        normalized_ancestors = [_normalize_label(part) for part in parts[:-1]]
        return any(marker in ancestor for ancestor in normalized_ancestors for marker in _ANNEX_SECTION_MARKERS)

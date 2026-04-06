from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from app.core.storage.json_store import JsonStore
from app.core.utils.id import new_id
from app.integrations.gicatesis.cache.format_cache import FormatCache

from .institutional_section_service import InstitutionalSectionService

_PROMPT_NAME_FORMAT_OVERRIDES = {
    "Informe Cuantitativo UNAC": "unac-informe-cuant",
    "Informe Cualitativo UNAC": "unac-informe-cual",
    "Informe UNI": "uni-informe-apa",
    "Maestría Cuantitativa UNAC": "unac-maestria-cuant",
    "Maestría Cualitativa UNAC": "unac-maestria-cual",
    "Proyecto Cuantitativo UNAC": "unac-proyecto-cuant",
    "Proyecto Cualitativo UNAC": "unac-proyecto-cual",
    "Plan de Trabajo UNI": "uni-proyecto-standard",
    "Posgrado UNI": "uni-posgrado-standard",
}

_LEGACY_METHOD_TO_FORMAT_TOKEN = {
    "INF": "informe",
    "PROY": "proyecto",
    "MAES": "maestria",
    "PLAN": "proyecto",
    "POST": "posgrado",
}

_LEGACY_SUBTYPE_TO_TOKEN = {
    "CUALI": "cual",
    "CUANTI": "cuant",
}


def _normalize_match_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()


class PromptService:
    """CRUD and normalization for institutional prompt packages."""

    def __init__(self, path: str = "data/prompts.json") -> None:
        self.store = JsonStore(path)
        self.format_cache = FormatCache()
        self.section_service = InstitutionalSectionService()

    def list_prompts(self) -> List[Dict[str, Any]]:
        packages = self._build_packages(self.store.read_list())
        packages.sort(key=lambda item: str(item.get("name") or "").lower())
        return packages

    def get_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        prompt_key = str(prompt_id or "").strip()
        if not prompt_key:
            return None
        for prompt in self.list_prompts():
            if str(prompt.get("id") or "").strip() == prompt_key:
                return prompt
        return None

    def get_prompt_by_format(
        self,
        format_id: str,
        *,
        format_detail: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        format_key = str(format_id or "").strip()
        if not format_key:
            return None

        items = self.store.read_list()
        detail_by_id = {format_key: format_detail} if format_detail else None
        packages = self._build_packages(items, format_detail_by_id=detail_by_id)
        for prompt in packages:
            if str(prompt.get("format_id") or "").strip() == format_key:
                return prompt

        format_meta = self._format_metadata(format_key, format_detail)
        if not format_meta:
            return None
        sections = self.section_service.extract_sections(format_meta.get("definition"))
        return self._normalize_package(
            {
                "id": f"promptpkg_{format_key.replace('-', '_')}",
                "name": f"Paquete {format_meta.get('title')}",
                "doc_type": format_meta.get("documentType") or "",
                "is_active": True,
                "format_id": format_key,
                "format_name": format_meta.get("title") or format_key,
                "format_version": format_meta.get("version") or "",
                "system_instruction": "",
                "template": "",
                "variables": [],
                "sections": sections,
            },
            format_detail=format_detail or format_meta,
            persisted=False,
        )

    def create_prompt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        items = self.store.read_list()
        normalized = self._normalize_incoming_package(payload, fallback_id=new_id("prompt"))
        filtered = self._filter_replaced_items(
            items,
            package_id=str(normalized.get("id") or ""),
            format_id=str(normalized.get("format_id") or ""),
        )
        filtered.insert(0, self._to_storage_record(normalized))
        self.store.write_list(filtered)
        return normalized

    def update_prompt(self, prompt_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_prompt(prompt_id)
        if existing is None:
            return None
        merged_payload = dict(existing)
        merged_payload.update(payload or {})
        merged_payload["id"] = prompt_id
        normalized = self._normalize_incoming_package(merged_payload, fallback_id=prompt_id)
        items = self.store.read_list()
        filtered = self._filter_replaced_items(
            items,
            package_id=str(prompt_id or ""),
            format_id=str(normalized.get("format_id") or ""),
        )
        filtered.insert(0, self._to_storage_record(normalized))
        self.store.write_list(filtered)
        return normalized

    def delete_prompt(self, prompt_id: str) -> bool:
        items = self.store.read_list()
        package = self.get_prompt(prompt_id)
        format_id = str(package.get("format_id") or "") if isinstance(package, dict) else ""
        filtered = self._filter_replaced_items(items, package_id=prompt_id, format_id=format_id)
        if len(filtered) == len(items):
            return False
        self.store.write_list(filtered)
        return True

    def _build_packages(
        self,
        raw_items: List[Dict[str, Any]],
        *,
        format_detail_by_id: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        modern_items: List[Dict[str, Any]] = []
        legacy_items: List[Dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            if item.get("id"):
                modern_items.append(item)
            elif item.get("prompts") and item.get("id_unico"):
                legacy_items.append(item)

        packages: List[Dict[str, Any]] = []
        package_by_format: Dict[str, Dict[str, Any]] = {}
        for item in modern_items:
            prompt = self._normalize_package(
                item,
                format_detail=(format_detail_by_id or {}).get(self._infer_format_id(item)),
                persisted=True,
            )
            packages.append(prompt)
            format_id = str(prompt.get("format_id") or "").strip()
            if format_id:
                package_by_format[format_id] = prompt

        for legacy_item in legacy_items:
            format_id = self._resolve_legacy_format_id(legacy_item)
            if not format_id:
                continue
            target = package_by_format.get(format_id)
            if target is None:
                format_meta = self._format_metadata(
                    format_id,
                    (format_detail_by_id or {}).get(format_id),
                )
                if not format_meta:
                    continue
                target = self._normalize_package(
                    {
                        "id": f"promptpkg_{format_id.replace('-', '_')}",
                        "name": f"Paquete {format_meta.get('title')}",
                        "doc_type": format_meta.get("documentType") or "",
                        "is_active": True,
                        "format_id": format_id,
                        "format_name": format_meta.get("title") or format_id,
                        "format_version": format_meta.get("version") or "",
                        "system_instruction": "",
                        "template": "",
                        "variables": [],
                        "sections": self.section_service.extract_sections(format_meta.get("definition")),
                    },
                    format_detail=format_meta,
                    persisted=False,
                )
                target["persisted"] = False
                package_by_format[format_id] = target
                packages.append(target)
            self._merge_legacy_prompt_blocks(target, legacy_item)

        for package in packages:
            package["variables"] = self._aggregate_package_variables(package)
        return packages

    def _normalize_incoming_package(self, payload: Dict[str, Any], *, fallback_id: str) -> Dict[str, Any]:
        format_id = str(
            payload.get("format_id") or payload.get("formatId") or self._infer_format_id(payload) or ""
        ).strip()
        format_meta = self._format_metadata(format_id)
        sections = payload.get("sections")
        if isinstance(sections, list) and sections:
            normalized_sections = self._normalize_sections(sections)
        else:
            normalized_sections = self.section_service.extract_sections(
                format_meta.get("definition") if isinstance(format_meta, dict) else None
            )

        doc_type = (
            payload.get("doc_type")
            or payload.get("docType")
            or format_meta.get("documentType")
            or "Tesis Completa"
        )
        format_name = (
            payload.get("format_name")
            or payload.get("formatName")
            or format_meta.get("title")
            or format_id
        )
        format_version = (
            payload.get("format_version")
            or payload.get("formatVersion")
            or format_meta.get("version")
            or ""
        )
        required_metadata = [
            str(item).strip()
            for item in payload.get("required_metadata") or []
            if str(item).strip()
        ]
        package = {
            "id": str(payload.get("id") or fallback_id),
            "name": str(payload.get("name") or format_meta.get("title") or "Nuevo paquete"),
            "doc_type": str(doc_type),
            "is_active": bool(payload.get("is_active", True)),
            "format_id": format_id,
            "format_name": str(format_name),
            "format_version": str(format_version),
            "system_instruction": str(payload.get("system_instruction") or payload.get("template") or ""),
            "required_metadata": required_metadata,
            "template": str(payload.get("template") or payload.get("system_instruction") or ""),
            "variables": self._normalize_variable_list(payload.get("variables")),
            "sections": normalized_sections,
            "persisted": True,
        }
        package["variables"] = self._aggregate_package_variables(package)
        return package

    def _normalize_package(
        self,
        payload: Dict[str, Any],
        *,
        format_detail: Optional[Dict[str, Any]] = None,
        persisted: bool,
    ) -> Dict[str, Any]:
        format_id = str(
            payload.get("format_id") or payload.get("formatId") or self._infer_format_id(payload) or ""
        ).strip()
        format_meta = self._format_metadata(format_id, format_detail)
        base_sections = self.section_service.extract_sections(
            format_meta.get("definition") if isinstance(format_meta, dict) else None
        )
        package_sections = self._normalize_sections(payload.get("sections"))
        merged_sections = self._merge_sections(base_sections, package_sections)
        doc_type = (
            payload.get("doc_type")
            or payload.get("docType")
            or format_meta.get("documentType")
            or "Tesis Completa"
        )
        format_name = (
            payload.get("format_name")
            or payload.get("formatName")
            or format_meta.get("title")
            or format_id
        )
        format_version = (
            payload.get("format_version")
            or payload.get("formatVersion")
            or format_meta.get("version")
            or ""
        )
        required_metadata = [
            str(item).strip()
            for item in payload.get("required_metadata") or []
            if str(item).strip()
        ]
        package = {
            "id": str(payload.get("id") or new_id("prompt")),
            "name": str(payload.get("name") or format_meta.get("title") or "Paquete sin nombre"),
            "doc_type": str(doc_type),
            "is_active": bool(payload.get("is_active", True)),
            "format_id": format_id,
            "format_name": str(format_name),
            "format_version": str(format_version),
            "system_instruction": str(payload.get("system_instruction") or payload.get("template") or ""),
            "required_metadata": required_metadata,
            "template": str(payload.get("template") or payload.get("system_instruction") or ""),
            "variables": self._normalize_variable_list(payload.get("variables")),
            "sections": merged_sections,
            "persisted": persisted,
        }
        package["variables"] = self._aggregate_package_variables(package)
        return package

    @staticmethod
    def _normalize_sections(raw_sections: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_sections, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in raw_sections:
            if not isinstance(item, dict):
                continue
            section_id = str(item.get("section_id") or item.get("sectionId") or "").strip()
            section_path = str(item.get("section_path") or item.get("path") or "").strip()
            if not section_id and not section_path:
                continue
            raw_blocks = item.get("blocks")
            blocks = raw_blocks if isinstance(raw_blocks, list) else []
            section_title = (
                item.get("section_title")
                or item.get("sectionTitle")
                or item.get("title")
                or (section_path.split("/")[-1] if section_path else "")
            )
            normalized.append(
                {
                    "section_id": section_id or section_path,
                    "section_path": section_path or section_id,
                    "section_title": str(section_title),
                    "parent_section_path": str(
                        item.get("parent_section_path") or item.get("parentSectionPath") or ""
                    ),
                    "section_level": max(1, int(item.get("section_level") or item.get("sectionLevel") or 1)),
                    "optional": bool(item.get("optional")),
                    "default_selected": bool(item.get("default_selected", True)),
                    "source_hints": str(item.get("source_hints") or item.get("sourceHints") or ""),
                    "blocks": [PromptService._normalize_block(block) for block in blocks if isinstance(block, dict)],
                }
            )
        return normalized

    @staticmethod
    def _normalize_block(raw_block: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "block_id": str(
                raw_block.get("block_id")
                or raw_block.get("id")
                or raw_block.get("legacy_prompt_id")
                or raw_block.get("numero_prompt")
                or ""
            ),
            "label": str(
                raw_block.get("label")
                or raw_block.get("titulo_cabecera")
                or raw_block.get("name")
                or "Prompt principal"
            ),
            "instructions": str(raw_block.get("instructions") or raw_block.get("instrucciones_ia") or ""),
            "required_variables": PromptService._normalize_variable_list(
                raw_block.get("required_variables") or raw_block.get("variables_locales") or raw_block.get("variables")
            ),
            "required": bool(raw_block.get("required", True)),
            "legacy_prompt_id": str(raw_block.get("legacy_prompt_id") or raw_block.get("numero_prompt") or ""),
        }

    def _merge_sections(
        self,
        base_sections: List[Dict[str, Any]],
        package_sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not base_sections:
            return package_sections
        package_by_key = {
            str(item.get("section_id") or item.get("section_path") or "").strip(): item
            for item in package_sections
            if str(item.get("section_id") or item.get("section_path") or "").strip()
        }
        merged: List[Dict[str, Any]] = []
        for base in base_sections:
            key = str(base.get("section_id") or base.get("section_path") or "").strip()
            overlay = package_by_key.get(key, {})
            raw_blocks = overlay.get("blocks")
            blocks = raw_blocks if isinstance(raw_blocks, list) else []
            merged.append(
                {
                    "section_id": key,
                    "section_path": str(base.get("section_path") or "").strip(),
                    "section_title": str(overlay.get("section_title") or base.get("section_title") or "").strip(),
                    "parent_section_path": str(base.get("parent_section_path") or "").strip(),
                    "section_level": int(base.get("section_level") or 1),
                    "optional": bool(overlay.get("optional", base.get("optional"))),
                    "default_selected": bool(overlay.get("default_selected", base.get("default_selected", True))),
                    "source_hints": "\n".join(
                        item
                        for item in [
                            str(base.get("source_hints") or "").strip(),
                            str(overlay.get("source_hints") or "").strip(),
                        ]
                        if item
                    ),
                    "blocks": [self._normalize_block(block) for block in blocks if isinstance(block, dict)],
                }
            )

        seen_keys = {str(item.get("section_id") or item.get("section_path") or "").strip() for item in merged}
        for section in package_sections:
            key = str(section.get("section_id") or section.get("section_path") or "").strip()
            if not key or key in seen_keys:
                continue
            merged.append(section)
        return merged

    def _merge_legacy_prompt_blocks(self, package: Dict[str, Any], legacy_item: Dict[str, Any]) -> None:
        prompts = legacy_item.get("prompts")
        if not isinstance(prompts, list):
            return
        sections = package.get("sections")
        if not isinstance(sections, list):
            sections = []
            package["sections"] = sections

        for raw_prompt in prompts:
            if not isinstance(raw_prompt, dict):
                continue
            target_section = self._find_target_section_for_legacy_block(sections, raw_prompt)
            if target_section is None:
                target_section = {
                    "section_id": str(raw_prompt.get("numero_prompt") or new_id("sec")),
                    "section_path": str(raw_prompt.get("capitulo_nombre") or raw_prompt.get("titulo_cabecera") or ""),
                    "section_title": str(raw_prompt.get("titulo_cabecera") or raw_prompt.get("capitulo_nombre") or ""),
                    "parent_section_path": "",
                    "section_level": 1,
                    "optional": False,
                    "default_selected": True,
                    "source_hints": "",
                    "blocks": [],
                }
                sections.append(target_section)
            blocks = target_section.setdefault("blocks", [])
            if not isinstance(blocks, list):
                blocks = []
                target_section["blocks"] = blocks
            blocks.append(
                self._normalize_block(
                    {
                        **raw_prompt,
                        "legacy_prompt_id": legacy_item.get("id_unico"),
                    }
                )
            )

    @staticmethod
    def _find_target_section_for_legacy_block(
        sections: List[Dict[str, Any]],
        raw_prompt: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        legacy_title = _normalize_match_text(raw_prompt.get("titulo_cabecera"))
        legacy_chapter = _normalize_match_text(raw_prompt.get("capitulo_nombre"))
        best_match: Optional[Tuple[int, Dict[str, Any]]] = None
        for section in sections:
            section_title = _normalize_match_text(section.get("section_title"))
            section_path = _normalize_match_text(section.get("section_path"))
            score = 0
            if legacy_title and legacy_title == section_title:
                score += 100
            elif legacy_title and legacy_title in section_title:
                score += 80
            if legacy_title and legacy_title in section_path:
                score += 60
            if legacy_chapter and legacy_chapter in section_path:
                score += 20
            if legacy_chapter and legacy_chapter == section_title:
                score += 10
            if score <= 0:
                continue
            if best_match is None or score > best_match[0]:
                best_match = (score, section)
        if best_match is not None:
            return best_match[1]
        return sections[0] if sections else None

    def _resolve_legacy_format_id(self, legacy_item: Dict[str, Any]) -> str:
        university = str(legacy_item.get("universidad") or "").strip().lower()
        method = str(legacy_item.get("metodologia") or "").strip().upper()
        subtype = str(legacy_item.get("categoria") or "").strip().upper()
        category_token = _LEGACY_METHOD_TO_FORMAT_TOKEN.get(method, "")
        subtype_token = _LEGACY_SUBTYPE_TO_TOKEN.get(subtype, "")

        candidates = self.format_cache.get_formats()
        for item in candidates:
            format_id = str(item.get("id") or "").strip().lower()
            if not format_id or university not in format_id or category_token not in format_id:
                continue
            if subtype_token and subtype_token not in format_id:
                continue
            return str(item.get("id") or "")
        return ""

    def _infer_format_id(self, prompt: Dict[str, Any]) -> str:
        explicit = str(prompt.get("format_id") or prompt.get("formatId") or "").strip()
        if explicit:
            return explicit
        name = str(prompt.get("name") or "").strip()
        if name in _PROMPT_NAME_FORMAT_OVERRIDES:
            return _PROMPT_NAME_FORMAT_OVERRIDES[name]

        normalized_name = name.lower()
        best_match: Tuple[int, str] = (0, "")
        for format_item in self.format_cache.get_formats():
            format_id = str(format_item.get("id") or "")
            title = str(format_item.get("title") or "").lower()
            score = 0
            if "unac" in normalized_name and "unac" in format_id:
                score += 3
            if "uni" in normalized_name and "uni-" in format_id:
                score += 3
            for token in ("informe", "proyecto", "maestr", "posgrado", "plan", "cuant", "cual", "apa", "standard"):
                if token in normalized_name and (token in title or token in format_id):
                    score += 2
            if score > best_match[0]:
                best_match = (score, format_id)
        return best_match[1]

    def _format_metadata(
        self,
        format_id: str,
        format_detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if format_detail and isinstance(format_detail, dict):
            return dict(format_detail)
        format_key = str(format_id or "").strip()
        if not format_key:
            return {}
        detail = self.format_cache.get_detail(format_key)
        if isinstance(detail, dict):
            return detail
        for item in self.format_cache.get_formats():
            if str(item.get("id") or "").strip() == format_key:
                return dict(item)
        return {}

    @staticmethod
    def _normalize_variable_list(raw_variables: Any) -> List[str]:
        if not isinstance(raw_variables, list):
            return []
        values: List[str] = []
        seen = set()
        for item in raw_variables:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            values.append(value)
        return values

    @classmethod
    def _aggregate_package_variables(cls, package: Dict[str, Any]) -> List[str]:
        variables = cls._normalize_variable_list(package.get("variables"))
        seen = set(variables)
        for section in package.get("sections") or []:
            if not isinstance(section, dict):
                continue
            for block in section.get("blocks") or []:
                if not isinstance(block, dict):
                    continue
                for variable in cls._normalize_variable_list(block.get("required_variables")):
                    if variable in seen:
                        continue
                    seen.add(variable)
                    variables.append(variable)
        return variables

    def _to_storage_record(self, package: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(package.get("id") or new_id("prompt")),
            "name": str(package.get("name") or "Nuevo paquete"),
            "doc_type": str(package.get("doc_type") or "Tesis Completa"),
            "is_active": bool(package.get("is_active", True)),
            "format_id": str(package.get("format_id") or ""),
            "format_name": str(package.get("format_name") or ""),
            "format_version": str(package.get("format_version") or ""),
            "system_instruction": str(package.get("system_instruction") or ""),
            "required_metadata": [
                str(item).strip()
                for item in package.get("required_metadata") or []
                if str(item).strip()
            ],
            "template": str(package.get("template") or package.get("system_instruction") or ""),
            "variables": self._aggregate_package_variables(package),
            "sections": self._normalize_sections(package.get("sections")),
        }

    def _filter_replaced_items(
        self,
        items: List[Dict[str, Any]],
        *,
        package_id: str,
        format_id: str,
    ) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            if package_id and item_id == package_id:
                continue
            if item.get("prompts") and self._resolve_legacy_format_id(item) == format_id:
                continue
            filtered.append(item)
        return filtered

from __future__ import annotations

from typing import Any, Dict, List, Set

from app.core.services.institutional_section_service import InstitutionalSectionService


class ProjectGenerationPlanner:
    """Merge institutional sections, prompt package metadata, and user selection."""

    def __init__(self, section_service: InstitutionalSectionService | None = None) -> None:
        self.section_service = section_service or InstitutionalSectionService()

    def plan_sections(
        self,
        *,
        definition: Dict[str, Any] | None,
        prompt_package: Dict[str, Any] | None,
        selected_sections: List[Dict[str, Any]] | List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        institutional_sections = self.section_service.extract_sections(definition)
        package_sections = self._normalize_package_sections(prompt_package)
        package_by_key: Dict[str, Dict[str, Any]] = {}
        for item in package_sections:
            for key in self._section_keys(item):
                package_by_key[key] = item

        merged_sections: List[Dict[str, Any]] = []
        for section in institutional_sections:
            package_section = self._find_matching_section(section, package_by_key)
            merged_sections.append(self._merge_section(section, package_section))

        selected_keys = self._resolve_selected_keys(
            selected_sections=selected_sections,
            merged_sections=merged_sections,
        )
        planned: List[Dict[str, Any]] = []
        for section in merged_sections:
            if selected_keys and not self._section_keys(section).intersection(selected_keys):
                continue
            planned.append(
                {
                    "sectionId": str(section.get("section_id") or "").strip(),
                    "path": str(section.get("section_path") or "").strip(),
                    "title": str(section.get("section_title") or "").strip(),
                    "parent_section_path": str(section.get("parent_section_path") or "").strip(),
                    "level": int(section.get("section_level") or 1),
                    "hints": str(section.get("source_hints") or "").strip(),
                    "optional": bool(section.get("optional")),
                    "default_selected": bool(section.get("default_selected")),
                    "blocks": [dict(item) for item in section.get("blocks") or [] if isinstance(item, dict)],
                    "required_variables": self._section_required_variables(section),
                    "additional_context": self._build_additional_context(section),
                }
            )
        return planned

    def infer_selected_sections_from_ai_result(
        self,
        ai_result: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(ai_result, dict):
            return []
        raw_sections = ai_result.get("sections")
        if not isinstance(raw_sections, list):
            return []
        selected: List[Dict[str, Any]] = []
        for item in raw_sections:
            if not isinstance(item, dict):
                continue
            section_id = str(item.get("sectionId") or "").strip()
            section_path = str(item.get("path") or "").strip()
            if not section_id and not section_path:
                continue
            selected.append(
                {
                    "section_id": section_id,
                    "section_path": section_path,
                }
            )
        return selected

    def collect_required_variables(
        self,
        prompt_package: Dict[str, Any] | None,
        selected_sections: List[Dict[str, Any]] | List[str] | None = None,
    ) -> Dict[str, Any]:
        package = prompt_package if isinstance(prompt_package, dict) else {}
        package_variables = self._normalize_variables(package.get("variables"))
        planned = self.plan_sections(
            definition={},
            prompt_package=package,
            selected_sections=selected_sections,
        )
        section_variables = {
            str(item.get("sectionId") or item.get("path") or ""): self._normalize_variables(
                item.get("required_variables")
            )
            for item in planned
        }
        return {
            "package": package_variables,
            "sections": section_variables,
        }

    @staticmethod
    def _normalize_package_sections(prompt_package: Dict[str, Any] | None) -> List[Dict[str, Any]]:
        if not isinstance(prompt_package, dict):
            return []
        sections = prompt_package.get("sections")
        return [dict(item) for item in sections if isinstance(item, dict)] if isinstance(sections, list) else []

    @staticmethod
    def _section_key(section: Dict[str, Any]) -> str:
        section_id = str(section.get("section_id") or section.get("sectionId") or "").strip()
        section_path = str(section.get("section_path") or section.get("path") or "").strip()
        return section_id or section_path

    @classmethod
    def _section_keys(cls, section: Dict[str, Any]) -> Set[str]:
        keys = {
            str(section.get("section_id") or section.get("sectionId") or "").strip(),
            str(section.get("section_path") or section.get("path") or "").strip(),
            cls._section_key(section),
        }
        return {key for key in keys if key}

    def _find_matching_section(
        self,
        section: Dict[str, Any],
        package_by_key: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        for key in self._section_keys(section):
            package_section = package_by_key.get(key)
            if isinstance(package_section, dict):
                return package_section
        return {}

    def _resolve_selected_keys(
        self,
        *,
        selected_sections: List[Dict[str, Any]] | List[str] | None,
        merged_sections: List[Dict[str, Any]],
    ) -> Set[str]:
        if isinstance(selected_sections, list) and selected_sections:
            selected_keys: Set[str] = set()
            for item in selected_sections:
                if isinstance(item, str):
                    key = item.strip()
                    if key:
                        selected_keys.add(key)
                    continue
                if not isinstance(item, dict):
                    continue
                selected_keys.update(self._section_keys(item))
            if selected_keys:
                return selected_keys

        return {
            key
            for item in merged_sections
            if bool(item.get("default_selected", True))
            for key in self._section_keys(item)
        }

    def _merge_section(self, institutional_section: Dict[str, Any], package_section: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(institutional_section)
        if package_section:
            merged["optional"] = bool(package_section.get("optional", merged.get("optional")))
            merged["default_selected"] = bool(
                package_section.get("default_selected", merged.get("default_selected", True))
            )
            source_hints = [
                str(merged.get("source_hints") or "").strip(),
                str(package_section.get("source_hints") or "").strip(),
            ]
            merged["source_hints"] = "\n".join(item for item in source_hints if item)
            package_blocks = package_section.get("blocks")
            merged["blocks"] = (
                [dict(item) for item in package_blocks if isinstance(item, dict)]
                if isinstance(package_blocks, list)
                else []
            )
        else:
            merged["blocks"] = []
        return merged

    @staticmethod
    def _normalize_variables(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        unique: List[str] = []
        seen: Set[str] = set()
        for item in values:
            key = str(item or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(key)
        return unique

    def _section_required_variables(self, section: Dict[str, Any]) -> List[str]:
        variables: List[str] = []
        seen: Set[str] = set()
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            for variable in self._normalize_variables(block.get("required_variables")):
                if variable in seen:
                    continue
                seen.add(variable)
                variables.append(variable)
        return variables

    def _build_additional_context(self, section: Dict[str, Any]) -> str:
        parts: List[str] = []
        base_hints = str(section.get("source_hints") or "").strip()
        if base_hints:
            parts.append(base_hints)

        blocks = [item for item in section.get("blocks") or [] if isinstance(item, dict)]
        if not blocks:
            return "\n\n".join(part for part in parts if part)

        block_lines: List[str] = []
        for block in blocks:
            label = str(block.get("label") or "Bloque").strip()
            instructions = str(block.get("instructions") or "").strip()
            required = self._normalize_variables(block.get("required_variables"))
            block_lines.append(f"- {label}")
            if instructions:
                block_lines.append(f"  Instrucciones: {instructions}")
            if required:
                block_lines.append(f"  Variables requeridas: {', '.join(required)}")
        parts.append("Bloques de prompt activos:\n" + "\n".join(block_lines))
        return "\n\n".join(part for part in parts if part)

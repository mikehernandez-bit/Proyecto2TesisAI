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
        matched_package_keys: Set[str] = set()
        for section in institutional_sections:
            package_section = self._find_matching_section(section, package_by_key)
            matched_package_keys.update(self._section_keys(package_section))
            merged_sections.append(self._merge_section(section, package_section))

        if not institutional_sections:
            merged_sections = [dict(item) for item in package_sections]
        else:
            merged_sections.extend(
                self._collect_custom_package_sections(
                    package_sections=package_sections,
                    matched_package_keys=matched_package_keys,
                )
            )

        merged_sections = self._flatten_sections_in_tree_order(merged_sections)

        # Inyectar sección institucional de Carátula para Maestría UNAC si falta
        format_id = str(prompt_package.get("format_id") or prompt_package.get("_meta", {}).get("id") or "").lower()
        if "maestria" in format_id:
            special_key = "titulo-info-basica"
            if not any(special_key in self._section_keys(s) for s in merged_sections):
                merged_sections.insert(0, {
                    "section_id": special_key,
                    "section_path": "Título + Información Básica",
                    "section_title": "Título + Información Básica",
                    "section_order": -100,
                    "default_selected": True,
                    "optional": False,
                    "blocks": [
                        {
                            "block_id": "block:titulo-info",
                            "header": "Validación de Título e Información Básica",
                            "label": "Validación de Título e Información Básica",
                            "required": True,
                        }
                    ],
                })

        selected_keys = self._resolve_selected_keys(
            selected_sections=selected_sections,
            merged_sections=merged_sections,
        )
        planned: List[Dict[str, Any]] = []
        for section in merged_sections:
            # SI SE PROPORCIONÓ UNA SELECCIÓN MANUAL, DEBEMOS RESPETARLA ESTRICTAMENTE.
            # No permitimos fallback a 'todo' si selected_sections no es None.
            if selected_sections is not None:
                if not selected_keys or not self._section_keys(section).intersection(selected_keys):
                    continue
            else:
                # Si selected_sections es None, usamos fallback a por defecto
                if not self._section_keys(section).intersection(selected_keys):
                    continue
            normalized_blocks = self._section_blocks(section)
            planned.append(
                {
                    "sectionId": str(section.get("section_id") or "").strip(),
                    "path": str(section.get("section_path") or "").strip(),
                    "title": str(section.get("section_title") or "").strip(),
                    "parent_section_path": str(section.get("parent_section_path") or "").strip(),
                    "level": int(section.get("section_level") or 1),
                    "section_order": int(section.get("section_order") or 0),
                    "hints": str(section.get("source_hints") or "").strip(),
                    "optional": bool(section.get("optional")),
                    "default_selected": bool(section.get("default_selected")),
                    "blocks": normalized_blocks,
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
        if not isinstance(sections, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in sections:
            if not isinstance(item, dict):
                continue
            section_path = str(item.get("section_path") or item.get("path") or "").strip()
            section_id = str(item.get("section_id") or item.get("sectionId") or section_path).strip()
            if not section_id and not section_path:
                continue
            parent_path = str(item.get("parent_section_path") or item.get("parentSectionPath") or "").strip()
            title = str(item.get("section_title") or item.get("title") or "").strip()
            normalized.append(
                {
                    **dict(item),
                    "section_id": section_id or section_path,
                    "section_path": section_path or section_id,
                    "section_title": title or (section_path.split("/")[-1].strip() if section_path else section_id),
                    "parent_section_path": parent_path,
                    "section_level": max(1, int(item.get("section_level") or item.get("sectionLevel") or 1)),
                    "section_order": int(item.get("section_order") or item.get("sectionOrder") or 0),
                    "source_hints": str(item.get("source_hints") or item.get("sourceHints") or "").strip(),
                    "blocks": [
                        dict(block)
                        for block in (item.get("blocks") if isinstance(item.get("blocks"), list) else [])
                        if isinstance(block, dict)
                    ],
                }
            )
        return normalized

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

    @staticmethod
    def _section_path(section: Dict[str, Any]) -> str:
        return str(section.get("section_path") or section.get("path") or "").strip()

    @staticmethod
    def _section_title(section: Dict[str, Any]) -> str:
        title = str(section.get("section_title") or section.get("title") or "").strip()
        if title:
            return title
        path = ProjectGenerationPlanner._section_path(section)
        return path.split("/")[-1].strip() if path else ""

    def _section_has_children(
        self,
        section: Dict[str, Any],
        children_by_parent: Dict[str, List[Dict[str, Any]]],
    ) -> bool:
        return bool(children_by_parent.get(self._section_path(section)))

    def _section_has_own_blocks(self, section: Dict[str, Any]) -> bool:
        return bool(self._section_blocks(section))

    def _collect_descendant_paths(
        self,
        section_path: str,
        children_by_parent: Dict[str, List[Dict[str, Any]]],
    ) -> List[str]:
        descendants: List[str] = []
        for child in children_by_parent.get(section_path, []):
            child_path = self._section_path(child)
            if not child_path:
                continue
            descendants.append(child_path)
            descendants.extend(self._collect_descendant_paths(child_path, children_by_parent))
        return descendants

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
        path_to_section = {self._section_path(item): item for item in merged_sections if self._section_path(item)}
        children_by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for item in merged_sections:
            parent_path = str(item.get("parent_section_path") or "").strip()
            children_by_parent.setdefault(parent_path, []).append(item)

        if isinstance(selected_sections, list):
            raw_selected_keys: Set[str] = set()
            for item in selected_sections:
                if isinstance(item, str):
                    key = item.strip()
                    if key:
                        raw_selected_keys.add(key)
                    continue
                if not isinstance(item, dict):
                    continue
                raw_selected_keys.update(self._section_keys(item))
            
            # Si se proporcionó una lista (Vacía o con datos), expandimos lo que haya 
            # y retornamos. NO permitimos caída al default_keys de abajo.
            return self._expand_selected_keys(
                raw_selected_keys=raw_selected_keys,
                merged_sections=merged_sections,
                path_to_section=path_to_section,
                children_by_parent=children_by_parent,
            )

        # SOLO si selected_sections es estrictamente None (no se envió nada),
        # usamos los valores predeterminados del paquete.
        default_keys = {
            key
            for item in merged_sections
            if bool(item.get("default_selected", True))
            for key in self._section_keys(item)
        }
        return self._expand_selected_keys(
            raw_selected_keys=default_keys,
            merged_sections=merged_sections,
            path_to_section=path_to_section,
            children_by_parent=children_by_parent,
        )

    def _expand_selected_keys(
        self,
        *,
        raw_selected_keys: Set[str],
        merged_sections: List[Dict[str, Any]],
        path_to_section: Dict[str, Dict[str, Any]],
        children_by_parent: Dict[str, List[Dict[str, Any]]],
    ) -> Set[str]:
        expanded_paths: Set[str] = set()
        for key in raw_selected_keys:
            section = path_to_section.get(str(key or "").strip())
            if section is None:
                section = next(
                    (item for item in merged_sections if str(key or "").strip() in self._section_keys(item)),
                    None,
                )
            if not isinstance(section, dict):
                continue
            section_path = self._section_path(section)
            if not section_path:
                continue
            expanded_paths.add(section_path)
            expanded_paths.update(self._collect_descendant_paths(section_path, children_by_parent))

        resolved: Set[str] = set()
        for item in merged_sections:
            section_path = self._section_path(item)
            if not section_path or section_path not in expanded_paths:
                continue
            if self._section_has_children(item, children_by_parent) and not self._section_has_own_blocks(item):
                continue
            resolved.update(self._section_keys(item))
        return resolved

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

    def _collect_custom_package_sections(
        self,
        *,
        package_sections: List[Dict[str, Any]],
        matched_package_keys: Set[str],
    ) -> List[Dict[str, Any]]:
        custom_sections: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()
        for section in package_sections:
            section_keys = self._section_keys(section)
            section_path = self._section_path(section)
            if section_keys.intersection(matched_package_keys):
                continue
            if section_path and section_path in seen_paths:
                continue
            custom_sections.append(dict(section))
            if section_path:
                seen_paths.add(section_path)
        return custom_sections

    def _flatten_sections_in_tree_order(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tree = self.section_service.build_tree(sections)
        ordered: List[Dict[str, Any]] = []

        def visit(node: Dict[str, Any]) -> None:
            current = dict(node)
            current.pop("children", None)
            ordered.append(current)
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    visit(child)

        for node in tree:
            if isinstance(node, dict):
                visit(node)
        return ordered

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

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return " ".join(str(value or "").lower().split())

    def _section_blocks(self, section: Dict[str, Any]) -> List[Dict[str, Any]]:
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for index, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            header = str(
                block.get("header")
                or block.get("cabecera")
                or block.get("titulo_cabecera")
                or block.get("label")
                or f"Cabecera {index + 1}"
            ).strip()
            label = str(block.get("label") or block.get("header") or header or f"Prompt {index + 1}").strip()
            normalized.append(
                {
                    **dict(block),
                    "header": header,
                    "cabecera": header,
                    "label": label,
                    "instructions": str(block.get("instructions") or "").strip(),
                    "required_variables": self._normalize_variables(block.get("required_variables")),
                    "required": bool(block.get("required", True)),
                }
            )
        return normalized

    def _section_required_variables(self, section: Dict[str, Any]) -> List[str]:
        variables: List[str] = []
        seen: Set[str] = set()
        for block in self._section_blocks(section):
            for variable in self._normalize_variables(block.get("required_variables")):
                if variable in seen:
                    continue
                seen.add(variable)
                variables.append(variable)
        return variables

    def _diagram_text_guidance(self, block: Dict[str, Any]) -> str:
        haystack = self._normalize_text(
            " ".join(
                [
                    str(block.get("header") or "").strip(),
                    str(block.get("label") or "").strip(),
                    str(block.get("instructions") or "").strip(),
                ]
            )
        )
        if not haystack:
            return ""
        if "ishikawa" in haystack:
            return (
                "Devuelve solo texto estructurado listo para dibujar manualmente un Ishikawa; "
                "no generes imagen ni FIGURE_JSON; no describas vagamente; "
                "incluye problema central, categorias, subcausas, "
                "como ubicar cada rama y como interpretar el resultado."
            )
        if "pareto" in haystack:
            return (
                "Devuelve solo texto estructurado listo para graficar manualmente un Pareto; "
                "no generes imagen ni FIGURE_JSON; no describas vagamente; "
                "incluye items, frecuencias o pesos, orden descendente, "
                "acumulado, pasos de grafico e interpretacion del 80/20."
            )
        if "6m" in haystack:
            return (
                "Devuelve solo texto estructurado listo para dibujar manualmente un analisis 6M; "
                "no generes imagen ni FIGURE_JSON; no describas vagamente; "
                "usa Metodo, Mano de obra, Maquinaria, Materiales, "
                "Medicion y Medio ambiente, con subcausas e interpretacion."
            )
        if "chicago" in haystack:
            return (
                "Devuelve solo texto estructurado listo para dibujo manual; "
                "no generes imagen ni FIGURE_JSON; no describas vagamente; "
                "enumera componentes, orden de disposicion, pasos para construirlo e interpretacion."
            )
        return ""

    def _build_additional_context(self, section: Dict[str, Any]) -> str:
        parts: List[str] = []
        base_hints = str(section.get("source_hints") or "").strip()
        parent_path = str(section.get("parent_section_path") or "").strip()
        section_path = self._section_path(section)
        section_title = self._section_title(section)
        level = max(1, int(section.get("section_level") or section.get("level") or 1))
        section_order = max(0, int(section.get("section_order") or 0))
        chapter_parent = section_path.split("/")[0].strip() if section_path else ""

        hierarchy_lines = [
            f"- Capitulo padre: {chapter_parent or 'Sin capitulo padre'}",
            f"- Seccion actual: {section_title or section_path or 'Sin seccion'}",
            f"- Path completo: {section_path or section_title or 'Sin path'}",
            f"- Nivel jerarquico: {level}",
        ]
        if section_order:
            hierarchy_lines.append(f"- Orden institucional: {section_order}")
        if parent_path and parent_path != chapter_parent:
            hierarchy_lines.append(f"- Seccion padre inmediata: {parent_path.split('/')[-1].strip() or parent_path}")
        if base_hints:
            hierarchy_lines.append(f"- Hints de la seccion: {base_hints}")
        parts.append("Contexto jerarquico:\n" + "\n".join(hierarchy_lines))

        blocks = self._section_blocks(section)
        if not blocks:
            return "\n\n".join(part for part in parts if part)

        block_lines: List[str] = []
        for block in blocks:
            header = str(block.get("header") or "Bloque").strip()
            label = str(block.get("label") or header or "Bloque").strip()
            instructions = str(block.get("instructions") or "").strip()
            required = self._normalize_variables(block.get("required_variables"))
            block_lines.append(f"- Cabecera: {header}")
            if label and label != header:
                block_lines.append(f"  Etiqueta: {label}")
            if instructions:
                block_lines.append(f"  Instrucciones: {instructions}")
            if required:
                block_lines.append(f"  Variables requeridas: {', '.join(required)}")
            diagram_guidance = self._diagram_text_guidance(block)
            if diagram_guidance:
                block_lines.append(f"  Salida textual requerida: {diagram_guidance}")
        parts.append("Bloques de prompt activos:\n" + "\n".join(block_lines))
        return "\n\n".join(part for part in parts if part)

from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Set

from app.core.services.institutional_section_service import InstitutionalSectionService
from app.core.services.maestria_payload_mapper import is_maestria_format


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

        # Inyectar sección especial para validación rápida de título e información
        # básica en Maestría UNAC y Proyecto de Tesis UNAC.
        if is_maestria_format(prompt_package or {}):
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
            merged_sections = self._apply_single_table_per_chapter_policy(merged_sections)

        child_only_generation = is_maestria_format(prompt_package or {})
        selected_keys = self._resolve_selected_keys(
            selected_sections=selected_sections,
            merged_sections=merged_sections,
            child_only_generation=child_only_generation,
        )
        if is_maestria_format(prompt_package or {}):
            special_key = "titulo-info-basica"
            if any(special_key in self._section_keys(section) for section in merged_sections):
                selected_keys.add(special_key)
        planned: List[Dict[str, Any]] = []
        for section in merged_sections:
            section_path = self._section_path(section)
            if self._is_excluded_static_table_path(section_path):
                continue
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
                    "source_content_type": str(section.get("source_content_type") or "texto").strip().lower()
                    or "texto",
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
            section_path = self._canonicalize_schedule_budget_path(str(item.get("path") or "").strip())
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
        by_path: Dict[str, Dict[str, Any]] = {}
        for item in sections:
            if not isinstance(item, dict):
                continue
            raw_section_path = str(item.get("section_path") or item.get("path") or "").strip()
            section_path = ProjectGenerationPlanner._canonicalize_schedule_budget_path(raw_section_path)
            section_id = str(item.get("section_id") or item.get("sectionId") or section_path).strip()
            if not section_id and not section_path:
                continue
            if ProjectGenerationPlanner._is_misplaced_chapter_two_matrix_path(section_path):
                continue
            if ProjectGenerationPlanner._is_excluded_static_table_path(section_path):
                continue
            parent_path = str(item.get("parent_section_path") or item.get("parentSectionPath") or "").strip()
            title = str(item.get("section_title") or item.get("title") or "").strip()
            if section_path and raw_section_path and section_path != raw_section_path:
                parent_path = ""
                title = section_path.split("/")[-1].strip()

            entry = {
                **dict(item),
                "section_id": section_id or section_path,
                "section_path": section_path or section_id,
                "section_title": title or (section_path.split("/")[-1].strip() if section_path else section_id),
                "parent_section_path": parent_path,
                "section_level": max(1, int(item.get("section_level") or item.get("sectionLevel") or 1)),
                "section_order": int(item.get("section_order") or item.get("sectionOrder") or 0),
                "source_hints": str(item.get("source_hints") or item.get("sourceHints") or "").strip(),
                "source_content_type": str(
                    item.get("source_content_type") or item.get("sourceContentType") or "texto"
                )
                .strip()
                .lower()
                or "texto",
                "blocks": [
                    dict(block)
                    for block in (item.get("blocks") if isinstance(item.get("blocks"), list) else [])
                    if isinstance(block, dict)
                ],
            }

            dedupe_key = str(entry.get("section_path") or entry.get("section_id") or "").strip()
            if not dedupe_key:
                normalized.append(entry)
                continue
            existing = by_path.get(dedupe_key)
            if existing is None:
                by_path[dedupe_key] = entry
                normalized.append(entry)
                continue

            hints = [str(existing.get("source_hints") or "").strip(), str(entry.get("source_hints") or "").strip()]
            existing["source_hints"] = "\n".join(item for item in hints if item)
            existing["section_order"] = min(
                int(existing.get("section_order") or 0),
                int(entry.get("section_order") or 0),
            )
            if str(existing.get("source_content_type") or "") != "tabla" and str(entry.get("source_content_type") or "") == "tabla":
                existing["source_content_type"] = "tabla"
            if entry.get("blocks"):
                merged_blocks = list(existing.get("blocks") or [])
                merged_blocks.extend(entry["blocks"])
                existing["blocks"] = merged_blocks
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
        child_only_generation: bool = False,
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
                        raw_selected_keys.add(self._canonicalize_schedule_budget_path(key))
                    continue
                if not isinstance(item, dict):
                    continue
                raw_selected_keys.update(self._section_keys(item))
                section_path = str(
                    item.get("section_path") or item.get("sectionPath") or item.get("path") or ""
                ).strip()
                if section_path:
                    raw_selected_keys.add(self._canonicalize_schedule_budget_path(section_path))
            
            # Si se proporcionó una lista (Vacía o con datos), expandimos lo que haya 
            # y retornamos. NO permitimos caída al default_keys de abajo.
            return self._expand_selected_keys(
                raw_selected_keys=raw_selected_keys,
                merged_sections=merged_sections,
                path_to_section=path_to_section,
                children_by_parent=children_by_parent,
                child_only_generation=child_only_generation,
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
            child_only_generation=child_only_generation,
        )

    def _expand_selected_keys(
        self,
        *,
        raw_selected_keys: Set[str],
        merged_sections: List[Dict[str, Any]],
        path_to_section: Dict[str, Dict[str, Any]],
        children_by_parent: Dict[str, List[Dict[str, Any]]],
        child_only_generation: bool = False,
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
            if self._section_has_children(item, children_by_parent) and (
                child_only_generation or not self._section_has_own_blocks(item)
            ):
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
            merged["source_content_type"] = (
                str(
                    package_section.get("source_content_type")
                    or package_section.get("sourceContentType")
                    or merged.get("source_content_type")
                    or "texto"
                )
                .strip()
                .lower()
                or "texto"
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
            merged["source_content_type"] = str(merged.get("source_content_type") or "texto").strip().lower() or "texto"
            merged["blocks"] = []
        return merged

    def _apply_single_table_per_chapter_policy(self, merged_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """For UNAC proyecto/maestria, keep only one table subsection in V and VI."""
        if not merged_sections:
            return merged_sections

        by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for item in merged_sections:
            parent_path = str(item.get("parent_section_path") or "").strip()
            if parent_path:
                by_parent.setdefault(parent_path, []).append(item)

        chapter_predicates = (
            self._is_schedule_chapter_path,
            self._is_budget_chapter_path,
        )
        allowed_children_by_parent: Dict[str, str] = {}
        for parent_path, children in by_parent.items():
            if not any(predicate(parent_path) for predicate in chapter_predicates):
                continue
            table_children = [
                child
                for child in children
                if str(child.get("source_content_type") or "").strip().lower() == "tabla"
            ]
            if not table_children:
                continue
            selected = sorted(
                table_children,
                key=lambda child: (
                    int(child.get("section_order") or 0),
                    self._section_path(child),
                ),
            )[0]
            selected_path = self._section_path(selected)
            if selected_path:
                allowed_children_by_parent[parent_path] = selected_path

        if not allowed_children_by_parent:
            return merged_sections

        filtered: List[Dict[str, Any]] = []
        for item in merged_sections:
            item_path = self._section_path(item)
            parent_path = str(item.get("parent_section_path") or "").strip()
            allowed_child = allowed_children_by_parent.get(parent_path)
            if allowed_child and item_path and item_path != allowed_child:
                continue
            filtered.append(item)
        return filtered

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
        lowered = str(value or "").strip().lower()
        if not lowered:
            return ""
        ascii_only = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_only.split())

    @staticmethod
    def _is_misplaced_chapter_two_matrix_path(path: str) -> bool:
        normalized = ProjectGenerationPlanner._normalize_text(path)
        if "bases te" not in normalized:
            return False
        return "matriz de consistencia" in normalized or "matriz de operacionalizaci" in normalized

    @staticmethod
    def _is_excluded_static_table_path(path: str) -> bool:
        normalized = ProjectGenerationPlanner._normalize_text(path)
        if not normalized:
            return False
        if "cronograma resumido de actividades" in normalized:
            return True
        if "matriz de consistencia de implementaci" in normalized:
            return True
        return "matriz de operacionalizaci" in normalized and (
            "diseno" in normalized or "bases te" in normalized
        )

    @staticmethod
    def _is_schedule_chapter_path(path: str) -> bool:
        normalized = ProjectGenerationPlanner._normalize_text(path)
        return "v. cronograma de actividades" in normalized

    @staticmethod
    def _is_budget_chapter_path(path: str) -> bool:
        normalized = ProjectGenerationPlanner._normalize_text(path)
        return "vi. presupuesto" in normalized

    @classmethod
    def _canonicalize_schedule_budget_path(cls, path: str) -> str:
        raw = str(path or "").strip()
        if not raw:
            return ""
        parts = [part.strip() for part in raw.split("/") if part.strip()]
        if len(parts) <= 1:
            return raw
        chapter = parts[0]
        if cls._is_schedule_chapter_path(chapter) or cls._is_budget_chapter_path(chapter):
            return chapter
        return raw

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
        if "relevancia" in haystack:
            return (
                "Devuelve solo texto estructurado listo para construir manualmente una matriz de relevancia; "
                "no generes imagen ni FIGURE_JSON; no describas vagamente; "
                "incluye alternativas, criterios de evaluacion, lectura por celda, "
                "decision final y como interpretar alternativas descartadas o preseleccionadas."
            )
        if "priorizacion" in haystack or "priorización" in haystack:
            return (
                "Devuelve solo texto estructurado listo para construir manualmente una matriz de priorizacion; "
                "no generes imagen ni FIGURE_JSON; no describas vagamente; "
                "incluye criterios ponderados, pesos, puntajes por alternativa, "
                "total ponderado, nota de escala y como interpretar la alternativa ganadora."
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
        raw_section_order = section.get("section_order")
        section_order = int(raw_section_order) if raw_section_order not in (None, "") else 0
        chapter_parent = section_path.split("/")[0].strip() if section_path else ""

        hierarchy_lines = [
            f"- Capitulo padre: {chapter_parent or 'Sin capitulo padre'}",
            f"- Seccion actual: {section_title or section_path or 'Sin seccion'}",
            f"- Path completo: {section_path or section_title or 'Sin path'}",
            f"- Nivel jerarquico: {level}",
        ]
        if raw_section_order not in (None, ""):
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

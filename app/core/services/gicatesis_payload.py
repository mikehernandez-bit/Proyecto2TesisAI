"""Build a hierarchical GicaTesis payload from format + AI sections.

This module takes the **original format definition** and the flat
``aiResult.sections[]`` list and produces a *render-ready* copy of the
format where:

* Every section in ``preliminares`` (except ``indices``) that matches
  a generated section gets its ``texto`` replaced with AI content.
* Each ``cuerpo[i]`` chapter gains a ``desarrollo`` field if content
  was generated for that chapter path.
* Each ``cuerpo[i].contenido[j]`` item gains a ``desarrollo`` field.
* ``finales`` sections are injected similarly.
* Guidance fields (``nota``, ``instruccion_detallada``, ``nota_capitulo``,
  ``ejemplo``, ``guia``, ``comentario``) are moved into a ``_meta`` dict
  so the renderer never prints them.
* ``preliminares.indices`` is **preserved structurally** but never
  receives generated content.

The original format dict is **not** mutated — a deep copy is returned.
"""

from __future__ import annotations

import copy
import unicodedata
from typing import Any, Dict, List, Optional

from app.core.services.toc_detector import is_toc_path

# Fields that carry authoring guidance — not document content.
_GUIDANCE_FIELDS = frozenset(
    {
        "nota",
        "nota_capitulo",
        "instruccion_detallada",
        "instruccion",
        "guia",
        "ejemplo",
        "comentario",
    }
)

# Keys that are indices / TOC — never receive content.
_INDICES_KEYS = frozenset({"indices", "indice", "tabla_de_contenido", "toc"})


def _norm(value: str) -> str:
    """Accent-insensitive, whitespace-collapsed normalisation for matching."""
    lowered = (value or "").strip().lower()
    if not lowered:
        return ""
    ascii_only = (
        unicodedata.normalize("NFKD", lowered)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return " ".join(ascii_only.split())


def _build_content_map(
    sections: List[Dict[str, str]],
) -> Dict[str, str]:
    """Map *normalised path* → *content* for non-empty, non-TOC sections.

    Also stores original path → content for exact-match lookups.
    """
    cmap: Dict[str, str] = {}
    for sec in sections:
        path = (sec.get("path") or "").strip()
        content = (sec.get("content") or "").strip()
        if path and content and not is_toc_path(path):
            # Store both exact and normalised keys for flexible matching.
            cmap[path] = content
            normed = _norm(path)
            if normed and normed != path:
                cmap[normed] = content
    return cmap


def _match_content(
    content_map: Dict[str, str],
    path: str,
) -> Optional[str]:
    """Look up content by exact path, then by normalised path."""
    if not path:
        return None
    # Exact match first.
    hit = content_map.get(path)
    if hit:
        return hit
    # Normalised fallback.
    return content_map.get(_norm(path))


def _move_guidance_to_meta(obj: Dict[str, Any]) -> None:
    """Move guidance fields into ``obj["_meta"]`` in-place."""
    meta: Dict[str, Any] = {}
    for key in list(obj.keys()):
        if key in _GUIDANCE_FIELDS:
            meta[key] = obj.pop(key)
    if meta:
        obj.setdefault("_meta", {}).update(meta)


def _extract_title(obj: Dict[str, Any]) -> str:
    """Extract section title from an object using standard keys."""
    for key in ("titulo", "title", "titulo_seccion", "texto"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return " ".join(val.strip().split())
    return ""


def _inject_into_preliminares(
    preliminares: Dict[str, Any],
    content_map: Dict[str, str],
) -> None:
    """Walk ``preliminares`` items and inject content, skipping indices."""
    for key, item in preliminares.items():
        # Never inject into indices / TOC sections.
        if key.lower() in _INDICES_KEYS:
            continue
        if not isinstance(item, dict):
            continue

        title = _extract_title(item)
        if not title:
            continue

        _move_guidance_to_meta(item)

        matched = _match_content(content_map, title)
        if matched:
            # Content goes into "desarrollo" (body text), NOT "texto".
            # "texto" is rendered as a heading by GicaTesis — anything
            # placed there appears in the ÍNDICE (Word TOC).
            item["desarrollo"] = matched


def _inject_into_cuerpo(
    cuerpo: List[Dict[str, Any]],
    content_map: Dict[str, str],
    parent_path: str = "",
) -> None:
    """Walk ``cuerpo`` chapters and inject generated text."""
    for chapter in cuerpo:
        if not isinstance(chapter, dict):
            continue

        titulo = (chapter.get("titulo") or "").strip()
        titulo = " ".join(titulo.split())  # normalise whitespace
        chapter_path = f"{parent_path}/{titulo}" if parent_path else titulo

        _move_guidance_to_meta(chapter)

        # Inject chapter-level content.
        matched = _match_content(content_map, chapter_path)
        if matched:
            chapter["desarrollo"] = matched

        # Walk contenido sub-items.
        contenido = chapter.get("contenido")
        if isinstance(contenido, list):
            for item in contenido:
                if not isinstance(item, dict):
                    continue

                sub_title = (item.get("texto") or "").strip()
                sub_title = " ".join(sub_title.split())
                sub_path = (
                    f"{chapter_path}/{sub_title}" if sub_title else chapter_path
                )

                _move_guidance_to_meta(item)

                sub_matched = _match_content(content_map, sub_path)
                if sub_matched:
                    item["desarrollo"] = sub_matched

        # Walk secciones / subsecciones if present.
        for child_key in ("secciones", "subsecciones", "items"):
            child_list = chapter.get(child_key)
            if isinstance(child_list, list):
                _inject_into_cuerpo(child_list, content_map, chapter_path)


def _inject_into_finales(
    finales: Any,
    content_map: Dict[str, str],
    parent_path: str = "",
) -> None:
    """Walk ``finales`` sections and inject generated text."""
    if isinstance(finales, dict):
        for key, item in finales.items():
            if not isinstance(item, dict):
                continue

            title = _extract_title(item)
            item_path = (
                f"{parent_path}/{title}" if parent_path and title else title
            )

            _move_guidance_to_meta(item)

            if title:
                matched = _match_content(content_map, item_path)
                if not matched:
                    matched = _match_content(content_map, title)
                if matched:
                    item["desarrollo"] = matched

            # Handle lista sub-items (e.g. anexos.lista).
            lista = item.get("lista")
            if isinstance(lista, list):
                for sub_item in lista:
                    if not isinstance(sub_item, dict):
                        continue
                    sub_title = _extract_title(sub_item)
                    sub_path = (
                        f"{item_path}/{sub_title}"
                        if item_path and sub_title
                        else sub_title
                    )
                    _move_guidance_to_meta(sub_item)
                    if sub_title:
                        sub_matched = _match_content(
                            content_map, sub_path
                        )
                        if not sub_matched:
                            sub_matched = _match_content(
                                content_map, sub_title
                            )
                        if sub_matched:
                            sub_item["desarrollo"] = sub_matched


def build_gicatesis_payload(
    format_definition: Dict[str, Any],
    ai_sections: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Return a render-ready **deep copy** of *format_definition* with AI
    content injected and guidance fields hidden.

    Parameters
    ----------
    format_definition:
        The raw ``definition`` object from the format detail.
    ai_sections:
        ``aiResult["sections"]`` — list of ``{sectionId, path, content}``.

    Returns
    -------
    dict
        A copy of *format_definition* suitable for GicaTesis render,
        with ``desarrollo`` fields populated and guidance in ``_meta``.
    """
    payload = copy.deepcopy(format_definition)
    content_map = _build_content_map(ai_sections)

    # --- Preliminares (skip indices, inject into everything else) ---------
    preliminares = payload.get("preliminares")
    if isinstance(preliminares, dict):
        _inject_into_preliminares(preliminares, content_map)

    # --- Cuerpo (main body — array of chapters) --------------------------
    cuerpo = payload.get("cuerpo")
    if isinstance(cuerpo, list):
        _inject_into_cuerpo(cuerpo, content_map)

    # --- Finales (anexos, referencias, etc.) -----------------------------
    finales = payload.get("finales")
    if finales:
        _inject_into_finales(finales, content_map)

    return payload

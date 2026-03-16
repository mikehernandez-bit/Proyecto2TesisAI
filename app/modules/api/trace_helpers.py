"""Trace and observability helpers for project events.

Extracted from router.py to keep endpoint handlers thin.
These functions emit structured trace events to the project store.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from typing import Any, Dict, Optional

from app.core.services.project_service import ProjectService

TRACE_MAX_PREVIEW_CHARS = 400

_API_KEY_RE = re.compile(r"AIza[0-9A-Za-z\-_]{20,}")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+/]+=*", re.IGNORECASE)
_SECRET_FIELD_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|token|secret)\b\s*[:=]\s*([^\s,;]+)"
)


def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_text(value: Any) -> str:
    text = str(value or "")
    text = _API_KEY_RE.sub("[REDACTED_KEY]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _SECRET_FIELD_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    return " ".join(text.split())


def clip_text(value: Any, max_chars: int = TRACE_MAX_PREVIEW_CHARS) -> str:
    sanitized = sanitize_text(value)
    if len(sanitized) <= max_chars:
        return sanitized
    return f"{sanitized[: max_chars - 1]}…"


def sanitize_preview(
    preview: Optional[Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    if not isinstance(preview, dict):
        return None
    cleaned: Dict[str, str] = {}
    for key in ("prompt", "raw", "clean", "payload"):
        if key in preview and preview.get(key) is not None:
            cleaned[key] = clip_text(preview.get(key))
    return cleaned or None


def status_to_level(status: str) -> str:
    lowered = str(status or "").lower()
    if lowered in {"error", "failed"}:
        return "error"
    if lowered in {"warn", "warning"}:
        return "warn"
    if lowered == "done":
        return "info"
    return "info"


def emit_project_trace(
    project_id: str,
    *,
    step: str,
    status: str,
    title: str,
    detail: str = "",
    meta: Optional[Dict[str, Any]] = None,
    preview: Optional[Dict[str, Any]] = None,
    projects: Optional[ProjectService] = None,
) -> None:
    safe_meta: Dict[str, Any] = {}
    if isinstance(meta, dict) and meta:
        for key, value in meta.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_meta[key] = (
                    clip_text(value, 140) if isinstance(value, str) else value
                )
            elif isinstance(value, (list, dict)):
                try:
                    import json as _json

                    serialized = _json.dumps(value, ensure_ascii=False)
                    if len(serialized) <= 8192:
                        safe_meta[key] = value
                except Exception:
                    pass

    def _as_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    provider = str(
        safe_meta.get("provider")
        or safe_meta.get("to")
        or safe_meta.get("targetProvider")
        or ""
    )
    section_current = _as_int(
        safe_meta.get("sectionIndex") or safe_meta.get("sectionCurrent") or 0
    )
    section_total = _as_int(
        safe_meta.get("sectionTotal") or safe_meta.get("totalSections") or 0
    )
    section_path = str(
        safe_meta.get("sectionPath") or safe_meta.get("path") or ""
    )

    message = clip_text(
        f"{title}. {detail}" if detail else title,
        360,
    )
    event_stage = str(safe_meta.get("stage") or step)
    event: Dict[str, Any] = {
        "ts": utc_now_z(),
        "level": status_to_level(status),
        "stage": event_stage,
        "message": message,
        "provider": provider,
        "sectionCurrent": section_current,
        "sectionTotal": section_total,
        "sectionPath": section_path,
        "step": step,
        "status": status,
        "title": clip_text(title, 220),
    }
    if detail:
        event["detail"] = clip_text(detail, 360)
    if safe_meta:
        event["meta"] = safe_meta
    safe_preview = sanitize_preview(preview)
    if safe_preview:
        event["preview"] = safe_preview
    if projects is not None:
        projects.append_event(project_id, event)


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"

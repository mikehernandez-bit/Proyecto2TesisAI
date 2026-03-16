"""
GicaTesis Connectivity Status — in-memory singleton.

Tracks whether GicaTesis upstream is reachable so that endpoints
and the frontend can behave consistently (e.g. show an offline banner,
avoid futile asset requests, or reject requests in strict mode).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional


class GicaTesisStatus:
    """Mutable, in-memory connectivity state for GicaTesis upstream."""

    def __init__(self) -> None:
        self.online: bool = True
        self.last_success_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.data_source: str = "none"  # "live" | "cache" | "demo" | "none"

    def record_success(self, *, source: str = "live") -> None:
        self.online = True
        self.last_success_at = dt.datetime.now(dt.timezone.utc).isoformat()
        self.last_error = None
        self.data_source = source

    def record_failure(self, error: str, *, source: str = "cache") -> None:
        self.online = False
        self.last_error = error
        self.data_source = source

    def to_dict(self) -> Dict[str, Any]:
        return {
            "online": self.online,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "data_source": self.data_source,
        }


# Module-level singleton — imported by format_service and router.
gicatesis_status = GicaTesisStatus()

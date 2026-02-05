"""
GicaTesis Integration - Format Cache

SRP: Only persistence of format catalog and details.
No HTTP, no business logic. Just read/write to JSON file.

Responsibilities:
- Load/save cache from data/gicatesis_cache.json
- Store catalog version, ETag, and format list
- Store format details by ID
- Atomic writes (temp file + rename)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..types import FormatSummary, FormatDetail


CACHE_PATH = Path("data/gicatesis_cache.json")


class FormatCache:
    """
    Persists format catalog and details with ETag support.
    
    SRP: Only read/write operations, no HTTP or business logic.
    
    Cache structure:
    {
        "catalogVersion": "sha256-hash",
        "catalogEtag": "\"etag-value\"",
        "formats": [FormatSummary, ...],
        "detailsById": {"id": FormatDetail, ...},
        "lastSyncAt": "2026-02-05T12:00:00"
    }
    """
    
    def __init__(self, cache_path: Optional[Path] = None):
        self._path = cache_path or CACHE_PATH
        self._data: Dict[str, Any] = {
            "catalogVersion": None,
            "catalogEtag": None,
            "formats": [],
            "detailsById": {},
            "lastSyncAt": None
        }
        self.load()
    
    def load(self) -> None:
        """Load cache from disk if exists."""
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                # Corrupted cache, start fresh
                pass
    
    def save(self) -> None:
        """
        Save cache to disk atomically.
        Uses temp file + rename to prevent corruption.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8"
        )
        tmp.replace(self._path)
    
    # --- Catalog properties ---
    
    @property
    def catalog_version(self) -> Optional[str]:
        """Get cached catalog version hash."""
        return self._data.get("catalogVersion")
    
    @property
    def catalog_etag(self) -> Optional[str]:
        """Get cached catalog ETag for If-None-Match."""
        return self._data.get("catalogEtag")
    
    @property
    def last_sync_at(self) -> Optional[str]:
        """Get timestamp of last successful sync."""
        return self._data.get("lastSyncAt")
    
    # --- Catalog operations ---
    
    def get_formats(self) -> List[Dict[str, Any]]:
        """Get cached format list."""
        return self._data.get("formats", [])
    
    def set_catalog(
        self,
        version: Optional[str],
        etag: Optional[str],
        formats: List[FormatSummary]
    ) -> None:
        """
        Update cached catalog with new data.
        
        Args:
            version: Catalog version hash from /formats/version
            etag: ETag header from /formats response
            formats: List of FormatSummary objects
        """
        self._data["catalogVersion"] = version
        self._data["catalogEtag"] = etag
        self._data["formats"] = [f.model_dump() for f in formats]
        self._data["lastSyncAt"] = datetime.now().isoformat()
        self.save()
    
    # --- Detail operations ---
    
    def get_detail(self, format_id: str) -> Optional[Dict[str, Any]]:
        """Get cached format detail by ID."""
        return self._data.get("detailsById", {}).get(format_id)
    
    def set_detail(self, format_id: str, detail: FormatDetail) -> None:
        """
        Cache a format detail.
        
        Args:
            format_id: Format ID
            detail: FormatDetail object to cache
        """
        if "detailsById" not in self._data:
            self._data["detailsById"] = {}
        self._data["detailsById"][format_id] = detail.model_dump()
        self.save()
    
    # --- Utility ---
    
    def has_cache(self) -> bool:
        """Check if we have any cached formats."""
        return bool(self._data.get("formats"))
    
    def clear(self) -> None:
        """Clear all cached data."""
        self._data = {
            "catalogVersion": None,
            "catalogEtag": None,
            "formats": [],
            "detailsById": {},
            "lastSyncAt": None
        }
        self.save()

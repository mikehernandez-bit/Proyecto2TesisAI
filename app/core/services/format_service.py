"""
Format Service - Orchestration Layer

SRP: Only business logic orchestration.
Combines client (HTTP) + cache (persistence) to provide format data.

Responsibilities:
- Version checking and catalog sync decisions
- Fallback to cache when GicaTesis is unavailable
- In-memory filtering of cached formats
- Detail fetching with cache
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.services.gicatesis_status import gicatesis_status
from app.integrations.gicatesis.cache.format_cache import FormatCache
from app.integrations.gicatesis.client import GicaTesisClient
from app.integrations.gicatesis.errors import GicaTesisError
from app.integrations.gicatesis.types import FormatDetail

logger = logging.getLogger(__name__)


class FormatService:
    """
    Orchestrates format catalog access with cache.

    SRP: Business logic only - delegates HTTP to client, persistence to cache.

    Features:
    - ETag-based cache validation (304 handling)
    - Automatic fallback to cache when GicaTesis is down
    - In-memory filtering for university/category/documentType
    """

    def __init__(self):
        self.client = GicaTesisClient()
        self.cache = FormatCache()
        self._demo_sample_path = Path("data/formats_sample.json")

    @staticmethod
    def _gicatesis_hint() -> str:
        return (
            "No se pudo conectar a GicaTesis en "
            f"{settings.GICATESIS_BASE_URL}. Levanta GicaTesis en :8000 "
            "o actualiza GICATESIS_BASE_URL. Para pruebas de catalogo sin "
            "upstream, puedes usar GICAGEN_DEMO_MODE=true."
        )

    def _load_demo_formats(self) -> List[Dict[str, Any]]:
        """
        Load demo formats from local sample file.

        Used only when `GICAGEN_DEMO_MODE=true` and upstream/cache are unavailable.
        """
        if not self._demo_sample_path.exists():
            return []
        try:
            raw = json.loads(self._demo_sample_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "id": item.get("id") or "",
                    "title": item.get("title") or item.get("name") or item.get("id") or "Formato",
                    "university": item.get("university") or item.get("short") or "demo",
                    "category": item.get("category") or item.get("career") or "general",
                    "documentType": item.get("documentType") or item.get("doc_type"),
                    "version": item.get("version")
                    or hashlib.sha256(str(item.get("id", "demo")).encode("utf-8")).hexdigest()[:16],
                }
            )
        return normalized

    def _demo_catalog_version(self, formats: List[Dict[str, Any]]) -> str:
        payload = json.dumps(formats, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def check_version(self) -> Dict[str, Any]:
        """
        Check if catalog version changed.

        Returns dict with:
        - current: Current version from GicaTesis (or None if unavailable)
        - cached: Cached version (or None if no cache)
        - changed: True if versions differ
        - generatedAt: Generation timestamp from GicaTesis
        - stale: True if using stale cache due to GicaTesis being down
        - error: Error message if GicaTesis unavailable
        """
        try:
            response = await self.client.get_catalog_version()
            cached = self.cache.catalog_version
            return {
                "current": response.version,
                "cached": cached,
                "changed": cached != response.version,
                "generatedAt": response.generatedAt,
                "stale": False,
            }
        except GicaTesisError as e:
            logger.warning("GicaTesis unavailable for version check: %s", e)
            if self.cache.has_cache():
                return {
                    "current": None,
                    "cached": self.cache.catalog_version,
                    "changed": False,
                    "error": self._gicatesis_hint(),
                    "stale": True,
                }
            if settings.GICAGEN_DEMO_MODE:
                demo_formats = self._load_demo_formats()
                demo_version = self._demo_catalog_version(demo_formats)
                return {
                    "current": demo_version,
                    "cached": None,
                    "changed": True,
                    "generatedAt": None,
                    "stale": True,
                    "source": "demo",
                }
            raise

    async def sync_catalog_if_needed(self, force: bool = False) -> None:
        """
        Sync catalog from GicaTesis if needed.

        Args:
            force: Force sync even if cache exists

        Sync happens if:
        - force=True
        - No cache exists
        - Version check indicates changes

        Uses ETag for efficient 304 handling.
        """
        # Skip sync if cache exists and not forced
        if not force and self.cache.has_cache():
            try:
                version_check = await self.check_version()
                if not version_check.get("changed") and not version_check.get("stale"):
                    logger.debug("Catalog not changed, skipping sync")
                    return
            except GicaTesisError:
                logger.info("GicaTesis unavailable, using existing cache")
                return

        # Attempt sync
        try:
            status, formats, etag = await self.client.list_formats(etag=self.cache.catalog_etag)

            if status == 304:
                logger.info("Catalog not modified (304), cache is valid")
                return

            if status == 200 and formats is not None:
                # Get version for cache metadata
                try:
                    version_resp = await self.client.get_catalog_version()
                    version = version_resp.version
                except GicaTesisError:
                    version = None

                self.cache.set_catalog(version, etag, formats)
                logger.info(f"Catalog synced: {len(formats)} formats")
                gicatesis_status.record_success(source="live")

        except GicaTesisError as e:
            if not self.cache.has_cache():
                gicatesis_status.record_failure(str(e), source="none")
                raise
            gicatesis_status.record_failure(str(e), source="cache")
            logger.warning(f"GicaTesis unavailable during sync, using cache: {e}")

    async def list_formats(
        self, university: Optional[str] = None, category: Optional[str] = None, document_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List formats with optional filtering.

        Syncs catalog if needed, then filters in memory.

        Returns dict with:
        - formats: List of FormatSummary dicts
        - stale: True if data is from stale cache
        - cachedAt: Timestamp of last sync
        """
        stale = False
        try:
            await self.sync_catalog_if_needed()
        except GicaTesisError:
            if not self.cache.has_cache() and not settings.GICAGEN_DEMO_MODE:
                raise
            stale = True

        formats = self.cache.get_formats()
        source = "cache"

        if not formats and stale and settings.GICAGEN_DEMO_MODE:
            formats = self._load_demo_formats()
            source = "demo"

        # Filter in memory
        if university:
            formats = [f for f in formats if f.get("university", "").lower() == university.lower()]
        if category:
            formats = [f for f in formats if f.get("category", "").lower() == category.lower()]
        if document_type:
            formats = [f for f in formats if (f.get("documentType") or "").lower() == document_type.lower()]

        return {"formats": formats, "stale": stale, "cachedAt": self.cache.last_sync_at, "source": source}

    async def get_format_detail(self, format_id: str) -> Optional[FormatDetail]:
        """
        Get full format detail with caching.

        Checks cache first, fetches from GicaTesis if not cached.

        Returns FormatDetail or None if not found.
        """
        # Check cache first
        cached = self.cache.get_detail(format_id)
        if cached and isinstance(cached.get("definition"), dict):
            logger.debug(f"Format detail cache hit: {format_id}")
            return FormatDetail(**cached)
        if cached:
            logger.info(f"Format detail cache refresh required (missing definition): {format_id}")

        # Fetch from GicaTesis
        try:
            detail = await self.client.get_format_detail(format_id)
            if detail:
                self.cache.set_detail(format_id, detail)
                logger.info(f"Format detail cached: {format_id}")
            return detail
        except GicaTesisError as e:
            logger.warning(
                "Cannot fetch format detail %s: %s. %s",
                format_id,
                e,
                self._gicatesis_hint(),
            )
            if settings.GICAGEN_DEMO_MODE:
                for item in self._load_demo_formats():
                    if item.get("id") != format_id:
                        continue
                    return FormatDetail(
                        id=item["id"],
                        title=item["title"],
                        university=item["university"],
                        category=item["category"],
                        documentType=item.get("documentType"),
                        version=item["version"],
                        fields=[],
                        assets=[],
                        rules=None,
                        templateRef=None,
                    )
            return None

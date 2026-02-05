"""
GicaTesis Integration - HTTP Client

SRP: Only HTTP communication with GicaTesis API.
No caching, no business logic. Just requests and response parsing.

Responsibilities:
- HTTP GET requests to GicaTesis endpoints
- Timeout handling (default 8s)
- ETag header management (If-None-Match)
- Error translation to custom exceptions
"""
from __future__ import annotations

import httpx
from typing import Optional, List, Tuple

from app.core.config import settings
from .errors import UpstreamUnavailable, UpstreamTimeout, BadUpstreamResponse
from .types import FormatSummary, FormatDetail, CatalogVersionResponse


class GicaTesisClient:
    """
    HTTP client for GicaTesis Formats API v1.
    
    SRP: Only HTTP, no cache logic.
    
    Endpoints:
    - GET /formats/version - Catalog version check
    - GET /formats - List all formats (supports ETag)
    - GET /formats/{id} - Format detail
    """
    
    def __init__(self):
        self.base_url = settings.GICATESIS_BASE_URL.rstrip("/")
        self.timeout = settings.GICATESIS_TIMEOUT
    
    async def get_catalog_version(self) -> CatalogVersionResponse:
        """
        GET /formats/version
        
        Returns the current catalog version hash and generation timestamp.
        Used for quick version checks before syncing.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(f"{self.base_url}/formats/version")
                r.raise_for_status()
                return CatalogVersionResponse(**r.json())
        except httpx.ConnectError as e:
            raise UpstreamUnavailable(f"Cannot connect to GicaTesis: {e}")
        except httpx.TimeoutException:
            raise UpstreamTimeout(f"GicaTesis timeout after {self.timeout}s")
        except Exception as e:
            raise BadUpstreamResponse(f"Unexpected error: {e}")
    
    async def list_formats(
        self,
        university: Optional[str] = None,
        category: Optional[str] = None,
        document_type: Optional[str] = None,
        etag: Optional[str] = None
    ) -> Tuple[int, Optional[List[FormatSummary]], Optional[str]]:
        """
        GET /formats with optional ETag support.
        
        Args:
            university: Filter by university code (e.g., "unac")
            category: Filter by category (e.g., "informe")
            document_type: Filter by document type (e.g., "cual")
            etag: Previous ETag for If-None-Match header
        
        Returns:
            Tuple of (status_code, data_or_none, new_etag_or_none)
            - 200: (200, [FormatSummary, ...], "new-etag")
            - 304: (304, None, None) - Cache is still valid
        """
        headers = {}
        if etag:
            # ETag must be sent exactly as received (with quotes if present)
            headers["If-None-Match"] = etag
        
        params = {}
        if university:
            params["university"] = university
        if category:
            params["category"] = category
        if document_type:
            params["documentType"] = document_type
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    f"{self.base_url}/formats",
                    params=params,
                    headers=headers
                )
                
                # Handle 304 Not Modified
                if r.status_code == 304:
                    return 304, None, None
                
                r.raise_for_status()
                
                # Extract ETag from response headers
                new_etag = r.headers.get("ETag")
                
                # Parse response
                data = [FormatSummary(**item) for item in r.json()]
                return 200, data, new_etag
                
        except httpx.ConnectError as e:
            raise UpstreamUnavailable(f"Cannot connect to GicaTesis: {e}")
        except httpx.TimeoutException:
            raise UpstreamTimeout(f"GicaTesis timeout after {self.timeout}s")
        except Exception as e:
            raise BadUpstreamResponse(f"Unexpected error: {e}")
    
    async def get_format_detail(self, format_id: str) -> Optional[FormatDetail]:
        """
        GET /formats/{id}
        
        Returns full format details including fields for wizard.
        Returns None if format not found (404).
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(f"{self.base_url}/formats/{format_id}")
                
                if r.status_code == 404:
                    return None
                
                r.raise_for_status()
                return FormatDetail(**r.json())
                
        except httpx.ConnectError as e:
            raise UpstreamUnavailable(f"Cannot connect to GicaTesis: {e}")
        except httpx.TimeoutException:
            raise UpstreamTimeout(f"GicaTesis timeout after {self.timeout}s")
        except Exception as e:
            raise BadUpstreamResponse(f"Unexpected error: {e}")

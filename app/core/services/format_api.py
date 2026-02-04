from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from app.core.config import settings

SAMPLE_PATH = Path("data/formats_sample.json")

class FormatService:
    """Provides institutional formats for Step 1.

    MODES:
      - Demo: reads data/formats_sample.json
      - Real: set FORMAT_API_BASE_URL (+ optional FORMAT_API_KEY)

    TODO (DEV): adjust endpoint and mapping if your API differs.
    """

    async def list_formats(self, university: Optional[str] = None, career: Optional[str] = None) -> List[Dict[str, Any]]:
        if settings.FORMAT_API_BASE_URL:
            url = f"{settings.FORMAT_API_BASE_URL.rstrip('/')}/formats"
            headers = {}
            if settings.FORMAT_API_KEY:
                headers["Authorization"] = f"Bearer {settings.FORMAT_API_KEY}"
            params = {}
            if university: params["university"] = university
            if career: params["career"] = career

            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, params=params, headers=headers)
                r.raise_for_status()
                data = r.json()

            # TODO (DEV): return list mapped to:
            # id, university, short, career, name, version, includes[]
            return data

        if not SAMPLE_PATH.exists():
            return []

        items = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        if university:
            items = [x for x in items if university.lower() in x.get("university", "").lower()]
        if career:
            items = [x for x in items if career.lower() in x.get("career", "").lower()]
        return items

from __future__ import annotations

from typing import Any, Dict
import httpx
from app.core.config import settings

class N8NClient:
    """Client to call n8n (optional).
    If N8N_WEBHOOK_URL is empty, caller should fall back to demo.
    """

    async def trigger(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not settings.N8N_WEBHOOK_URL:
            return {"ok": False, "reason": "N8N_WEBHOOK_URL not configured"}

        headers = {}
        if settings.N8N_SHARED_SECRET:
            headers["X-GICAGEN-SECRET"] = settings.N8N_SHARED_SECRET

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(settings.N8N_WEBHOOK_URL, json=payload, headers=headers)
            r.raise_for_status()
            return {"ok": True, "data": r.json()}

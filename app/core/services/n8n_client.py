from __future__ import annotations

import time
from typing import Any, Dict
import httpx
from app.core.config import settings

PING_TIMEOUT = 30  # seconds
TRIGGER_TIMEOUT = 600  # seconds


class N8NClient:
    """Client to call n8n webhook.

    If N8N_WEBHOOK_URL is empty, returns configured=False so callers
    can fall back to demo mode.
    """

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if settings.N8N_SHARED_SECRET:
            h["X-GICAGEN-SECRET"] = settings.N8N_SHARED_SECRET
        return h

    # ------------------------------------------------------------------
    # Health / Ping
    # ------------------------------------------------------------------
    async def ping(self) -> Dict[str, Any]:
        """POST a lightweight ping to the webhook and report reachability."""
        result: Dict[str, Any] = {
            "configured": bool(settings.N8N_WEBHOOK_URL),
            "webhookUrl": "present" if settings.N8N_WEBHOOK_URL else "missing",
            "secret": "present" if settings.N8N_SHARED_SECRET else "missing",
            "reachable": False,
            "statusCode": None,
            "latencyMs": None,
            "message": "",
        }

        if not settings.N8N_WEBHOOK_URL:
            result["message"] = "N8N_WEBHOOK_URL no configurada"
            return result

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=PING_TIMEOUT) as client:
                r = await client.post(
                    settings.N8N_WEBHOOK_URL,
                    json={"type": "ping", "source": "gicagen"},
                    headers=self._headers(),
                )
            elapsed = int((time.monotonic() - t0) * 1000)
            result["statusCode"] = r.status_code
            result["latencyMs"] = elapsed

            if r.status_code in (200, 202):
                result["reachable"] = True
                result["message"] = f"Conectado a n8n ({r.status_code}, {elapsed}ms)"
            elif r.status_code in (401, 403):
                result["reachable"] = True
                result["message"] = f"Webhook alcanzable pero secreto invalido ({r.status_code})"
            elif r.status_code == 404:
                result["message"] = "Webhook no encontrado (404). Verifica la URL."
            else:
                result["message"] = f"Respuesta inesperada: HTTP {r.status_code}"
        except httpx.TimeoutException:
            elapsed = int((time.monotonic() - t0) * 1000)
            result["latencyMs"] = elapsed
            result["message"] = f"Timeout al conectar ({elapsed}ms). Verifica que n8n este activo."
        except httpx.ConnectError:
            result["message"] = "No se pudo conectar. Verifica la URL y que n8n este corriendo."
        except Exception as exc:
            result["message"] = f"Error inesperado: {exc}"

        return result

    # ------------------------------------------------------------------
    # Trigger (real workflow)
    # ------------------------------------------------------------------
    async def trigger(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST the generation payload to the n8n webhook.

        Returns {"ok": True/False, "data": ..., "statusCode": ..., "error": ...}
        """
        if not settings.N8N_WEBHOOK_URL:
            return {"ok": False, "error": "N8N_WEBHOOK_URL no configurada"}

        try:
            async with httpx.AsyncClient(timeout=TRIGGER_TIMEOUT) as client:
                r = await client.post(
                    settings.N8N_WEBHOOK_URL,
                    json=payload,
                    headers=self._headers(),
                )

            if r.status_code in (200, 202):
                try:
                    body = r.json()
                except Exception:
                    body = {}
                return {
                    "ok": True,
                    "statusCode": r.status_code,
                    "data": body,
                }

            return {
                "ok": False,
                "statusCode": r.status_code,
                "error": f"n8n respondio HTTP {r.status_code}",
            }

        except httpx.TimeoutException:
            return {"ok": False, "error": "Timeout al enviar a n8n"}
        except httpx.ConnectError:
            return {"ok": False, "error": "No se pudo conectar a n8n"}
        except Exception as exc:
            return {"ok": False, "error": f"Error: {exc}"}


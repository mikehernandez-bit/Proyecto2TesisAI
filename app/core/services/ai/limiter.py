"""Combined limiter: provider concurrency + tenant concurrency + RPM."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager, contextmanager
from typing import Dict, Iterator, Optional, Tuple

from app.core.services.ai.rate_limiter import SlidingWindowRateLimiter


class LLMLimiter:
    """Coordinates queueing and resource limits for provider calls."""

    def __init__(
        self,
        *,
        provider_concurrency: Dict[str, int],
        provider_rpm: Dict[str, int],
        max_inflight_per_tenant: int = 0,
        default_concurrency: int = 2,
        default_rpm: int = 60,
        rate_window_seconds: float = 60.0,
    ) -> None:
        self._provider_concurrency = {str(k): max(1, int(v)) for k, v in (provider_concurrency or {}).items()}
        self._provider_rpm = {str(k): max(1, int(v)) for k, v in (provider_rpm or {}).items()}
        self._max_inflight_per_tenant = max(0, int(max_inflight_per_tenant))
        self._default_concurrency = max(1, int(default_concurrency))
        self._default_rpm = max(1, int(default_rpm))
        self._rate_window_seconds = max(0.1, float(rate_window_seconds))

        self._lock = threading.RLock()
        self._provider_semaphores: Dict[str, threading.BoundedSemaphore] = {}
        self._tenant_semaphores: Dict[Tuple[str, str], threading.BoundedSemaphore] = {}
        self._rate_limiters: Dict[str, SlidingWindowRateLimiter] = {}
        self._waiting_by_provider: Dict[str, int] = {}

    def _provider_limit(self, provider: str) -> int:
        return self._provider_concurrency.get(provider, self._default_concurrency)

    def _provider_rpm_limit(self, provider: str) -> int:
        return self._provider_rpm.get(provider, self._default_rpm)

    def _provider_semaphore(self, provider: str) -> threading.BoundedSemaphore:
        with self._lock:
            if provider not in self._provider_semaphores:
                self._provider_semaphores[provider] = threading.BoundedSemaphore(self._provider_limit(provider))
            return self._provider_semaphores[provider]

    def _tenant_semaphore(self, provider: str, tenant_id: Optional[str]) -> Optional[threading.BoundedSemaphore]:
        if self._max_inflight_per_tenant <= 0 or not tenant_id:
            return None
        key = (provider, str(tenant_id))
        with self._lock:
            if key not in self._tenant_semaphores:
                self._tenant_semaphores[key] = threading.BoundedSemaphore(self._max_inflight_per_tenant)
            return self._tenant_semaphores[key]

    def _provider_rate_limiter(self, provider: str) -> SlidingWindowRateLimiter:
        with self._lock:
            if provider not in self._rate_limiters:
                self._rate_limiters[provider] = SlidingWindowRateLimiter(
                    self._provider_rpm_limit(provider),
                    window_seconds=self._rate_window_seconds,
                )
            return self._rate_limiters[provider]

    def _inc_waiting(self, provider: str) -> None:
        with self._lock:
            self._waiting_by_provider[provider] = int(self._waiting_by_provider.get(provider, 0)) + 1

    def _dec_waiting(self, provider: str) -> None:
        with self._lock:
            current = int(self._waiting_by_provider.get(provider, 0))
            self._waiting_by_provider[provider] = max(0, current - 1)

    @contextmanager
    def acquire_sync(self, provider: str, tenant_id: Optional[str] = None) -> Iterator[None]:
        """Blocking context manager for thread-based execution paths."""
        safe_provider = str(provider or "")
        provider_sem = self._provider_semaphore(safe_provider)
        tenant_sem = self._tenant_semaphore(safe_provider, tenant_id)
        rate_limiter = self._provider_rate_limiter(safe_provider)

        self._inc_waiting(safe_provider)
        provider_sem.acquire()
        self._dec_waiting(safe_provider)

        if tenant_sem is not None:
            tenant_sem.acquire()

        try:
            rate_limiter.acquire_sync()
            yield
        finally:
            if tenant_sem is not None:
                tenant_sem.release()
            provider_sem.release()

    @asynccontextmanager
    async def acquire(self, provider: str, tenant_id: Optional[str] = None):
        """Async context manager for async execution paths."""
        safe_provider = str(provider or "")
        provider_sem = self._provider_semaphore(safe_provider)
        tenant_sem = self._tenant_semaphore(safe_provider, tenant_id)
        rate_limiter = self._provider_rate_limiter(safe_provider)

        self._inc_waiting(safe_provider)
        await asyncio.to_thread(provider_sem.acquire)
        self._dec_waiting(safe_provider)

        if tenant_sem is not None:
            await asyncio.to_thread(tenant_sem.acquire)

        try:
            await rate_limiter.acquire()
            yield
        finally:
            if tenant_sem is not None:
                tenant_sem.release()
            provider_sem.release()

    def queue_depth(self, provider: str) -> int:
        with self._lock:
            return int(self._waiting_by_provider.get(provider, 0))

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            providers = set(self._provider_semaphores) | set(self._rate_limiters) | set(self._waiting_by_provider)

        payload: Dict[str, Dict[str, int]] = {}
        for provider in sorted(providers):
            limiter = self._provider_rate_limiter(provider)
            payload[provider] = {
                "queue_depth": self.queue_depth(provider),
                "concurrency_limit": self._provider_limit(provider),
                "rpm_limit": self._provider_rpm_limit(provider),
                "window_usage": limiter.window_usage(),
            }
        return payload

"""Unit tests for combined concurrency/RPM limiter."""

from __future__ import annotations

import threading
import time

from app.core.services.ai.limiter import LLMLimiter


def test_limiter_blocks_when_provider_concurrency_reached() -> None:
    limiter = LLMLimiter(
        provider_concurrency={"mistral": 1},
        provider_rpm={"mistral": 60},
        max_inflight_per_tenant=0,
    )

    release_first = threading.Event()
    first_entered = threading.Event()
    second_entered = threading.Event()

    def first_worker() -> None:
        with limiter.acquire_sync("mistral", tenant_id="tenant-a"):
            first_entered.set()
            release_first.wait(timeout=2)

    def second_worker() -> None:
        with limiter.acquire_sync("mistral", tenant_id="tenant-b"):
            second_entered.set()

    t1 = threading.Thread(target=first_worker, daemon=True)
    t2 = threading.Thread(target=second_worker, daemon=True)
    t1.start()
    assert first_entered.wait(timeout=1.0)

    t2.start()
    time.sleep(0.1)
    assert second_entered.is_set() is False
    assert limiter.queue_depth("mistral") >= 1

    release_first.set()
    t1.join(timeout=1.0)
    t2.join(timeout=1.0)
    assert second_entered.is_set() is True


def test_limiter_enforces_provider_rpm_window() -> None:
    limiter = LLMLimiter(
        provider_concurrency={"mistral": 2},
        provider_rpm={"mistral": 1},
        max_inflight_per_tenant=0,
        rate_window_seconds=1.0,
    )

    started = time.monotonic()
    with limiter.acquire_sync("mistral", tenant_id="tenant-a"):
        pass
    with limiter.acquire_sync("mistral", tenant_id="tenant-a"):
        pass
    elapsed = time.monotonic() - started

    # One request/min-window means second call must wait for the sliding window.
    assert elapsed >= 0.9

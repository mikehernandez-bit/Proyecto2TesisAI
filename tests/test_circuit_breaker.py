"""Unit tests for circuit breaker state transitions."""

from app.core.services.ai.circuit_breaker import CircuitBreaker


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


def test_circuit_breaker_opens_then_recovers_on_success() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(
        failures_threshold=2,
        window_seconds=10,
        open_seconds=5,
        half_open_max_trials=1,
        time_fn=clock.monotonic,
    )

    assert breaker.before_call("mistral") is True
    breaker.on_failure("mistral", reason="timeout")
    assert breaker.current_state("mistral") == "closed"

    breaker.on_failure("mistral", reason="timeout")
    assert breaker.current_state("mistral") == "open"
    assert breaker.before_call("mistral") is False

    clock.advance(5)
    assert breaker.current_state("mistral") == "half_open"
    assert breaker.before_call("mistral") is True

    breaker.on_success("mistral")
    assert breaker.current_state("mistral") == "closed"


def test_circuit_breaker_reopens_on_half_open_failure() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(
        failures_threshold=1,
        window_seconds=10,
        open_seconds=4,
        half_open_max_trials=1,
        time_fn=clock.monotonic,
    )

    breaker.on_failure("gemini", reason="timeout")
    assert breaker.current_state("gemini") == "open"

    clock.advance(4)
    assert breaker.before_call("gemini") is True  # half-open trial
    breaker.on_failure("gemini", reason="timeout")

    assert breaker.current_state("gemini") == "open"
    assert breaker.before_call("gemini") is False

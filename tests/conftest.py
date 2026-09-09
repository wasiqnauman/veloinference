"""Shared test fixtures."""


class FakeClock:
    """Deterministic monotonic clock for policy and scheduler tests."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        """Return the current fake time."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Advance fake time by a nonnegative duration."""
        if seconds < 0:
            raise ValueError("seconds must be nonnegative")
        self.now += seconds

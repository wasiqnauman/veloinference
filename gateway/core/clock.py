"""Clock abstractions used by scheduling code and deterministic tests."""

from time import monotonic
from typing import Protocol


class Clock(Protocol):
    """Provide monotonic time in seconds."""

    def monotonic(self) -> float:
        """Return the current monotonic time."""


class SystemClock:
    """Production clock backed by time.monotonic."""

    def monotonic(self) -> float:
        """Return the current monotonic time."""
        return monotonic()

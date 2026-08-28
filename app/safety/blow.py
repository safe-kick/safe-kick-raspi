from __future__ import annotations

from dataclasses import dataclass

from .config import BlowConfig


@dataclass(frozen=True)
class BlowReading:
    status: str
    duration: float
    progress: float
    detected: bool


class BlowDetector:
    """Track one active-low breath while tolerating short HIGH gaps."""

    def __init__(self, config: BlowConfig) -> None:
        self._config = config
        self.reset()

    def reset(self) -> BlowReading:
        self._started_at: float | None = None
        self._high_since: float | None = None
        self._detected = False
        self._retry = False
        return self.reading(0.0)

    def observe(self, active_low_detected: bool, now: float) -> BlowReading:
        if self._detected:
            return self.reading(now)

        if active_low_detected:
            if self._started_at is None:
                self._started_at = now
            self._high_since = None
            self._retry = False
        elif self._started_at is not None:
            if self._high_since is None:
                self._high_since = now
            elif now - self._high_since > self._config.max_gap_seconds:
                self._started_at = None
                self._high_since = None
                self._retry = True

        duration = 0.0 if self._started_at is None else now - self._started_at
        if duration >= self._config.minimum_seconds:
            self._detected = True
        return self.reading(now)

    def reading(self, now: float) -> BlowReading:
        duration = 0.0 if self._started_at is None else now - self._started_at
        duration = min(duration, self._config.minimum_seconds)
        if self._detected:
            status = "success"
            duration = self._config.minimum_seconds
        elif self._started_at is not None:
            status = "blowing"
        elif self._retry:
            status = "retry"
        else:
            status = "ready"
        return BlowReading(
            status=status,
            duration=duration,
            progress=min(1.0, max(0.0, duration / self._config.minimum_seconds)),
            detected=self._detected,
        )

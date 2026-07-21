from enum import Enum, auto

from .config import WeightConfig


class OccupancyAction(Enum):
    NONE = auto()
    WARN = auto()
    LOCK = auto()
    CLEAR_WARNING = auto()


class OccupancyMonitor:
    def __init__(self, config: WeightConfig) -> None:
        self._config = config
        self.reset()

    def reset(self) -> None:
        self._overweight_since: float | None = None
        self._warning_sent = False
        self._lock_sent = False

    def observe(self, total_kg: float, now: float) -> OccupancyAction:
        weight = 0.0 if abs(total_kg) < self._config.deadband_kg else total_kg
        if weight < self._config.two_person_threshold_kg:
            had_warning = self._warning_sent
            self.reset()
            return OccupancyAction.CLEAR_WARNING if had_warning else OccupancyAction.NONE
        if self._overweight_since is None:
            self._overweight_since = now
            return OccupancyAction.NONE
        elapsed = now - self._overweight_since
        lock_after = self._config.warning_after_seconds + self._config.lock_after_warning_seconds
        if elapsed >= lock_after and not self._lock_sent:
            self._lock_sent = True
            return OccupancyAction.LOCK
        if elapsed >= self._config.warning_after_seconds and not self._warning_sent:
            self._warning_sent = True
            return OccupancyAction.WARN
        return OccupancyAction.NONE

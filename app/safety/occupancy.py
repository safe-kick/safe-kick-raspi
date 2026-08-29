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
        self._baseline_kg: float | None = None
        self._ride_started_at: float | None = None
        self._ride_baseline_captured = False
        self._candidate_samples = 0
        self._clear_samples = 0
        self._warning_since: float | None = None
        self._warning_sent = False
        self._lock_sent = False

    @property
    def baseline_kg(self) -> float | None:
        return self._baseline_kg

    def start(self, initial_baseline_kg: float, now: float) -> None:
        self.reset()
        self._baseline_kg = initial_baseline_kg
        self._ride_started_at = now

    def _reset_detection(self) -> None:
        self._candidate_samples = 0
        self._clear_samples = 0
        self._warning_since = None
        self._warning_sent = False
        self._lock_sent = False

    def observe(self, total_kg: float, now: float) -> OccupancyAction:
        weight = 0.0 if abs(total_kg) < self._config.deadband_kg else total_kg

        if self._baseline_kg is None or self._ride_started_at is None:
            return OccupancyAction.NONE

        if (
            not self._ride_baseline_captured
            and now - self._ride_started_at >= self._config.baseline_delay_seconds
            and self._config.minimum_baseline_kg
            <= weight
            <= self._config.maximum_baseline_kg
        ):
            self._baseline_kg = weight
            self._ride_baseline_captured = True
            self._reset_detection()

        warning_threshold = self._baseline_kg + self._config.two_person_delta_kg
        clear_threshold = self._baseline_kg + self._config.clear_delta_kg

        if self._warning_sent:
            if weight <= clear_threshold:
                self._clear_samples += 1
                if self._clear_samples >= self._config.clear_sample_count:
                    self._reset_detection()
                    return OccupancyAction.CLEAR_WARNING
            else:
                self._clear_samples = 0

            if (
                self._warning_since is not None
                and now - self._warning_since >= self._config.lock_after_warning_seconds
                and not self._lock_sent
            ):
                self._lock_sent = True
                return OccupancyAction.LOCK
            return OccupancyAction.NONE

        if weight < warning_threshold:
            self._candidate_samples = 0
            return OccupancyAction.NONE

        self._candidate_samples += 1
        if self._candidate_samples < self._config.candidate_sample_count:
            return OccupancyAction.NONE

        if not self._warning_sent:
            self._warning_since = now
            self._warning_sent = True
            self._clear_samples = 0
            return OccupancyAction.WARN
        return OccupancyAction.NONE

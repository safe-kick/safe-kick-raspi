from collections import deque
from dataclasses import dataclass
from statistics import median

from .config import BoardingConfig
from .protocol import WeightReading


@dataclass(frozen=True)
class RiderBaseline:
    total_kg: float


class BoardingMonitor:
    def __init__(self, config: BoardingConfig) -> None:
        self._config = config
        self._samples: deque[WeightReading] = deque(maxlen=config.sample_count)

    def reset(self) -> None:
        self._samples.clear()

    def observe(self, reading: WeightReading) -> RiderBaseline | None:
        self._samples.append(reading)
        if len(self._samples) < self._config.sample_count:
            return None
        totals = [sample.total for sample in self._samples]
        if max(totals) - min(totals) > self._config.stability_range_kg:
            return None
        total_kg = float(median(totals))
        if not self._config.minimum_rider_kg <= total_kg <= self._config.maximum_rider_kg:
            return None
        return RiderBaseline(total_kg)

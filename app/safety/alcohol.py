from dataclasses import dataclass

from .config import AlcoholConfig


@dataclass(frozen=True)
class AlcoholResult:
    unsafe: bool
    baseline: int
    samples: tuple[int, ...]
    positive_samples: int
    peak_delta: int
    reason: str


class AlcoholPolicy:
    def __init__(self, config: AlcoholConfig) -> None:
        self._config = config

    def evaluate(self, baseline: int | None, samples: list[int]) -> AlcoholResult:
        if baseline is None:
            return AlcoholResult(True, 0, tuple(samples), 0, 0, "missing baseline")
        deltas = [value - baseline for value in samples]
        if len(samples) < self._config.minimum_sample_count:
            return AlcoholResult(
                True, baseline, tuple(samples), 0, max(deltas, default=0),
                "not enough samples",
            )
        positive_count = sum(delta >= self._config.minimum_delta for delta in deltas)
        consecutive_count = 0
        max_consecutive_count = 0
        for delta in deltas:
            if delta >= self._config.minimum_delta:
                consecutive_count += 1
                max_consecutive_count = max(
                    max_consecutive_count,
                    consecutive_count,
                )
            else:
                consecutive_count = 0

        consecutive_delta_exceeded = (
            max_consecutive_count >= self._config.required_positive_samples
        )
        absolute_threshold_exceeded = any(
            value > self._config.absolute_threshold
            for value in samples
        )
        unsafe = consecutive_delta_exceeded or absolute_threshold_exceeded
        if absolute_threshold_exceeded:
            reason = "absolute threshold exceeded"
        elif consecutive_delta_exceeded:
            reason = "alcohol detected"
        else:
            reason = "within configured range"
        return AlcoholResult(
            unsafe, baseline, tuple(samples), positive_count, max(deltas, default=0),
            reason,
        )

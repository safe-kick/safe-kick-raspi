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
        unsafe = positive_count >= self._config.required_positive_samples
        return AlcoholResult(
            unsafe, baseline, tuple(samples), positive_count, max(deltas, default=0),
            "alcohol detected" if unsafe else "within configured range",
        )

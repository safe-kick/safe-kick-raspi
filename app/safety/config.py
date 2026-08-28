from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SerialConfig:
    port: str = "/dev/serial0"
    baudrate: int = 115200
    read_timeout_seconds: float = 0.2
    reconnect_delay_seconds: float = 2.0


@dataclass(frozen=True)
class AlcoholConfig:
    minimum_delta: int = 100
    required_positive_samples: int = 3
    minimum_sample_count: int = 8
    absolute_threshold: int = 400


@dataclass(frozen=True)
class BlowConfig:
    gpio: int = 17
    minimum_seconds: float = 1.0
    max_gap_seconds: float = 0.2
    poll_interval_seconds: float = 0.02
    baseline_timeout_seconds: float = 6.0


@dataclass(frozen=True)
class BoardingConfig:
    sample_count: int = 3
    minimum_rider_kg: float = 20.0
    maximum_rider_kg: float = 100.0
    stability_range_kg: float = 5.0


@dataclass(frozen=True)
class WeightConfig:
    deadband_kg: float = 2.0
    two_person_threshold_kg: float = 110.0
    warning_after_seconds: float = 4.0
    lock_after_warning_seconds: float = 10.0


@dataclass(frozen=True)
class AppConfig:
    serial: SerialConfig = SerialConfig()
    alcohol: AlcoholConfig = AlcoholConfig()
    blow: BlowConfig = BlowConfig()
    boarding: BoardingConfig = BoardingConfig()
    weight: WeightConfig = WeightConfig()


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"[{name}] must be a TOML table")
    return value


def load_config(path: str | Path) -> AppConfig:
    try:
        import tomllib
    except ModuleNotFoundError:
        data = _load_simple_toml(Path(path))
    else:
        with Path(path).open("rb") as file:
            data = tomllib.load(file)

    config = AppConfig(
        serial=SerialConfig(**_section(data, "serial")),
        alcohol=AlcoholConfig(**_section(data, "alcohol")),
        blow=BlowConfig(**_section(data, "blow")),
        boarding=BoardingConfig(**_section(data, "boarding")),
        weight=WeightConfig(**_section(data, "weight")),
    )
    _validate(config)
    return config


def _load_simple_toml(path: Path) -> dict[str, Any]:
    """Read this project's scalar-only TOML config on Python 3.10."""
    data: dict[str, Any] = {}
    section: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = data.setdefault(line[1:-1].strip(), {})
            continue
        if section is None or "=" not in line:
            raise ValueError(f"Invalid config line: {raw_line}")
        key, raw_value = (part.strip() for part in line.split("=", 1))
        section[key] = _parse_scalar(raw_value)
    return data


def _parse_scalar(value: str) -> str | int | float | bool:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return float(value) if "." in value else int(value)
    except ValueError as error:
        raise ValueError(f"Unsupported config value: {value}") from error


def _validate(config: AppConfig) -> None:
    if config.serial.baudrate <= 0:
        raise ValueError("serial.baudrate must be positive")
    if config.alcohol.minimum_sample_count <= 0:
        raise ValueError("alcohol.minimum_sample_count must be positive")
    if config.alcohol.absolute_threshold <= 0:
        raise ValueError("alcohol.absolute_threshold must be positive")
    if not 1 <= config.alcohol.required_positive_samples <= config.alcohol.minimum_sample_count:
        raise ValueError("alcohol.required_positive_samples is out of range")
    if config.blow.gpio < 0:
        raise ValueError("blow.gpio must not be negative")
    if config.blow.minimum_seconds <= 0:
        raise ValueError("blow.minimum_seconds must be positive")
    if config.blow.max_gap_seconds < 0:
        raise ValueError("blow.max_gap_seconds must not be negative")
    if config.blow.poll_interval_seconds <= 0:
        raise ValueError("blow.poll_interval_seconds must be positive")
    if config.blow.baseline_timeout_seconds <= 0:
        raise ValueError("blow.baseline_timeout_seconds must be positive")
    if config.boarding.sample_count < 3:
        raise ValueError("boarding.sample_count must be at least 3")
    if config.boarding.minimum_rider_kg >= config.boarding.maximum_rider_kg:
        raise ValueError("boarding rider weight range is invalid")
    if config.boarding.stability_range_kg <= 0:
        raise ValueError("boarding.stability_range_kg must be positive")
    if config.weight.two_person_threshold_kg <= config.weight.deadband_kg:
        raise ValueError("weight.two_person_threshold_kg must exceed deadband_kg")

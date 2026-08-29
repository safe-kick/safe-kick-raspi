from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class MessageType(Enum):
    EMPTY = auto()
    COMMAND_ECHO = auto()
    BOOTING = auto()
    READY = auto()
    MQ3_START = auto()
    MQ3_BASELINE_START = auto()
    MQ3_BASELINE = auto()
    MQ3_BASELINE_END = auto()
    MQ3_MEASURE_START = auto()
    MEASURE_BEGIN = auto()
    MQ3_SAMPLE = auto()
    MQ3_END = auto()
    MQ3_MEASURE_END = auto()
    WEIGHT_START = auto()
    WEIGHT_SAMPLE = auto()
    WEIGHT_END = auto()
    LOCK_OK = auto()
    UNLOCK_OK = auto()
    MOTOR_STATE = auto()
    FAULT = auto()
    ERROR = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class WeightReading:
    fl: float
    fr: float
    rl: float
    rr: float
    total: float


@dataclass(frozen=True)
class MotorState:
    unlocked: bool
    speed_percent: int


@dataclass(frozen=True)
class Message:
    type: MessageType
    raw: str
    value: int | str | WeightReading | MotorState | None = None


COMMANDS = {
    "CHECK_MQ3", "CHECK_MQ3_BASELINE", "CHECK_MQ3_MEASURE",
    "TEST_MQ3", "STOP_TEST_MQ3", "CHECK_WEIGHT",
    "STOP_WEIGHT", "BUZZ_ON", "BUZZ_OFF", "LOCK", "UNLOCK", "MOTOR_STATE",
}

_WEIGHT_PATTERN = re.compile(
    r"FL:(?P<fl>[+-]?\d+(?:\.\d+)?)\s+"
    r"FR:(?P<fr>[+-]?\d+(?:\.\d+)?)\s+"
    r"RL:(?P<rl>[+-]?\d+(?:\.\d+)?)\s+"
    r"RR:(?P<rr>[+-]?\d+(?:\.\d+)?)\s+"
    r"TOTAL:(?P<total>[+-]?\d+(?:\.\d+)?)"
)
_MOTOR_STATE_PATTERN = re.compile(
    r"MOTOR:(?P<state>LOCKED|UNLOCKED)\s+SPEED:(?P<speed>\d+)"
)
MINIMUM_WEIGHT_KG = 1.0


def parse_line(line: str) -> Message:
    raw = line.strip()
    if not raw:
        return Message(MessageType.EMPTY, raw)
    if raw in COMMANDS:
        return Message(MessageType.COMMAND_ECHO, raw, raw)
    if raw == "Tare...":
        return Message(MessageType.BOOTING, raw)
    if raw == "READY":
        return Message(MessageType.READY, raw)
    markers = {
        "[CHECK_MQ3]": MessageType.MQ3_START,
        "[CHECK_MQ3_BASELINE]": MessageType.MQ3_BASELINE_START,
        "[END_MQ3_BASELINE]": MessageType.MQ3_BASELINE_END,
        "[CHECK_MQ3_MEASURE]": MessageType.MQ3_MEASURE_START,
        "MEASURE_BEGIN": MessageType.MEASURE_BEGIN,
        "MEASURE_END": MessageType.MQ3_MEASURE_END,
        "[END_MQ3_MEASURE]": MessageType.MQ3_MEASURE_END,
        "[END_MQ3]": MessageType.MQ3_END,
        "[CHECK_WEIGHT]": MessageType.WEIGHT_START,
        "[END_WEIGHT]": MessageType.WEIGHT_END,
        "LOCK_OK": MessageType.LOCK_OK,
        "UNLOCK_OK": MessageType.UNLOCK_OK,
    }
    if raw in markers:
        return Message(markers[raw], raw)
    if raw.startswith("MQ3_BASELINE:"):
        return _parse_integer(MessageType.MQ3_BASELINE, raw, "MQ3_BASELINE:")
    if raw.startswith("MQ3:"):
        return _parse_integer(MessageType.MQ3_SAMPLE, raw, "MQ3:")
    if raw.startswith("FAULT:"):
        return Message(MessageType.FAULT, raw, raw.removeprefix("FAULT:"))
    if raw.startswith("ERR:"):
        return Message(MessageType.ERROR, raw, raw.removeprefix("ERR:"))

    motor_match = _MOTOR_STATE_PATTERN.fullmatch(raw)
    if motor_match:
        return Message(
            MessageType.MOTOR_STATE,
            raw,
            MotorState(
                unlocked=motor_match.group("state") == "UNLOCKED",
                speed_percent=int(motor_match.group("speed")),
            ),
        )

    match = _WEIGHT_PATTERN.fullmatch(raw)
    if match:
        values = {name: float(value) for name, value in match.groupdict().items()}
        if values["total"] < MINIMUM_WEIGHT_KG:
            values["total"] = 0.0
        return Message(MessageType.WEIGHT_SAMPLE, raw, WeightReading(**values))
    return Message(MessageType.UNKNOWN, raw)


def _parse_integer(message_type: MessageType, raw: str, prefix: str) -> Message:
    try:
        value = int(raw.removeprefix(prefix))
    except ValueError:
        return Message(MessageType.ERROR, raw, f"INVALID_{message_type.name}")
    return Message(message_type, raw, value)

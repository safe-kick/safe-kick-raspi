#!/usr/bin/env python3
"""Run a fail-safe UART smoke test against the SAFE-KICK STM32 firmware."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.safety.protocol import MessageType, parse_line  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="e.g. /dev/serial0 or COM5")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--weight-samples", type=int, default=3)
    parser.add_argument(
        "--test-actuators",
        action="store_true",
        help="Also pulse the buzzer and unlock relay; use only on a secured kickboard.",
    )
    return parser.parse_args()


def send(serial_port, command: str) -> None:
    print(f"RPi -> STM32: {command}")
    serial_port.write(f"{command}\r\n".encode("ascii"))
    serial_port.flush()


def read_message(serial_port, deadline: float):
    while time.monotonic() < deadline:
        data = serial_port.readline()
        if not data:
            continue
        line = data.decode("ascii", errors="replace").strip()
        if line:
            print(f"STM32 -> RPi: {line}")
            return parse_line(line)
    raise TimeoutError("STM32 response timed out")


def wait_for(serial_port, expected: MessageType, timeout: float):
    deadline = time.monotonic() + timeout
    while True:
        message = read_message(serial_port, deadline)
        if message.type is expected:
            return message
        if message.type in {MessageType.FAULT, MessageType.ERROR}:
            raise RuntimeError(f"STM32 reported {message.raw}")


def verify_mq3(serial_port, timeout: float) -> tuple[int, list[int]]:
    send(serial_port, "CHECK_MQ3")
    deadline = time.monotonic() + timeout
    baseline = None
    samples: list[int] = []
    while True:
        message = read_message(serial_port, deadline)
        if message.type is MessageType.MQ3_BASELINE:
            baseline = int(message.value)
        elif message.type is MessageType.MQ3_SAMPLE:
            samples.append(int(message.value))
        elif message.type is MessageType.MQ3_END:
            break
        elif message.type in {MessageType.FAULT, MessageType.ERROR}:
            raise RuntimeError(f"STM32 reported {message.raw}")
    if baseline is None:
        raise RuntimeError("MQ3_BASELINE was not received")
    if len(samples) != 8:
        raise RuntimeError(f"Expected 8 MQ3 samples, received {len(samples)}")
    return baseline, samples


def verify_weight(serial_port, count: int, timeout: float) -> list[float]:
    send(serial_port, "CHECK_WEIGHT")
    deadline = time.monotonic() + timeout
    totals: list[float] = []
    while len(totals) < count:
        message = read_message(serial_port, deadline)
        if message.type is MessageType.WEIGHT_SAMPLE:
            totals.append(message.value.total)
        elif message.type in {MessageType.FAULT, MessageType.ERROR}:
            raise RuntimeError(f"STM32 reported {message.raw}")
    return totals


def main() -> int:
    args = parse_args()
    import serial

    serial_port = serial.Serial(
        port=args.port,
        baudrate=args.baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.2,
    )
    try:
        time.sleep(0.2)
        serial_port.reset_input_buffer()
        send(serial_port, "LOCK")
        wait_for(serial_port, MessageType.LOCK_OK, args.timeout)

        baseline, mq3_samples = verify_mq3(serial_port, args.timeout)
        weight_totals = verify_weight(serial_port, args.weight_samples, args.timeout)

        if args.test_actuators:
            send(serial_port, "BUZZ_ON")
            time.sleep(2.0)
            send(serial_port, "BUZZ_OFF")
            send(serial_port, "UNLOCK")
            wait_for(serial_port, MessageType.UNLOCK_OK, args.timeout)

        print(
            "PASS: UART protocol verified "
            f"(MQ3 baseline={baseline}, samples={mq3_samples}, "
            f"weight totals={weight_totals})"
        )
        return 0
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    finally:
        try:
            send(serial_port, "BUZZ_OFF")
            send(serial_port, "LOCK")
        finally:
            serial_port.close()


if __name__ == "__main__":
    raise SystemExit(main())

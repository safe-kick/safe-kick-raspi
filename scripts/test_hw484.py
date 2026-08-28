#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from gpiozero import DigitalInputDevice

from app.safety.blow import BlowDetector
from app.safety.config import load_config


def main() -> None:
    config = load_config(PROJECT_ROOT / "config.toml").blow
    config = replace(
        config,
        gpio=int(os.getenv("MIC_GPIO", str(config.gpio))),
        minimum_seconds=float(
            os.getenv("MIN_BLOW_SECONDS", str(config.minimum_seconds))
        ),
        max_gap_seconds=float(
            os.getenv("MAX_GAP_SECONDS", str(config.max_gap_seconds))
        ),
    )
    detector = BlowDetector(config)
    sensor = DigitalInputDevice(config.gpio, pull_up=True)
    previous_status = "ready"
    last_print_at = 0.0
    print(
        f"HW-484 GPIO{config.gpio} ACTIVE_LOW: "
        f"{config.minimum_seconds:.2f}s 유지, {config.max_gap_seconds:.2f}s gap 허용"
    )
    try:
        while True:
            now = time.monotonic()
            reading = detector.observe(sensor.is_active, now)
            if (
                reading.status != previous_status
                or (reading.status == "blowing" and now - last_print_at >= 0.1)
            ):
                level = 0 if sensor.is_active else 1
                print(
                    f"GPIO={level} status={reading.status} "
                    f"duration={reading.duration:.2f}s progress={reading.progress:.0%}"
                )
                previous_status = reading.status
                last_print_at = now
            if reading.detected:
                print("SUCCESS")
                return
            time.sleep(config.poll_interval_seconds)
    except KeyboardInterrupt:
        print("중단")
    finally:
        sensor.close()


if __name__ == "__main__":
    main()

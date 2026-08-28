from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from app.safety.blow import BlowDetector, BlowReading
from app.safety.config import BlowConfig


class BlowService:
    def __init__(
        self,
        config: BlowConfig,
        use_mock: bool = False,
        reader: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.use_mock = use_mock
        self._reader = reader
        self._clock = clock
        self._detector = BlowDetector(config)
        self._last_reading = self._detector.reset()
        self._callback: Callable[[BlowReading], None] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._device = None
        self._logger = logging.getLogger(__name__)

    @property
    def detected(self) -> bool:
        return self._last_reading.detected

    def start(self, callback: Callable[[BlowReading], None]) -> None:
        self.stop()
        self._callback = callback
        self._last_reading = self._detector.reset()
        self._stop.clear()
        callback(self._last_reading)
        self._logger.info(
            "[BLOW] GPIO=%d ACTIVE_LOW minimum=%.2fs max_gap=%.2fs",
            self.config.gpio,
            self.config.minimum_seconds,
            self.config.max_gap_seconds,
        )
        self._thread = threading.Thread(
            target=self._run,
            name="hw484-blow",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> bool:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        self._thread = None
        return self._last_reading.detected

    def close(self) -> None:
        self.stop()
        if self._device is not None:
            self._device.close()
            self._device = None

    def _read_active_low(self) -> bool:
        if self._reader is not None:
            return bool(self._reader())
        if self.use_mock:
            return True
        if self._device is None:
            from gpiozero import DigitalInputDevice

            self._device = DigitalInputDevice(self.config.gpio, pull_up=True)
        return bool(self._device.is_active)

    def _run(self) -> None:
        previous_status = self._last_reading.status
        last_log_at = 0.0
        try:
            while not self._stop.is_set():
                now = self._clock()
                reading = self._detector.observe(self._read_active_low(), now)
                self._last_reading = reading
                if self._callback is not None:
                    self._callback(reading)

                if reading.status != previous_status:
                    if reading.status == "blowing":
                        self._logger.info("[BLOW] start")
                    elif reading.status == "retry":
                        self._logger.info("[BLOW] gap exceeded; retry")
                    elif reading.status == "success":
                        self._logger.info(
                            "[BLOW] duration=%.2f success", reading.duration
                        )
                    previous_status = reading.status
                elif reading.status == "blowing" and now - last_log_at >= 0.25:
                    self._logger.info("[BLOW] duration=%.2f", reading.duration)
                    last_log_at = now

                if reading.detected:
                    return
                self._stop.wait(self.config.poll_interval_seconds)
        except Exception:
            self._logger.exception("[BLOW] GPIO monitoring failed")

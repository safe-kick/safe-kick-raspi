from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from app.safety.config import SerialConfig


class UARTService:
    """Owns the serial port and continuously dispatches STM32 lines."""

    def __init__(self, config: SerialConfig | None = None) -> None:
        self.config = config or SerialConfig(
            port=os.getenv("SERIAL_PORT", "/dev/serial0"),
            baudrate=int(os.getenv("BAUD_RATE", "115200")),
        )
        self.use_mock = os.getenv("USE_UART_MOCK", "true").lower() == "true"
        self._serial: Any | None = None
        self._mock_connected = False
        self._line_handler: Callable[[str], None] | None = None
        self._connected_handler: Callable[[], None] | None = None
        self._write_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._logger = logging.getLogger(__name__)
        self._mock_motor_unlocked = False
        self._mock_motor_speed = 0

    @property
    def is_connected(self) -> bool:
        if self.use_mock:
            return self._mock_connected
        return bool(self._serial and self._serial.is_open)

    def start(
        self,
        line_handler: Callable[[str], None],
        connected_handler: Callable[[], None],
    ) -> None:
        self._line_handler = line_handler
        self._connected_handler = connected_handler
        self._stop.clear()
        if self.use_mock:
            self._mock_connected = True
            connected_handler()
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="stm32-uart", daemon=True)
        self._thread.start()

    def send_command(self, command: str) -> None:
        command = command.strip()
        if self.use_mock:
            self._emit_mock(command)
            return
        if not self.is_connected:
            raise ConnectionError("STM32 serial port is not connected")
        payload = f"{command}\r\n".encode("ascii")
        with self._write_lock:
            self._serial.write(payload)
            self._serial.flush()
        self._logger.info("RPi -> STM32: %s", command)

    def close(self) -> None:
        self._stop.set()
        self._mock_connected = False
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._close_serial()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._open_serial()
                if self._connected_handler:
                    self._connected_handler()
                while not self._stop.is_set() and self.is_connected:
                    data = self._serial.readline()
                    if data and self._line_handler:
                        line = data.decode("ascii", errors="replace").strip()
                        self._logger.debug("STM32 -> RPi: %s", line)
                        self._line_handler(line)
            except Exception:
                if not self._stop.is_set():
                    self._logger.exception("STM32 UART connection failed")
            finally:
                self._close_serial()
            self._stop.wait(self.config.reconnect_delay_seconds)

    def _open_serial(self) -> None:
        import serial

        self._serial = serial.Serial(
            port=self.config.port,
            baudrate=self.config.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.config.read_timeout_seconds,
        )
        time.sleep(0.2)
        self._serial.reset_input_buffer()

    def _close_serial(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    def _emit_mock(self, command: str) -> None:
        if not self._line_handler:
            return
        if command == "UNLOCK":
            self._mock_motor_unlocked = True
            self._mock_motor_speed = 70
        elif command == "BUZZ_ON" and self._mock_motor_unlocked:
            self._mock_motor_speed = 30
        elif command == "BUZZ_OFF" and self._mock_motor_unlocked:
            self._mock_motor_speed = 70
        elif command == "LOCK":
            self._mock_motor_unlocked = False
            self._mock_motor_speed = 0

        responses = {
            "LOCK": ["LOCK_OK"],
            "UNLOCK": ["UNLOCK_OK"],
            "MOTOR_STATE": [
                "MOTOR:%s SPEED:%d"
                % (
                    "UNLOCKED" if self._mock_motor_unlocked else "LOCKED",
                    self._mock_motor_speed,
                )
            ],
            "CHECK_MQ3": [
                "[CHECK_MQ3]", "MQ3_BASELINE:90",
                "MQ3:110", "MQ3:108", "MQ3:92", "MQ3:92",
                "MQ3:88", "MQ3:88", "MQ3:93", "MQ3:92", "[END_MQ3]",
            ],
            "CHECK_WEIGHT": [
                "[CHECK_WEIGHT]",
                "FL:24.00 FR:20.00 RL:11.00 RR:10.00 TOTAL:65.00",
                "FL:23.00 FR:21.00 RL:10.50 RR:10.50 TOTAL:65.00",
                "FL:22.00 FR:22.00 RL:10.00 RR:11.00 TOTAL:65.00",
            ],
        }.get(command, [])
        for line in responses:
            self._line_handler(line)


uart_service = UARTService()

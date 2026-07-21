from __future__ import annotations

import logging
import os
import threading
from dataclasses import replace
from pathlib import Path

from app.managers.session_manager import SessionManager
from app.safety.config import load_config
from app.safety.controller import Controller, SystemState
from app.safety.protocol import MessageType, WeightReading, parse_line
from app.services import log_service
from app.services.uart_service import uart_service


class SafetyService:
    def __init__(self) -> None:
        default_config = Path(__file__).resolve().parents[2] / "config.toml"
        config_path = Path(os.getenv("SAFE_KICK_CONFIG", str(default_config)))
        self.config = load_config(config_path)
        self.config = replace(
            self.config,
            serial=replace(
                self.config.serial,
                port=os.getenv("SERIAL_PORT", self.config.serial.port),
                baudrate=int(os.getenv("BAUD_RATE", str(self.config.serial.baudrate))),
            ),
        )
        uart_service.config = self.config.serial
        self.controller = Controller(self.config, uart_service.send_command)
        self._lock = threading.RLock()
        self._pending_lock_reason: str | None = None
        self._last_uart_line: str | None = None
        self._logger = logging.getLogger(__name__)

    def start(self) -> None:
        uart_service.start(self._on_line, self._on_connected)

    def stop(self) -> None:
        try:
            if uart_service.is_connected:
                self.request_lock("shutdown")
        except Exception:
            self._logger.exception("Failed to lock during shutdown")
        finally:
            uart_service.close()

    def prepare_session(self) -> None:
        self.request_lock("session_start")

    def authentication_completed(self, user_id: int) -> bool:
        if not SessionManager.is_active() or SessionManager.get_user_id() != user_id:
            return False
        with self._lock:
            accepted = self.controller.on_authentication_completed()
            self._sync_state()
            return accepted

    def request_lock(self, reason: str) -> bool:
        with self._lock:
            self._pending_lock_reason = reason
            try:
                self.controller.request_lock()
            except ConnectionError:
                self._logger.warning("Cannot send LOCK: STM32 is disconnected")
                self.controller.state = SystemState.FAULT
                SessionManager.set_stm32_connected(False)
                SessionManager.confirm_locked("fault")
                self._sync_state()
                return False
            return True

    def request_manual_unlock(self) -> str:
        if os.getenv("ALLOW_MANUAL_UNLOCK", "false").lower() != "true":
            return "manual_unlock_disabled"
        with self._lock:
            try:
                self.controller.request_manual_unlock()
            except ConnectionError:
                self.controller.state = SystemState.FAULT
                SessionManager.set_stm32_connected(False)
                SessionManager.confirm_locked("fault")
                self._sync_state()
                return "stm32_disconnected"
            self._sync_state()
        return "accepted"

    def start_weight_check(self, user_id: int) -> bool:
        if not SessionManager.is_active() or SessionManager.get_user_id() != user_id:
            return False
        with self._lock:
            try:
                accepted = self.controller.start_rider_check()
            except ConnectionError:
                self.controller.state = SystemState.FAULT
                SessionManager.set_stm32_connected(False)
                SessionManager.confirm_locked("fault")
                self._sync_state()
                return False
            self._sync_state()
            return accepted

    def status(self) -> dict:
        data = SessionManager.get_device_data()
        data["uart_mock"] = uart_service.use_mock
        data["last_uart_line"] = self._last_uart_line
        result = self.controller.last_alcohol_result
        data["alcohol_result"] = (
            {
                "unsafe": result.unsafe,
                "baseline": result.baseline,
                "samples": list(result.samples),
                "positive_samples": result.positive_samples,
                "peak_delta": result.peak_delta,
                "reason": result.reason,
            }
            if result is not None
            else None
        )
        data["rider_baseline_kg"] = (
            self.controller.rider_baseline.total_kg
            if self.controller.rider_baseline is not None
            else None
        )
        return data

    def _on_connected(self) -> None:
        with self._lock:
            SessionManager.set_stm32_connected(True)
            self.controller.on_connected()
            self._sync_state()

    def _on_line(self, line: str) -> None:
        self._last_uart_line = line
        message = parse_line(line)
        with self._lock:
            previous = self.controller.state
            if message.type is MessageType.WEIGHT_SAMPLE and isinstance(message.value, WeightReading):
                SessionManager.update_weight(message.value.total)
            elif message.type is MessageType.MQ3_SAMPLE:
                SessionManager.update_gas(float(message.value))

            self.controller.handle(message)
            self._sync_transition(previous, self.controller.state)
            self._sync_state()

    def _sync_transition(self, previous: SystemState, current: SystemState) -> None:
        if current is previous:
            return
        session_id = SessionManager.get_session_id()
        if current is SystemState.MONITORING:
            SessionManager.unlock()
        elif current is SystemState.WARNING:
            SessionManager.warn_two_person()
            if session_id is not None:
                log_service.save_warning_log(session_id, "two_person")
        elif previous is SystemState.WARNING and current is SystemState.MONITORING:
            SessionManager.clear_warning()
        elif current is SystemState.LOCKED:
            reason = self._pending_lock_reason
            self._pending_lock_reason = None
            if previous is SystemState.CHECKING_ALCOHOL:
                reason = "drunk"
            elif previous is SystemState.WARNING:
                reason = "two_person"
            if reason == "two_person" and SessionManager.is_active():
                SessionManager.confirm_locked("warning")
            elif reason == "drunk" and SessionManager.is_active():
                SessionManager.lock(reason)
                if session_id is not None:
                    log_service.save_warning_log(session_id, reason)
            else:
                SessionManager.confirm_locked("locked")
        elif current is SystemState.FAULT:
            SessionManager.confirm_locked("fault")

    def _sync_state(self) -> None:
        SessionManager.set_safety_state(self.controller.state.name.lower())


safety_service = SafetyService()

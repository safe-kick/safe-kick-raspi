from __future__ import annotations

import logging
import os
import threading
from dataclasses import replace
from pathlib import Path

from app.managers.session_manager import SessionManager
from app.safety.config import load_config
from app.safety.blow import BlowReading
from app.safety.controller import Controller, SystemState
from app.safety.protocol import MessageType, MotorState, WeightReading, parse_line
from app.services import log_service
from app.services.blow_service import BlowService
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
            blow=replace(
                self.config.blow,
                gpio=int(os.getenv("MIC_GPIO", str(self.config.blow.gpio))),
                minimum_seconds=float(
                    os.getenv("MIN_BLOW_SECONDS", str(self.config.blow.minimum_seconds))
                ),
                max_gap_seconds=float(
                    os.getenv("MAX_GAP_SECONDS", str(self.config.blow.max_gap_seconds))
                ),
            ),
        )
        uart_service.config = self.config.serial
        self.controller = Controller(self.config, uart_service.send_command)
        use_gpio_mock = os.getenv(
            "USE_GPIO_MOCK", os.getenv("USE_UART_MOCK", "true")
        ).lower() == "true"
        self._blow_service = BlowService(self.config.blow, use_mock=use_gpio_mock)
        self._lock = threading.RLock()
        self._baseline_timer: threading.Timer | None = None
        self._baseline_request_active = False
        self._pending_lock_reason: str | None = None
        self._last_uart_line: str | None = None
        self._motor_state: MotorState | None = None
        self._motor_state_event = threading.Event()
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
            self._cancel_baseline_timer()
            self._blow_service.close()
            uart_service.close()

    def prepare_session(self) -> None:
        self._cancel_baseline_timer()
        self._baseline_request_active = False
        self._blow_service.stop()
        self.controller.reset_session()
        SessionManager.reset_alcohol_state(self.config.blow.minimum_seconds)
        self.request_lock("session_start")

    def request_baseline(self, user_id: int) -> str:
        if not SessionManager.is_active() or SessionManager.get_user_id() != user_id:
            return "invalid_session"
        with self._lock:
            if self.controller.baseline is not None:
                SessionManager.set_baseline_status("ready", self.controller.baseline)
                return "ready"
            already_running = self.controller.baseline_in_progress
            self._baseline_request_active = True
            SessionManager.set_baseline_status("measuring")
            if not already_running:
                self._start_baseline_timer()
                self._logger.info("[BASELINE] request sent")
            try:
                accepted = self.controller.request_baseline_capture()
            except ConnectionError:
                self._cancel_baseline_timer()
                self._baseline_request_active = False
                SessionManager.set_stm32_connected(False)
                SessionManager.set_baseline_status("failed")
                return "stm32_disconnected"
            if not accepted:
                self._cancel_baseline_timer()
                self._baseline_request_active = False
                SessionManager.set_baseline_status("failed")
                return "invalid_state"
            if self.controller.baseline is not None and not self.controller.baseline_in_progress:
                self._cancel_baseline_timer()
                SessionManager.set_baseline_status("ready", self.controller.baseline)
                return "ready"
            return "in_progress"

    def authentication_completed(self, user_id: int) -> bool:
        if (
            not SessionManager.is_active()
            or SessionManager.get_user_id() != user_id
            or not SessionManager.is_identity_verified()
        ):
            return False
        if self.controller.baseline is None:
            SessionManager.set_baseline_status("failed")
            return False
        with self._lock:
            accepted = self.controller.on_authentication_completed()
            if accepted:
                SessionManager.clear_warning()
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

    def send_motor_test_command(self, command: str) -> str:
        allowed_commands = {"UNLOCK", "BUZZ_ON", "BUZZ_OFF", "LOCK", "MOTOR_STATE"}
        if command not in allowed_commands:
            return "invalid_command"
        if not uart_service.is_connected:
            return "stm32_disconnected"

        if command == "MOTOR_STATE":
            self._motor_state_event.clear()
        try:
            uart_service.send_command(command)
        except ConnectionError:
            return "stm32_disconnected"

        if command == "MOTOR_STATE":
            if not self._motor_state_event.wait(timeout=0.7):
                return "response_timeout"
        return "accepted"

    def status(self) -> dict:
        data = SessionManager.get_device_data()
        data["uart_mock"] = uart_service.use_mock
        data["last_uart_line"] = self._last_uart_line
        data["motor_state"] = (
            {
                "unlocked": self._motor_state.unlocked,
                "speed_percent": self._motor_state.speed_percent,
            }
            if self._motor_state is not None
            else None
        )
        result = self.controller.last_alcohol_result
        data["alcohol_result"] = (
            {
                "unsafe": result.unsafe,
                "is_blown": result.is_blown,
                "is_drunk": result.is_drunk,
                "hw484_blow_detected": SessionManager.get_sensor_data()[
                    "hw484_blow_detected"
                ],
                "valid_blow": self.controller.last_valid_blow,
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
            if (
                message.type in {
                    MessageType.MQ3_BASELINE_START,
                    MessageType.MQ3_BASELINE,
                    MessageType.MQ3_BASELINE_END,
                }
                and not self._baseline_request_active
            ):
                self._logger.warning("[BASELINE] ignored late response: %s", line)
                return
            if (
                message.type is MessageType.ERROR
                and self.controller.baseline_in_progress
            ):
                self._baseline_failed("parse_or_uart_error")
                return
            previous = self.controller.state
            sensor_updated = False
            if message.type is MessageType.MQ3_BASELINE_START:
                SessionManager.set_baseline_status("measuring")
            elif message.type is MessageType.MQ3_BASELINE:
                self._logger.info("[BASELINE] value=%s", message.value)
            elif message.type is MessageType.MQ3_MEASURE_START:
                SessionManager.update_blow(
                    "buzzer", 0.0, self.config.blow.minimum_seconds, 0.0, False
                )
                self._logger.info("[ALCOHOL] waiting for STM32 buzzer")
            elif message.type is MessageType.MEASURE_BEGIN:
                self._logger.info("[ALCOHOL] MEASURE_BEGIN")
                self._blow_service.start(self._on_blow_reading)
            elif message.type in {MessageType.MQ3_MEASURE_END, MessageType.MQ3_END}:
                self.controller.set_hw484_result(self._blow_service.stop())

            if message.type is MessageType.WEIGHT_SAMPLE and isinstance(message.value, WeightReading):
                SessionManager.update_weight(message.value.total)
                sensor_updated = True
            elif message.type is MessageType.MQ3_SAMPLE:
                SessionManager.update_gas(float(message.value))
                sensor_updated = True
            elif message.type is MessageType.MOTOR_STATE and isinstance(message.value, MotorState):
                self._motor_state = message.value
                self._motor_state_event.set()

            self.controller.handle(message)
            if message.type is MessageType.MQ3_BASELINE_END:
                if self.controller.baseline is None:
                    self._baseline_failed("missing_value")
                else:
                    self._cancel_baseline_timer()
                    self._baseline_request_active = False
                    SessionManager.set_baseline_status("ready", self.controller.baseline)
                    self._logger.info(
                        "[BASELINE] stored session baseline=%d", self.controller.baseline
                    )
            self._sync_transition(previous, self.controller.state)
            self._sync_state()
            if sensor_updated:
                self._save_sensor_snapshot()

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
        elif current is SystemState.ALCOHOL_RETRY:
            SessionManager.update_blow(
                "retry", 0.0, self.config.blow.minimum_seconds, 0.0, False
            )

    def _sync_state(self) -> None:
        SessionManager.set_safety_state(self.controller.state.name.lower())

    def _save_sensor_snapshot(self) -> None:
        session_id = SessionManager.get_session_id()
        if session_id is None or not SessionManager.is_active():
            return
        sensor = SessionManager.get_sensor_data()
        log_service.save_sensor_log(
            session_id=session_id,
            face_score=sensor["face_score"],
            weight=sensor["weight"],
            gas=sensor["gas"],
        )

    def _on_blow_reading(self, reading: BlowReading) -> None:
        SessionManager.update_blow(
            reading.status,
            reading.duration,
            self.config.blow.minimum_seconds,
            reading.progress,
            reading.detected,
        )

    def _start_baseline_timer(self) -> None:
        self._cancel_baseline_timer()
        self._baseline_timer = threading.Timer(
            self.config.blow.baseline_timeout_seconds,
            self._on_baseline_timeout,
        )
        self._baseline_timer.daemon = True
        self._baseline_timer.start()

    def _cancel_baseline_timer(self) -> None:
        if self._baseline_timer is not None:
            self._baseline_timer.cancel()
            self._baseline_timer = None

    def _on_baseline_timeout(self) -> None:
        with self._lock:
            if self.controller.baseline_in_progress:
                self._baseline_failed("timeout")

    def _baseline_failed(self, reason: str) -> None:
        self._cancel_baseline_timer()
        self._baseline_request_active = False
        self.controller.baseline_failed()
        SessionManager.set_baseline_status("failed")
        self._logger.error("[BASELINE] failed reason=%s", reason)


safety_service = SafetyService()

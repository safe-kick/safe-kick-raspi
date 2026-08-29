import logging
import time
from enum import Enum, auto
from typing import Callable

from .alcohol import AlcoholPolicy, AlcoholResult
from .boarding import BoardingMonitor, RiderBaseline
from .config import AppConfig
from .occupancy import OccupancyAction, OccupancyMonitor
from .protocol import Message, MessageType, WeightReading


class SystemState(Enum):
    STARTING = auto()
    LOCKED = auto()
    CHECKING_ALCOHOL = auto()
    ALCOHOL_RETRY = auto()
    WAITING_RIDER = auto()
    CHECKING_RIDER = auto()
    UNLOCKING = auto()
    MONITORING = auto()
    WARNING = auto()
    FAULT = auto()


class Controller:
    def __init__(self, config: AppConfig, send_command: Callable[[str], None], clock=time.monotonic) -> None:
        self.config = config
        self.state = SystemState.STARTING
        self.last_alcohol_result: AlcoholResult | None = None
        self.rider_baseline: RiderBaseline | None = None
        self._send = send_command
        self._clock = clock
        self._alcohol = AlcoholPolicy(config.alcohol)
        self._boarding = BoardingMonitor(config.boarding)
        self._occupancy = OccupancyMonitor(config.weight)
        self._baseline: int | None = None
        self._mq3_samples: list[int] = []
        self._baseline_pending = False
        self._baseline_in_progress = False
        self._hw484_blow_detected = False
        self.last_valid_blow = False
        self._waiting_for_initial_lock = False
        self._authentication_pending = False
        self._logger = logging.getLogger(__name__)

    def on_connected(self) -> None:
        self.state = SystemState.STARTING
        self._waiting_for_initial_lock = True
        self._baseline = None
        self._baseline_pending = False
        self._baseline_in_progress = False
        self._mq3_samples.clear()
        self._hw484_blow_detected = False
        self.last_valid_blow = False
        self._boarding.reset()
        self._occupancy.reset()
        self.rider_baseline = None
        self._send("LOCK")

    def reset_session(self) -> None:
        self._baseline = None
        self._baseline_pending = False
        self._baseline_in_progress = False
        self._mq3_samples.clear()
        self._authentication_pending = False
        self._hw484_blow_detected = False
        self.last_valid_blow = False
        self.last_alcohol_result = None

    def on_authentication_completed(self) -> bool:
        if self._baseline is None:
            self._logger.warning("Ignoring alcohol check without MQ3 baseline")
            return False
        if self.state is SystemState.STARTING:
            self._authentication_pending = True
            return True
        if self.state in {SystemState.CHECKING_ALCOHOL, SystemState.WAITING_RIDER}:
            return True
        if self.state not in {SystemState.LOCKED, SystemState.ALCOHOL_RETRY}:
            self._logger.warning("Ignoring authentication in state %s", self.state.name)
            return False
        self._start_alcohol_check()
        return True

    @property
    def baseline(self) -> int | None:
        return self._baseline

    @property
    def baseline_in_progress(self) -> bool:
        return self._baseline_in_progress or self._baseline_pending

    def request_baseline_capture(self) -> bool:
        if self._baseline is not None or self.baseline_in_progress:
            return True
        if self.state is SystemState.STARTING:
            self._baseline_pending = True
            return True
        if self.state is not SystemState.LOCKED:
            self._logger.warning("Ignoring baseline in state %s", self.state.name)
            return False
        self._start_baseline_capture()
        return True

    def baseline_failed(self) -> None:
        self._baseline = None
        self._baseline_pending = False
        self._baseline_in_progress = False

    def set_hw484_result(self, detected: bool) -> None:
        self._hw484_blow_detected = detected

    def handle(self, message: Message) -> None:
        message_type = message.type
        if message_type in {MessageType.EMPTY, MessageType.COMMAND_ECHO, MessageType.READY}:
            return
        if message_type is MessageType.BOOTING:
            self.state = SystemState.STARTING
        elif message_type is MessageType.LOCK_OK:
            self.state = SystemState.LOCKED
            self._occupancy.reset()
            if self._waiting_for_initial_lock:
                self._waiting_for_initial_lock = False
                if self._baseline_pending:
                    self._start_baseline_capture()
                if self._authentication_pending:
                    self._authentication_pending = False
                    self._start_alcohol_check()
        elif message_type is MessageType.MQ3_START:
            # Legacy CHECK_MQ3 response support.
            self._baseline = None
            self._mq3_samples.clear()
            self.state = SystemState.CHECKING_ALCOHOL
        elif message_type is MessageType.MQ3_BASELINE_START:
            self._baseline_in_progress = True
        elif message_type is MessageType.MQ3_BASELINE:
            self._baseline = int(message.value)
        elif message_type is MessageType.MQ3_BASELINE_END:
            self._baseline_in_progress = False
        elif message_type is MessageType.MQ3_MEASURE_START:
            self._mq3_samples.clear()
            self._hw484_blow_detected = False
            self.last_valid_blow = False
            self.state = SystemState.CHECKING_ALCOHOL
        elif message_type is MessageType.MEASURE_BEGIN:
            self.state = SystemState.CHECKING_ALCOHOL
        elif message_type is MessageType.MQ3_SAMPLE:
            self._mq3_samples.append(int(message.value))
        elif message_type is MessageType.MQ3_END:
            self._finish_alcohol_check()
        elif message_type is MessageType.MQ3_MEASURE_END:
            if self.state is SystemState.CHECKING_ALCOHOL:
                self._finish_alcohol_check()
        elif message_type is MessageType.UNLOCK_OK:
            self.state = SystemState.MONITORING
            if self.rider_baseline is None:
                self.state = SystemState.FAULT
                self._send("LOCK")
            else:
                self._occupancy.start(self.rider_baseline.total_kg, self._clock())
        elif message_type is MessageType.WEIGHT_SAMPLE:
            if self.state is SystemState.CHECKING_RIDER:
                self._handle_boarding(message.value)
            elif self.state in {SystemState.MONITORING, SystemState.WARNING}:
                self._handle_weight(message.value, self._clock())
        elif message_type in {MessageType.FAULT, MessageType.ERROR}:
            self._logger.error("STM32 reported %s", message.raw)
            self.state = SystemState.FAULT
            self._send("LOCK")

    def request_lock(self) -> None:
        self._send("LOCK")

    def request_manual_unlock(self) -> None:
        self.state = SystemState.UNLOCKING
        self._send("UNLOCK")

    def start_rider_check(self) -> bool:
        if self.state is SystemState.CHECKING_RIDER:
            # The weight stream is already running. A retry only needs to
            # discard the previous unstable/overweight sample window.
            self._boarding.reset()
            self.rider_baseline = None
            return True
        if self.state is not SystemState.WAITING_RIDER:
            self._logger.warning("Ignoring weight check in state %s", self.state.name)
            return False
        self._boarding.reset()
        self.rider_baseline = None
        self.state = SystemState.CHECKING_RIDER
        self._send("CHECK_WEIGHT")
        return True

    def _start_alcohol_check(self) -> None:
        self._mq3_samples.clear()
        self._hw484_blow_detected = False
        self.last_valid_blow = False
        self.state = SystemState.CHECKING_ALCOHOL
        self._send("CHECK_MQ3_MEASURE")

    def _start_baseline_capture(self) -> None:
        self._baseline_pending = False
        self._baseline_in_progress = True
        self._send("CHECK_MQ3_BASELINE")

    def _finish_alcohol_check(self) -> None:
        result = self._alcohol.evaluate(self._baseline, self._mq3_samples)
        self.last_alcohol_result = result
        self.last_valid_blow = result.is_blown and self._hw484_blow_detected
        self._logger.info(
            "[ALCOHOL] baseline=%s peak_delta=%d is_blown=%s hw484=%s "
            "valid_blow=%s is_drunk=%s",
            self._baseline,
            result.peak_delta,
            result.is_blown,
            self._hw484_blow_detected,
            self.last_valid_blow,
            result.is_drunk,
        )
        if result.is_drunk:
            self.state = SystemState.LOCKED
            self._send("LOCK")
        elif not self.last_valid_blow:
            self.state = SystemState.ALCOHOL_RETRY
        else:
            self.state = SystemState.WAITING_RIDER

    def _handle_boarding(self, value: object) -> None:
        if not isinstance(value, WeightReading):
            self.state = SystemState.FAULT
            self._send("LOCK")
            return
        baseline = self._boarding.observe(value)
        if baseline is not None:
            self.rider_baseline = baseline
            self.state = SystemState.UNLOCKING
            self._send("UNLOCK")

    def _handle_weight(self, value: object, now: float) -> None:
        if not isinstance(value, WeightReading):
            self.state = SystemState.FAULT
            self._send("LOCK")
            return
        action = self._occupancy.observe(value.total, now)
        if self._occupancy.baseline_kg is not None:
            self.rider_baseline = RiderBaseline(self._occupancy.baseline_kg)
        if action is OccupancyAction.WARN:
            self.state = SystemState.WARNING
            self._send("BUZZ_ON")
        elif action is OccupancyAction.LOCK:
            self.state = SystemState.LOCKED
            self._send("LOCK")
        elif action is OccupancyAction.CLEAR_WARNING:
            self.state = SystemState.MONITORING
            self._send("BUZZ_OFF")

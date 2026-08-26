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
        self._waiting_for_initial_lock = False
        self._authentication_pending = False
        self._logger = logging.getLogger(__name__)

    def on_connected(self) -> None:
        self.state = SystemState.STARTING
        self._waiting_for_initial_lock = True
        self._baseline = None
        self._mq3_samples.clear()
        self._boarding.reset()
        self._occupancy.reset()
        self.rider_baseline = None
        self._send("LOCK")

    def on_authentication_completed(self) -> bool:
        if self.state is SystemState.STARTING:
            self._authentication_pending = True
            return True
        if self.state in {SystemState.CHECKING_ALCOHOL, SystemState.WAITING_RIDER}:
            # A retried HTTP response must acknowledge the already-started check
            # without sending CHECK_MQ3 to the STM32 a second time.
            return True
        if self.state is not SystemState.LOCKED:
            self._logger.warning("Ignoring authentication in state %s", self.state.name)
            return False
        self._start_alcohol_check()
        return True

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
                if self._authentication_pending:
                    self._authentication_pending = False
                    self._start_alcohol_check()
        elif message_type is MessageType.MQ3_START:
            self._baseline = None
            self._mq3_samples.clear()
            self.state = SystemState.CHECKING_ALCOHOL
        elif message_type is MessageType.MQ3_BASELINE:
            self._baseline = int(message.value)
        elif message_type is MessageType.MQ3_SAMPLE:
            self._mq3_samples.append(int(message.value))
        elif message_type is MessageType.MQ3_END:
            self._finish_alcohol_check()
        elif message_type is MessageType.UNLOCK_OK:
            self.state = SystemState.MONITORING
            self._occupancy.reset()
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
        if self.state is not SystemState.WAITING_RIDER:
            self._logger.warning("Ignoring weight check in state %s", self.state.name)
            return False
        self._boarding.reset()
        self.rider_baseline = None
        self.state = SystemState.CHECKING_RIDER
        self._send("CHECK_WEIGHT")
        return True

    def _start_alcohol_check(self) -> None:
        self._baseline = None
        self._mq3_samples.clear()
        self.state = SystemState.CHECKING_ALCOHOL
        self._send("CHECK_MQ3")

    def _finish_alcohol_check(self) -> None:
        result = self._alcohol.evaluate(self._baseline, self._mq3_samples)
        self.last_alcohol_result = result
        if result.unsafe:
            self.state = SystemState.LOCKED
            self._send("LOCK")
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
        if action is OccupancyAction.WARN:
            self.state = SystemState.WARNING
            self._send("BUZZ_ON")
        elif action is OccupancyAction.LOCK:
            self.state = SystemState.LOCKED
            self._send("LOCK")
        elif action is OccupancyAction.CLEAR_WARNING:
            self.state = SystemState.MONITORING
            self._send("BUZZ_OFF")

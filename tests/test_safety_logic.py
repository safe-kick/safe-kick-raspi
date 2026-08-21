import unittest

from app.safety.boarding import BoardingMonitor
from app.safety.config import AppConfig, BoardingConfig, WeightConfig
from app.safety.controller import Controller, SystemState
from app.safety.occupancy import OccupancyAction, OccupancyMonitor
from app.safety.protocol import MessageType, MotorState, WeightReading, parse_line


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class SafetyLogicTest(unittest.TestCase):
    def test_protocol_parses_weight(self) -> None:
        message = parse_line("FL:20.00 FR:20.00 RL:15.00 RR:10.00 TOTAL:65.00")
        self.assertEqual(message.type, MessageType.WEIGHT_SAMPLE)
        self.assertEqual(message.value.total, 65.0)

    def test_protocol_parses_motor_state(self) -> None:
        message = parse_line("MOTOR:UNLOCKED SPEED:42")
        self.assertEqual(message.type, MessageType.MOTOR_STATE)
        self.assertEqual(message.value, MotorState(unlocked=True, speed_percent=42))

    def test_boarding_requires_three_stable_samples(self) -> None:
        monitor = BoardingMonitor(BoardingConfig())
        readings = [
            WeightReading(24, 20, 11, 10, 65),
            WeightReading(23, 21, 10.5, 10.5, 65),
            WeightReading(22, 22, 10, 11, 65),
        ]
        self.assertIsNone(monitor.observe(readings[0]))
        self.assertIsNone(monitor.observe(readings[1]))
        self.assertEqual(monitor.observe(readings[2]).total_kg, 65)

    def test_controller_authenticates_then_unlocks(self) -> None:
        commands: list[str] = []
        controller = Controller(AppConfig(), commands.append)
        controller.on_connected()
        controller.handle(parse_line("LOCK_OK"))
        controller.on_authentication_completed()
        controller.handle(parse_line("MQ3_BASELINE:600"))
        for value in range(610, 690, 10):
            controller.handle(parse_line(f"MQ3:{value}"))
        controller.handle(parse_line("[END_MQ3]"))
        self.assertEqual(controller.state, SystemState.WAITING_RIDER)
        self.assertTrue(controller.start_rider_check())
        for _ in range(3):
            controller.handle(
                parse_line("FL:24.00 FR:20.00 RL:11.00 RR:10.00 TOTAL:65.00")
            )
        self.assertEqual(controller.state, SystemState.UNLOCKING)
        self.assertEqual(commands, ["LOCK", "CHECK_MQ3", "CHECK_WEIGHT", "UNLOCK"])
        controller.handle(parse_line("UNLOCK_OK"))
        self.assertEqual(controller.state, SystemState.MONITORING)

    def test_sustained_two_person_weight_warns_then_locks(self) -> None:
        monitor = OccupancyMonitor(
            WeightConfig(
                two_person_threshold_kg=110,
                warning_after_seconds=4,
                lock_after_warning_seconds=10,
            )
        )
        self.assertEqual(monitor.observe(120, 0), OccupancyAction.NONE)
        self.assertEqual(monitor.observe(120, 4), OccupancyAction.WARN)
        self.assertEqual(monitor.observe(120, 14), OccupancyAction.LOCK)


if __name__ == "__main__":
    unittest.main()

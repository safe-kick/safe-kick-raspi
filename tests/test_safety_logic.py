import unittest

from app.safety.alcohol import AlcoholPolicy
from app.safety.blow import BlowDetector
from app.safety.boarding import BoardingMonitor
from app.safety.config import AlcoholConfig, AppConfig, BlowConfig, BoardingConfig, WeightConfig
from app.safety.controller import Controller, SystemState
from app.safety.occupancy import OccupancyAction, OccupancyMonitor
from app.safety.protocol import MessageType, MotorState, WeightReading, parse_line


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class SafetyLogicTest(unittest.TestCase):
    def test_alcohol_requires_three_consecutive_positive_samples(self) -> None:
        policy = AlcoholPolicy(
            AlcoholConfig(minimum_delta=2000, absolute_threshold=10000)
        )

        nonconsecutive = policy.evaluate(
            100,
            [2100, 2200, 150, 2300, 2400, 150, 2500, 150],
        )
        consecutive = policy.evaluate(
            100,
            [150, 2100, 2200, 2300, 150, 150, 150, 150],
        )

        self.assertEqual(nonconsecutive.positive_samples, 5)
        self.assertFalse(nonconsecutive.unsafe)
        self.assertEqual(consecutive.positive_samples, 3)
        self.assertTrue(consecutive.unsafe)

    def test_alcohol_fails_when_absolute_threshold_is_exceeded(self) -> None:
        policy = AlcoholPolicy(AlcoholConfig(absolute_threshold=1500))

        at_threshold = policy.evaluate(
            1400,
            [1420, 1440, 1460, 1500, 1480, 1460, 1440, 1420],
        )
        above_threshold = policy.evaluate(
            1400,
            [1420, 1440, 1460, 1501, 1480, 1460, 1440, 1420],
        )

        self.assertFalse(at_threshold.unsafe)
        self.assertTrue(above_threshold.unsafe)
        self.assertEqual(above_threshold.reason, "absolute threshold exceeded")

    def test_protocol_parses_weight(self) -> None:
        message = parse_line("FL:20.00 FR:20.00 RL:15.00 RR:10.00 TOTAL:65.00")
        self.assertEqual(message.type, MessageType.WEIGHT_SAMPLE)
        self.assertEqual(message.value.total, 65.0)

    def test_protocol_parses_negative_sensor_noise(self) -> None:
        message = parse_line("FL:-0.01 FR:+0.01 RL:0.00 RR:-0.00 TOTAL:0.00")
        self.assertEqual(message.type, MessageType.WEIGHT_SAMPLE)
        self.assertEqual(message.value.fl, -0.01)

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
        controller.request_baseline_capture()
        controller.handle(parse_line("[CHECK_MQ3_BASELINE]"))
        controller.handle(parse_line("MQ3_BASELINE:90"))
        controller.handle(parse_line("[END_MQ3_BASELINE]"))
        controller.on_authentication_completed()
        controller.handle(parse_line("[CHECK_MQ3_MEASURE]"))
        controller.handle(parse_line("MEASURE_BEGIN"))
        for value in [110, 108, 92, 92, 88, 88, 93, 92]:
            controller.handle(parse_line(f"MQ3:{value}"))
        controller.set_hw484_result(True)
        controller.handle(parse_line("MEASURE_END"))
        self.assertEqual(controller.state, SystemState.WAITING_RIDER)
        self.assertTrue(controller.start_rider_check())
        for _ in range(3):
            controller.handle(
                parse_line("FL:24.00 FR:20.00 RL:11.00 RR:10.00 TOTAL:65.00")
            )
        self.assertEqual(controller.state, SystemState.UNLOCKING)
        self.assertEqual(commands, [
            "LOCK", "CHECK_MQ3_BASELINE", "CHECK_MQ3_MEASURE",
            "CHECK_WEIGHT", "UNLOCK",
        ])
        controller.handle(parse_line("UNLOCK_OK"))
        self.assertEqual(controller.state, SystemState.MONITORING)

    def test_retried_authentication_does_not_restart_alcohol_check(self) -> None:
        commands: list[str] = []
        controller = Controller(AppConfig(), commands.append)
        controller.on_connected()
        controller.handle(parse_line("LOCK_OK"))
        controller.request_baseline_capture()
        controller.handle(parse_line("MQ3_BASELINE:90"))
        controller.handle(parse_line("[END_MQ3_BASELINE]"))

        self.assertTrue(controller.on_authentication_completed())
        self.assertTrue(controller.on_authentication_completed())

        self.assertEqual(controller.state, SystemState.CHECKING_ALCOHOL)
        self.assertEqual(commands, ["LOCK", "CHECK_MQ3_BASELINE", "CHECK_MQ3_MEASURE"])

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

    def test_two_person_warning_clears_when_weight_recovers(self) -> None:
        monitor = OccupancyMonitor(WeightConfig(two_person_threshold_kg=110))
        self.assertEqual(monitor.observe(120, 0), OccupancyAction.NONE)
        self.assertEqual(monitor.observe(120, 4), OccupancyAction.WARN)
        self.assertEqual(monitor.observe(80, 5), OccupancyAction.CLEAR_WARNING)
        self.assertEqual(monitor.observe(120, 6), OccupancyAction.NONE)

    def test_unsafe_alcohol_result_keeps_vehicle_locked(self) -> None:
        commands: list[str] = []
        controller = Controller(AppConfig(), commands.append)
        controller.on_connected()
        controller.handle(parse_line("LOCK_OK"))
        controller.request_baseline_capture()
        controller.handle(parse_line("MQ3_BASELINE:600"))
        controller.handle(parse_line("[END_MQ3_BASELINE]"))
        controller.on_authentication_completed()
        for value in [1501] * 8:
            controller.handle(parse_line(f"MQ3:{value}"))
        controller.set_hw484_result(True)
        controller.handle(parse_line("MEASURE_END"))

        self.assertEqual(controller.state, SystemState.LOCKED)
        self.assertTrue(controller.last_alcohol_result.unsafe)
        self.assertEqual(commands[-1], "LOCK")

    def test_hw484_tolerates_short_gap_and_resets_after_long_gap(self) -> None:
        detector = BlowDetector(BlowConfig(minimum_seconds=1.0, max_gap_seconds=0.2))

        detector.observe(True, 0.0)
        detector.observe(True, 0.5)
        detector.observe(False, 0.6)
        short_gap = detector.observe(True, 0.75)
        success = detector.observe(True, 1.0)

        self.assertEqual(short_gap.status, "blowing")
        self.assertTrue(success.detected)

        detector.reset()
        detector.observe(True, 2.0)
        detector.observe(False, 2.5)
        retry = detector.observe(False, 2.71)

        self.assertEqual(retry.status, "retry")
        self.assertEqual(retry.duration, 0.0)

    def test_invalid_hw484_breath_retries_without_recapturing_baseline(self) -> None:
        commands: list[str] = []
        controller = Controller(AppConfig(), commands.append)
        controller.on_connected()
        controller.handle(parse_line("LOCK_OK"))
        controller.request_baseline_capture()
        controller.handle(parse_line("MQ3_BASELINE:90"))
        controller.handle(parse_line("[END_MQ3_BASELINE]"))

        self.assertTrue(controller.on_authentication_completed())
        for value in [95] * 8:
            controller.handle(parse_line(f"MQ3:{value}"))
        controller.set_hw484_result(False)
        controller.handle(parse_line("MEASURE_END"))

        self.assertEqual(controller.state, SystemState.ALCOHOL_RETRY)
        self.assertTrue(controller.on_authentication_completed())
        self.assertEqual(commands.count("CHECK_MQ3_BASELINE"), 1)
        self.assertEqual(commands.count("CHECK_MQ3_MEASURE"), 2)

    def test_rider_check_retry_resets_samples_without_restarting_stream(self) -> None:
        commands: list[str] = []
        controller = Controller(AppConfig(), commands.append)
        controller.state = SystemState.WAITING_RIDER

        self.assertTrue(controller.start_rider_check())
        controller.handle(parse_line("FL:30 FR:30 RL:30 RR:30 TOTAL:120"))
        self.assertTrue(controller.start_rider_check())

        self.assertEqual(controller.state, SystemState.CHECKING_RIDER)
        self.assertEqual(commands.count("CHECK_WEIGHT"), 1)


if __name__ == "__main__":
    unittest.main()

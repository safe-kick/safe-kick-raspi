import os
import unittest

os.environ["USE_UART_MOCK"] = "true"

from app.managers.session_manager import SessionManager
from app.services.safety_service import safety_service


class SafetyServiceTest(unittest.TestCase):
    def tearDown(self) -> None:
        SessionManager.end()

    def test_face_auth_event_runs_full_mock_safety_flow(self) -> None:
        safety_service.start()
        SessionManager.start(1, "KB-001", 7)
        safety_service.prepare_session()

        accepted = safety_service.authentication_completed(7)

        self.assertTrue(accepted)
        self.assertTrue(SessionManager.is_locked())
        self.assertEqual(safety_service.status()["safety_state"], "waiting_rider")

        weight_check_started = safety_service.start_weight_check(7)

        self.assertTrue(weight_check_started)
        self.assertFalse(SessionManager.is_locked())
        self.assertEqual(safety_service.status()["safety_state"], "monitoring")
        self.assertEqual(SessionManager.get_sensor_data()["weight"], 65.0)
        self.assertFalse(safety_service.status()["alcohol_result"]["unsafe"])
        self.assertEqual(len(safety_service.status()["alcohol_result"]["samples"]), 8)
        self.assertEqual(safety_service.status()["rider_baseline_kg"], 65.0)

    def test_rejects_authentication_for_another_user(self) -> None:
        safety_service.start()
        SessionManager.start(2, "KB-001", 7)
        safety_service.prepare_session()

        self.assertFalse(safety_service.authentication_completed(8))
        self.assertTrue(SessionManager.is_locked())

    def test_motor_test_commands_with_uart_mock(self) -> None:
        safety_service.start()

        self.assertEqual(safety_service.send_motor_test_command("UNLOCK"), "accepted")
        self.assertEqual(safety_service.send_motor_test_command("BUZZ_ON"), "accepted")
        self.assertEqual(safety_service.send_motor_test_command("MOTOR_STATE"), "accepted")

        motor_state = safety_service.status()["motor_state"]
        self.assertEqual(motor_state, {"unlocked": True, "speed_percent": 30})

        self.assertEqual(safety_service.send_motor_test_command("LOCK"), "accepted")


if __name__ == "__main__":
    unittest.main()

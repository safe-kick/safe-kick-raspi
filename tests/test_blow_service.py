import threading
import unittest

from app.safety.config import BlowConfig
from app.services.blow_service import BlowService


class BlowServiceTest(unittest.TestCase):
    def test_diagnostics_report_detected_active_low_signal(self) -> None:
        completed = threading.Event()
        service = BlowService(
            BlowConfig(minimum_seconds=0.02, poll_interval_seconds=0.005),
            reader=lambda: True,
        )
        try:
            service.start(lambda reading: completed.set() if reading.detected else None)

            self.assertTrue(completed.wait(timeout=0.5))
            diagnostics = service.diagnostics
            self.assertTrue(diagnostics["signal_seen"])
            self.assertTrue(diagnostics["last_signal_active"])
            self.assertIsNone(diagnostics["last_error"])
        finally:
            service.close()

    def test_gpio_read_error_is_reported(self) -> None:
        reported = threading.Event()

        def failing_reader() -> bool:
            raise OSError("GPIO unavailable")

        service = BlowService(
            BlowConfig(poll_interval_seconds=0.005),
            reader=failing_reader,
        )
        try:
            service.start(lambda _reading: None, lambda _error: reported.set())

            self.assertTrue(reported.wait(timeout=0.5))
            self.assertEqual(service.diagnostics["last_error"], "gpio_read_failed")
        finally:
            service.close()


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import db
from app.managers.session_manager import SessionManager
from app.services import session_service


class SessionServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temporary_directory = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self._temporary_directory.name) / "safe_kick.db"
        db.init_db()
        SessionManager.end()

    def tearDown(self) -> None:
        SessionManager.end()
        db.DB_PATH = self._original_db_path
        self._temporary_directory.cleanup()

    def test_end_session_posts_enriched_summary(self) -> None:
        request = SimpleNamespace(user_id=7, kickboard_id="KB-001")
        with patch("app.services.session_service.safety_service.prepare_session"):
            started = session_service.start_session(request)

        SessionManager.update_face_score(0.87)
        SessionManager.update_gas(640)
        SessionManager.update_weight(65)
        SessionManager.warn_two_person()

        with patch("app.services.session_service.safety_service.request_lock"), patch(
            "app.services.session_service.send_session_summary",
            return_value={"status": "sent", "http_status": 202},
        ) as send_summary:
            ended = session_service.end_session()

        summary = send_summary.call_args.args[0]
        self.assertEqual(summary["id"], started["data"]["session_id"])
        self.assertEqual(summary["sensor"]["face_score"], 0.87)
        self.assertEqual(summary["warning_reasons"], ["two_person"])
        self.assertEqual(ended["data"]["backend_sync"]["status"], "sent")
        self.assertFalse(SessionManager.is_active())

    def test_start_weight_check_delegates_to_safety_service(self) -> None:
        with patch(
            "app.services.session_service.safety_service.start_weight_check",
            return_value=True,
        ) as start_weight_check:
            accepted = session_service.start_weight_check(7)

        self.assertTrue(accepted)
        start_weight_check.assert_called_once_with(7)

    def test_start_alcohol_check_delegates_to_safety_service(self) -> None:
        with patch(
            "app.services.session_service.safety_service.authentication_completed",
            return_value=True,
        ) as authentication_completed:
            accepted = session_service.start_alcohol_check(7)

        self.assertTrue(accepted)
        authentication_completed.assert_called_once_with(7)

    def test_start_mq3_baseline_delegates_to_safety_service(self) -> None:
        with patch(
            "app.services.session_service.safety_service.request_baseline",
            return_value="in_progress",
        ) as request_baseline:
            result = session_service.start_mq3_baseline(7)

        self.assertEqual(result, "in_progress")
        request_baseline.assert_called_once_with(7)

    def test_new_session_waits_for_mq3_baseline(self) -> None:
        request = SimpleNamespace(user_id=7, kickboard_id="KB-001")
        with patch("app.services.session_service.safety_service.prepare_session"):
            session_service.start_session(request)

        self.assertEqual(SessionManager.get_baseline_status(), "measuring")
        self.assertIsNone(SessionManager.get_baseline())


if __name__ == "__main__":
    unittest.main()

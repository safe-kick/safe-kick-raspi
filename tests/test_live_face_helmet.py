import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from app import db
from app.managers.session_manager import SessionManager
from app.routes.face import FaceVerifyRequest, live_verify_face
from app.services.face_attempt_service import face_attempt_service
from app.services.helmet_service import HelmetService


class HelmetServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._api_key = os.environ.get("ROBOFLOW_API_KEY")
        os.environ["ROBOFLOW_API_KEY"] = "test-key"

    def tearDown(self) -> None:
        if self._api_key is None:
            os.environ.pop("ROBOFLOW_API_KEY", None)
        else:
            os.environ["ROBOFLOW_API_KEY"] = self._api_key

    def _service(self, response=None, error=None):
        client = Mock()
        if error is not None:
            client.infer.side_effect = error
        else:
            client.infer.return_value = response
        return HelmetService(client_factory=lambda **_kwargs: client)

    def test_with_helmet_above_threshold_passes(self) -> None:
        service = self._service({
            "predictions": [{"class": "With Helmet", "confidence": 0.92}],
        })
        result = service.verify_image(np.zeros((2, 2, 3), dtype=np.uint8))
        self.assertTrue(result["helmet_verified"])
        self.assertEqual(result["reason"], "success")

    def test_without_helmet_fails(self) -> None:
        service = self._service({
            "predictions": [
                {"class": "With Helmet", "confidence": 0.95},
                {"class": "Without Helmet", "confidence": 0.70},
            ],
        })
        result = service.verify_image(np.zeros((2, 2, 3), dtype=np.uint8))
        self.assertFalse(result["helmet_verified"])
        self.assertEqual(result["reason"], "without_helmet_detected")

    def test_no_predictions_and_inference_errors_fail_safely(self) -> None:
        no_prediction = self._service({"predictions": []}).verify_image(
            np.zeros((2, 2, 3), dtype=np.uint8)
        )
        failed_request = self._service(error=TimeoutError()).verify_image(
            np.zeros((2, 2, 3), dtype=np.uint8)
        )
        self.assertFalse(no_prediction["helmet_verified"])
        self.assertEqual(no_prediction["reason"], "no_predictions")
        self.assertFalse(failed_request["helmet_verified"])
        self.assertEqual(failed_request["reason"], "inference_error")

    def test_missing_api_key_and_invalid_response_fail_safely(self) -> None:
        os.environ.pop("ROBOFLOW_API_KEY", None)
        missing_key = self._service({}).verify_image(
            np.zeros((2, 2, 3), dtype=np.uint8)
        )
        os.environ["ROBOFLOW_API_KEY"] = "test-key"
        invalid_response = self._service("unexpected").verify_image(
            np.zeros((2, 2, 3), dtype=np.uint8)
        )
        self.assertEqual(missing_key["reason"], "api_key_not_configured")
        self.assertEqual(invalid_response["reason"], "invalid_response")


class LiveVerifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temporary_directory = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self._temporary_directory.name) / "safe_kick.db"
        db.init_db()
        SessionManager.end()
        face_attempt_service.reset(7)
        self.image = np.zeros((2, 2, 3), dtype=np.uint8)

    def tearDown(self) -> None:
        SessionManager.end()
        db.DB_PATH = self._original_db_path
        self._temporary_directory.cleanup()

    def _verify(self, face_verified: bool, helmet_verified: bool):
        face = {
            "match": face_verified,
            "confidence": 0.8 if face_verified else 0.2,
            "face_vector": [],
            "reason": "success" if face_verified else "not_matched",
        }
        helmet = {
            "helmet_verified": helmet_verified,
            "helmet_score": 0.9 if helmet_verified else 0.1,
            "helmet_class": "With Helmet" if helmet_verified else None,
            "reason": "success" if helmet_verified else "helmet_not_detected",
        }
        with (
            patch(
                "app.routes.face.face_service.face_service.decode_base64_image",
                return_value=self.image,
            ),
            patch(
                "app.routes.face.face_service.face_service.verify_face_image",
                return_value=face,
            ),
            patch("app.routes.face.helmet_service.verify_image", return_value=helmet),
            patch(
                "app.routes.face.safety_service.authentication_completed",
                return_value=True,
            ) as auth_completed,
        ):
            response = live_verify_face(FaceVerifyRequest(user_id=7, image="frame"))
        return response, auth_completed

    def test_all_face_helmet_combinations(self) -> None:
        for face, helmet, expected in (
            (True, True, True),
            (True, False, False),
            (False, True, False),
            (False, False, False),
        ):
            with self.subTest(face=face, helmet=helmet):
                response, auth_completed = self._verify(face, helmet)
                self.assertEqual(response["data"]["verified"], expected)
                self.assertEqual(auth_completed.called, expected)

    def test_failed_live_verify_does_not_increment_retry_count(self) -> None:
        before = face_attempt_service.get_status(7)
        response, _ = self._verify(False, False)
        after = face_attempt_service.get_status(7)
        self.assertFalse(response["data"]["verified"])
        self.assertEqual(after.failed_attempts, before.failed_attempts)


if __name__ == "__main__":
    unittest.main()

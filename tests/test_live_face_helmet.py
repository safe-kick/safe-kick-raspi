import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from fastapi import Response, status

from app import db
from app.managers.session_manager import SessionManager
from app.routes.face import FaceVerifyRequest, live_verify_face
from app.services.face_attempt_service import face_attempt_service
from app.services.face_service import FaceService
from app.services.helmet_service import HelmetService


class HelmetServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._api_key = os.environ.get("ROBOFLOW_API_KEY")
        self._timeout = os.environ.get("HELMET_INFERENCE_TIMEOUT_SECONDS")
        os.environ["ROBOFLOW_API_KEY"] = "test-key"

    def tearDown(self) -> None:
        if self._api_key is None:
            os.environ.pop("ROBOFLOW_API_KEY", None)
        else:
            os.environ["ROBOFLOW_API_KEY"] = self._api_key
        if self._timeout is None:
            os.environ.pop("HELMET_INFERENCE_TIMEOUT_SECONDS", None)
        else:
            os.environ["HELMET_INFERENCE_TIMEOUT_SECONDS"] = self._timeout

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
        self.assertTrue(result["helmet_ok"])
        self.assertEqual(result["detected_class"], "With Helmet")
        self.assertEqual(result["confidence"], 0.92)
        self.assertEqual(result["without_helmet_score"], 0.0)
        self.assertEqual(result["reason"], "success")

    def test_passes_when_with_is_high_and_without_is_low(self) -> None:
        service = self._service({
            "predictions": [
                {"class": "With Helmet", "confidence": 0.90},
                {"class": "Without Helmet", "confidence": 0.50},
            ],
        })
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            result = service.verify_image(np.zeros((2, 2, 3), dtype=np.uint8))
        self.assertTrue(result["helmet_ok"])
        self.assertEqual(result["helmet_score"], 0.90)
        self.assertEqual(result["without_helmet_score"], 0.50)
        message = " ".join(captured.output)
        self.assertIn("With Helmet threshold_min=0.9000", message)
        self.assertIn("Without Helmet threshold_max=0.5000", message)
        self.assertIn("result=PASS", message)

    def test_uses_required_serverless_model(self) -> None:
        original_model = os.environ.pop("ROBOFLOW_HELMET_MODEL_ID", None)
        client = Mock()
        client.infer.return_value = {"predictions": []}
        factory = Mock(return_value=client)
        try:
            HelmetService(client_factory=factory).verify_image(
                np.zeros((2, 2, 3), dtype=np.uint8)
            )
        finally:
            if original_model is not None:
                os.environ["ROBOFLOW_HELMET_MODEL_ID"] = original_model

        factory.assert_called_once_with(
            api_key="test-key",
            api_url="https://serverless.roboflow.com",
        )
        self.assertEqual(client.infer.call_args.kwargs["model_id"], "helmet-srsz5/2")

    def test_logs_model_id_for_each_inference(self) -> None:
        service = self._service({"predictions": []})
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            service.verify_image(np.zeros((2, 2, 3), dtype=np.uint8))
        self.assertIn("model_id=helmet-srsz5/2", " ".join(captured.output))

    def test_without_helmet_fails(self) -> None:
        service = self._service({
            "predictions": [
                {"class": "With Helmet", "confidence": 0.95},
                {"class": "Without Helmet", "confidence": 0.70},
            ],
        })
        result = service.verify_image(np.zeros((2, 2, 3), dtype=np.uint8))
        self.assertFalse(result["helmet_verified"])
        self.assertFalse(result["helmet_ok"])
        self.assertEqual(result["detected_class"], "With Helmet")
        self.assertEqual(result["without_helmet_score"], 0.70)
        self.assertEqual(result["reason"], "without_helmet_detected")

    def test_with_helmet_below_threshold_fails(self) -> None:
        service = self._service({
            "predictions": [{"class": "With Helmet", "confidence": 0.69}],
        })
        result = service.verify_image(np.zeros((2, 2, 3), dtype=np.uint8))
        self.assertFalse(result["helmet_ok"])
        self.assertEqual(result["detected_class"], "With Helmet")
        self.assertEqual(result["confidence"], 0.69)
        self.assertEqual(result["reason"], "confidence_below_threshold")

    def test_inference_timeout_fails_safely(self) -> None:
        os.environ["HELMET_INFERENCE_TIMEOUT_SECONDS"] = "0.01"
        client = Mock()
        client.infer.side_effect = lambda *_args, **_kwargs: time.sleep(0.1)
        service = HelmetService(client_factory=lambda **_kwargs: client)
        result = service.verify_image(np.zeros((2, 2, 3), dtype=np.uint8))
        self.assertFalse(result["helmet_ok"])
        self.assertEqual(result["reason"], "inference_timeout")

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
        self.assertEqual(failed_request["reason"], "inference_timeout")

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


class FaceRotationTest(unittest.TestCase):
    def test_retries_rotated_images_when_original_has_no_face(self) -> None:
        face = Mock()
        face.bbox = np.array([0, 0, 10, 10])
        face.embedding = np.array([0.1, 0.2], dtype=np.float32)
        model = Mock()
        model.get.side_effect = [[], [face]]
        service = FaceService()
        service._app = model

        embedding = service.extract_embedding(
            np.zeros((2, 3, 3), dtype=np.uint8)
        )

        np.testing.assert_array_equal(embedding, face.embedding)
        self.assertEqual(model.get.call_count, 2)
        self.assertEqual(model.get.call_args_list[0].args[0].shape, (2, 3, 3))
        self.assertEqual(model.get.call_args_list[1].args[0].shape, (3, 2, 3))

    def test_returns_none_after_trying_all_orientations(self) -> None:
        model = Mock()
        model.get.return_value = []
        service = FaceService()
        service._app = model

        result = service.extract_embedding(np.zeros((2, 3, 3), dtype=np.uint8))

        self.assertIsNone(result)
        self.assertEqual(model.get.call_count, 4)


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
            "helmet_ok": helmet_verified,
            "detected_class": "With Helmet" if helmet_verified else None,
            "confidence": 0.9 if helmet_verified else None,
            "helmet_bbox": None,
            "without_helmet_score": 0.0,
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
            http_response = Response()
            response = live_verify_face(
                FaceVerifyRequest(user_id=7, image="frame"),
                http_response,
            )
        return response, auth_completed, http_response

    def test_all_face_helmet_combinations(self) -> None:
        for face, helmet, expected in (
            (True, True, True),
            (True, False, False),
            (False, True, False),
            (False, False, False),
        ):
            with self.subTest(face=face, helmet=helmet):
                response, auth_completed, http_response = self._verify(face, helmet)
                self.assertEqual(response["data"]["verified"], expected)
                self.assertEqual(auth_completed.called, expected)
                self.assertEqual(
                    http_response.status_code,
                    status.HTTP_200_OK,
                )
                self.assertEqual(response["data"]["face_verified"], face)
                self.assertEqual(response["data"]["helmet_verified"], helmet)

    def test_failed_live_verify_does_not_increment_retry_count(self) -> None:
        before = face_attempt_service.get_status(7)
        response, _, _ = self._verify(False, False)
        after = face_attempt_service.get_status(7)
        self.assertFalse(response["data"]["verified"])
        self.assertEqual(after.failed_attempts, before.failed_attempts)

    def test_invalid_image_returns_http_200_with_structured_failure(self) -> None:
        before = face_attempt_service.get_status(7)
        with patch(
            "app.routes.face.face_service.face_service.decode_base64_image",
            return_value=None,
        ):
            http_response = Response()
            response = live_verify_face(
                FaceVerifyRequest(user_id=7, image="invalid"),
                http_response,
            )

        after = face_attempt_service.get_status(7)
        self.assertEqual(http_response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["status"], "error")
        self.assertFalse(response["data"]["verified"])
        self.assertFalse(response["data"]["face_verified"])
        self.assertFalse(response["data"]["helmet_verified"])
        self.assertEqual(response["data"]["face_reason"], "invalid_image")
        self.assertEqual(response["data"]["helmet_reason"], "invalid_image")
        self.assertEqual(after.failed_attempts, before.failed_attempts)

    def test_live_verify_logs_scores_thresholds_and_result(self) -> None:
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            self._verify(True, True)

        message = " ".join(captured.output)
        self.assertIn("face_score=80.00%", message)
        self.assertIn("face_threshold=45.00%", message)
        self.assertIn("helmet_score=90.00%", message)
        self.assertIn("helmet_threshold=90.00%", message)
        self.assertIn("verified=True", message)


if __name__ == "__main__":
    unittest.main()

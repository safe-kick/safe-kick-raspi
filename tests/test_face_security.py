import os
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app import db
from app.managers.session_manager import SessionManager
from app.routes.face import FaceVerifyRequest, verify_face
from app.services.embedding_store import EmbeddingStore, NodeEmbeddingStore
from app.services.face_attempt_service import FaceAttemptService, face_attempt_service
from app.services.safety_service import safety_service


class FaceSecurityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temporary_directory = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self._temporary_directory.name) / "safe_kick.db"
        db.init_db()
        SessionManager.end()

    def tearDown(self) -> None:
        safety_service.stop()
        SessionManager.end()
        db.DB_PATH = self._original_db_path
        self._temporary_directory.cleanup()

    def test_failed_attempts_lock_then_expire(self) -> None:
        now = [100.0]
        service = FaceAttemptService(
            max_attempts=3,
            lockout_seconds=10,
            clock=lambda: now[0],
        )

        self.assertEqual(service.record_failure(7).attempts_remaining, 2)
        self.assertEqual(service.record_failure(7).attempts_remaining, 1)
        locked = service.record_failure(7)
        self.assertFalse(locked.allowed)
        self.assertEqual(locked.retry_after_seconds, 10)

        now[0] = 111.0
        reset = service.get_status(7)
        self.assertTrue(reset.allowed)
        self.assertEqual(reset.failed_attempts, 0)

    def test_embedding_is_owner_only_and_deletable(self) -> None:
        store = EmbeddingStore(Path(self._temporary_directory.name) / "users")
        expected = np.array([0.1, 0.2, 0.3], dtype=np.float32)

        path = store.save(3, expected)

        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        np.testing.assert_array_equal(store.load(3), expected)
        self.assertTrue(store.delete(3))
        self.assertFalse(store.delete(3))

    def test_node_embedding_store_sends_device_identity_and_loads_vector(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "status": "success",
                    "data": {
                        "embedding": [0.1, 0.2],
                        "dimension": 2,
                        "model_name": "buffalo_sc",
                    },
                }).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        environment = {
            "INTERNAL_API_KEY": "internal-secret",
            "KICKBOARD_DEVICE_ID": "RPI-001",
            "NODE_EMBEDDING_TIMEOUT_SECONDS": "2.5",
        }
        with patch.dict(os.environ, environment, clear=True), patch(
            "app.services.embedding_store.urlopen",
            side_effect=fake_urlopen,
        ):
            store = NodeEmbeddingStore("https://node.test/internal/face-embeddings")
            embedding = store.load(7)

        np.testing.assert_allclose(embedding, np.array([0.1, 0.2], dtype=np.float32))
        self.assertEqual(captured["timeout"], 2.5)
        self.assertEqual(captured["request"].get_header("X-device-id"), "RPI-001")
        self.assertEqual(captured["request"].get_header("X-internal-api-key"), "internal-secret")

    def test_face_success_resets_failures_without_starting_safety_check(self) -> None:
        safety_service.start()
        SessionManager.start(1, "KB-001", 7)
        safety_service.prepare_session()
        face_attempt_service.reset(7)
        face_attempt_service.record_failure(7)
        matched = {
            "match": True,
            "confidence": 0.8,
            "face_vector": [],
            "reason": "success",
        }

        with patch("app.routes.face.face_service.verify_face", return_value=matched):
            response = verify_face(FaceVerifyRequest(user_id=7, image="unused"))

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["data"]["failed_attempts"], 0)
        self.assertFalse(response["data"]["safety_check_started"])
        self.assertNotEqual(safety_service.status()["safety_state"], "waiting_rider")


if __name__ == "__main__":
    unittest.main()

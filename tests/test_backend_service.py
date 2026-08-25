import json
import os
import unittest
from unittest.mock import patch

from app.services.backend_service import send_session_summary


class FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return b'{"accepted":true}'


class BackendServiceTest(unittest.TestCase):
    def test_disabled_without_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(send_session_summary({"id": 1}), {"status": "disabled"})

    def test_posts_summary_with_bearer_token(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        environment = {
            "NODE_SUMMARY_URL": "http://backend.test/rides/summary",
            "NODE_SUMMARY_TOKEN": "secret",
            "NODE_SUMMARY_TIMEOUT_SECONDS": "2.5",
        }
        with patch.dict(os.environ, environment, clear=True), patch(
            "app.services.backend_service.urlopen",
            side_effect=fake_urlopen,
        ):
            result = send_session_summary({"id": 9})

        self.assertEqual(result["status"], "sent")
        self.assertEqual(captured["timeout"], 2.5)
        self.assertEqual(captured["request"].get_header("Authorization"), "Bearer secret")
        payload = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(payload, {"event": "session.ended", "data": {"id": 9}})


if __name__ == "__main__":
    unittest.main()

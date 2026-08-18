from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def send_session_summary(summary: dict) -> dict:
    """Send a completed ride summary to the optional Node.js webhook."""
    url = os.getenv("NODE_SUMMARY_URL", "").strip()
    if not url:
        return {"status": "disabled"}

    payload = json.dumps(
        {"event": "session.ended", "data": summary},
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.getenv("NODE_SUMMARY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, data=payload, headers=headers, method="POST")
    timeout = float(os.getenv("NODE_SUMMARY_TIMEOUT_SECONDS", "3"))
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read(4096).decode("utf-8", errors="replace")
            return {
                "status": "sent",
                "http_status": response.status,
                "response": response_body or None,
            }
    except HTTPError as error:
        return {
            "status": "failed",
            "http_status": error.code,
            "error": str(error),
        }
    except (URLError, OSError, ValueError) as error:
        return {"status": "failed", "error": str(error)}

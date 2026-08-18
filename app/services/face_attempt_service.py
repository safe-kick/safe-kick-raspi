from __future__ import annotations

import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable

from app.db import get_connection


@dataclass(frozen=True)
class AttemptStatus:
    allowed: bool
    failed_attempts: int
    attempts_remaining: int
    retry_after_seconds: int

    def to_dict(self) -> dict:
        return asdict(self)


class FaceAttemptService:
    """Persist face verification failures and enforce a temporary lockout."""

    def __init__(
        self,
        max_attempts: int | None = None,
        lockout_seconds: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.max_attempts = (
            max_attempts
            if max_attempts is not None
            else int(os.getenv("FACE_MAX_VERIFY_ATTEMPTS", "3"))
        )
        self.lockout_seconds = (
            lockout_seconds
            if lockout_seconds is not None
            else int(os.getenv("FACE_VERIFY_LOCKOUT_SECONDS", "300"))
        )
        if self.max_attempts <= 0 or self.lockout_seconds <= 0:
            raise ValueError("Face retry settings must be positive")
        self._clock = clock
        self._lock = threading.RLock()

    def get_status(self, user_id: int) -> AttemptStatus:
        now = self._clock()
        with self._lock:
            conn = get_connection()
            try:
                row = conn.execute(
                    """
                    SELECT failed_attempts, locked_until
                    FROM face_verification_attempts
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()
                if row is None:
                    return self._status(0, None, now)

                locked_until = row["locked_until"]
                if locked_until is not None and locked_until <= now:
                    conn.execute(
                        "DELETE FROM face_verification_attempts WHERE user_id = ?",
                        (user_id,),
                    )
                    conn.commit()
                    return self._status(0, None, now)
                return self._status(row["failed_attempts"], locked_until, now)
            finally:
                conn.close()

    def record_failure(self, user_id: int) -> AttemptStatus:
        now = self._clock()
        with self._lock:
            conn = get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT failed_attempts, locked_until
                    FROM face_verification_attempts
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()
                failed_attempts = 0
                locked_until = None
                if row is not None and (
                    row["locked_until"] is None or row["locked_until"] > now
                ):
                    failed_attempts = row["failed_attempts"]
                    locked_until = row["locked_until"]

                if locked_until is None:
                    failed_attempts += 1
                    if failed_attempts >= self.max_attempts:
                        locked_until = now + self.lockout_seconds

                conn.execute(
                    """
                    INSERT INTO face_verification_attempts (
                        user_id, failed_attempts, locked_until, updated_at
                    ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        failed_attempts = excluded.failed_attempts,
                        locked_until = excluded.locked_until,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, failed_attempts, locked_until),
                )
                conn.commit()
                return self._status(failed_attempts, locked_until, now)
            finally:
                conn.close()

    def reset(self, user_id: int) -> None:
        with self._lock:
            conn = get_connection()
            try:
                conn.execute(
                    "DELETE FROM face_verification_attempts WHERE user_id = ?",
                    (user_id,),
                )
                conn.commit()
            finally:
                conn.close()

    def _status(
        self,
        failed_attempts: int,
        locked_until: float | None,
        now: float,
    ) -> AttemptStatus:
        retry_after = max(0, int((locked_until or 0) - now + 0.999))
        allowed = retry_after == 0
        return AttemptStatus(
            allowed=allowed,
            failed_attempts=failed_attempts,
            attempts_remaining=max(0, self.max_attempts - failed_attempts),
            retry_after_seconds=retry_after,
        )


face_attempt_service = FaceAttemptService()

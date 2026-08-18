import asyncio
import json

from app.db import get_connection
from app.services.backend_service import send_session_summary
from app.managers.session_manager import SessionManager
from app.services.safety_service import safety_service


def start_session(request):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO sessions (kickboard_id, user_id, status)
        VALUES (?, ?, ?)
        """,
        (request.kickboard_id, request.user_id, "active")
    )

    conn.commit()
    session_id = cursor.lastrowid
    conn.close()

    SessionManager.start(
        session_id=session_id,
        kickboard_id=request.kickboard_id,
        user_id=request.user_id
    )
    safety_service.prepare_session()

    return {
        "status": "success",
        "data": {
            "session_id": session_id,
            "kickboard_id": request.kickboard_id,
            "user_id": request.user_id,
            "monitoring": False,
            "safety_state": safety_service.status()["safety_state"]
        },
        "message": "세션이 생성되었습니다. 앱 인증 완료 후 안전 검사를 시작합니다."
    }


async def stream_session():
    while SessionManager.is_active():
        event_data = SessionManager.get_stream_data()

        yield f"data: {json.dumps(event_data)}\n\n"

        await asyncio.sleep(1)


def end_session():
    session_id = SessionManager.get_session_id()

    if session_id is None:
        return {
            "status": "error",
            "data": None,
            "message": "활성화된 세션이 없습니다."
        }

    safety_service.request_lock("user")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE sessions
        SET
            ended_at = CURRENT_TIMESTAMP,
            status = ?,
            warning_count = ?
        WHERE id = ?
        """,
        (
            "ended",
            SessionManager.get_warning_count(),
            session_id
        )
    )

    conn.commit()

    cursor.execute(
        """
        SELECT
            id,
            kickboard_id,
            user_id,
            started_at,
            ended_at,
            status,
            warning_count
        FROM sessions
        WHERE id = ?
        """,
        (session_id,)
    )

    row = cursor.fetchone()
    conn.close()

    summary = dict(row)
    summary["sensor"] = SessionManager.get_sensor_data()
    summary["warning_reasons"] = SessionManager.get_warning_reasons()

    SessionManager.end()
    backend_sync = send_session_summary(summary)

    return {
        "status": "success",
        "data": {
            **summary,
            "backend_sync": backend_sync,
        },
        "message": "운행이 종료되었습니다."
    }


def get_session_summary(session_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            kickboard_id,
            user_id,
            started_at,
            ended_at,
            status,
            warning_count
        FROM sessions
        WHERE id = ?
        """,
        (session_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return dict(row)

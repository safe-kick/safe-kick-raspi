import asyncio
import json
from app.db import get_connection
import app.state as state


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

    state.current_session["session_id"] = session_id
    state.current_session["kickboard_id"] = request.kickboard_id
    state.current_session["user_id"] = request.user_id
    state.current_session["active"] = True
    state.current_session["is_locked"] = False
    state.current_session["status"] = "normal"
    state.current_session["warning_reason"] = None
    state.current_session["warning_count"] = 0
    state.current_session["warning_reasons"] = []

    return {
        "status": "success",
        "data": {
            "session_id": session_id,
            "kickboard_id": request.kickboard_id,
            "user_id": request.user_id,
            "monitoring": True
        },
        "message": "운행 세션이 시작되었습니다."
    }


async def stream_session():
    while state.current_session["active"]:
        event_data = {
            "face_score": state.current_session["face_score"],
            "weight": state.current_session["weight"],
            "gas": state.current_session["gas"],
            "is_two_person": state.current_session["is_two_person"],
            "is_drunk": state.current_session["is_drunk"],
            "is_locked": state.current_session["is_locked"],
            "status": state.current_session["status"],
            "warning_reason": state.current_session["warning_reason"]
        }

        yield f"data: {json.dumps(event_data)}\n\n"
        await asyncio.sleep(1)


def end_session():
    session_id = state.current_session["session_id"]

    if session_id is None:
        return {
            "status": "error",
            "data": None,
            "message": "활성화된 세션이 없습니다."
        }

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
            state.current_session["warning_count"],
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

    state.current_session["active"] = False
    state.current_session["is_locked"] = True
    state.current_session["status"] = "ended"

    state.current_session["session_id"] = None
    state.current_session["kickboard_id"] = None
    state.current_session["user_id"] = None
    state.current_session["warning_reason"] = None

    return {
        "status": "success",
        "data": summary,
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
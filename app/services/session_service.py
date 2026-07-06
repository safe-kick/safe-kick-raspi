import asyncio
import json

import app.state as state

def start_session(request):
    state.current_session["session_id"] = 5
    state.current_session["kickboard_id"] = request.kickboard_id
    state.current_session["user_id"] = request.user_id
    state.current_session["active"] = True
    state.current_session["is_locked"] = False
    state.current_session["status"] = "normal"
    state.current_session["warning_reason"] = None

    return {
        "status": "success",
        "data": {
            "session_id": state.current_session["session_id"],
            "kickboard_id": state.current_session["kickboard_id"],
            "user_id": state.current_session["user_id"],
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
    summary = {
        "session_id": state.current_session["session_id"],
        "kickboard_id": state.current_session["kickboard_id"],
        "user_id": state.current_session["user_id"],
        "duration_sec": 1800,
        "warning_count": state.current_session["warning_count"],
        "warning_reasons": state.current_session["warning_reasons"],
    }

    state.last_session_summary = summary

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
    if state.last_session_summary is None:
        return None

    if state.last_session_summary["session_id"] != session_id:
        return None

    return state.last_session_summary
import app.state as state


def lock_kickboard(session_id: int, reason: str):
    if state.current_session["session_id"] != session_id and state.last_session_summary is None:
        return None

    state.current_session["is_locked"] = True
    state.current_session["status"] = "warning" if reason != "user" else "ended"
    state.current_session["warning_reason"] = reason

    if reason != "user":
        state.current_session["warning_count"] += 1

        if reason not in state.current_session["warning_reasons"]:
            state.current_session["warning_reasons"].append(reason)

    return {
        "session_id": session_id,
        "is_locked": True,
        "reason": reason
    }


def unlock_kickboard(session_id: int):
    if state.current_session["session_id"] != session_id:
        return None

    if state.current_session["is_locked"] is False:
        return "already_unlocked"

    if state.current_session["active"] is False:
        return "inactive_session"

    state.current_session["is_locked"] = False
    state.current_session["status"] = "unlocked"
    state.current_session["warning_reason"] = None

    return {
        "session_id": session_id,
        "is_locked": False
    }
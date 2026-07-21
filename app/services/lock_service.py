from app.managers.session_manager import SessionManager
from app.services.safety_service import safety_service


def lock_kickboard(session_id: int, reason: str):
    if SessionManager.get_session_id() != session_id:
        return None
    safety_service.request_lock(reason)
    return {
        "session_id": session_id,
        "is_locked": SessionManager.is_locked(),
        "reason": reason,
        "safety_state": safety_service.status()["safety_state"],
    }


def unlock_kickboard(session_id: int):
    if SessionManager.get_session_id() != session_id:
        return None
    if not SessionManager.is_active():
        return "inactive_session"
    if not SessionManager.is_locked():
        return "already_unlocked"

    result = safety_service.request_manual_unlock()
    if result != "accepted":
        return result
    return {
        "session_id": session_id,
        "is_locked": SessionManager.is_locked(),
        "safety_state": safety_service.status()["safety_state"],
    }

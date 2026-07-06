from app.managers.session_manager import SessionManager
from app.services import log_service
from app.services.uart_service import uart_service
from app.constants.uart_commands import UARTCommand

def lock_kickboard(session_id: int, reason: str):
    current_session_id = SessionManager.get_session_id()

    if current_session_id != session_id:
        return None

    SessionManager.lock(reason)

    response = uart_service.send_command(UARTCommand.LOCK)
    print(f"[UART] {response}")

    if reason != "user":
        log_service.save_warning_log(
            session_id=session_id,
            warning_type=reason
        )

    return {
        "session_id": session_id,
        "is_locked": True,
        "reason": reason
    }


def unlock_kickboard(session_id: int):
    current_session_id = SessionManager.get_session_id()

    if current_session_id != session_id:
        return None

    if SessionManager.is_locked() is False:
        return "already_unlocked"

    if SessionManager.is_active() is False:
        return "inactive_session"

    SessionManager.unlock()

    response = uart_service.send_command(UARTCommand.UNLOCK)
    print(f"[UART] {response}")

    return {
        "session_id": session_id,
        "is_locked": False
    }
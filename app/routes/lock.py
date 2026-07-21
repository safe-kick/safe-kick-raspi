from fastapi import APIRouter
from pydantic import BaseModel

from app.services import lock_service

router = APIRouter()


class LockRequest(BaseModel):
    session_id: int
    reason: str = "user"


class UnlockRequest(BaseModel):
    session_id: int


@router.post("/lock")
def lock_kickboard(request: LockRequest):
    result = lock_service.lock_kickboard(
        session_id=request.session_id,
        reason=request.reason
    )

    if result is None:
        return {
            "status": "error",
            "data": None,
            "message": "존재하지 않는 세션입니다."
        }

    return {
        "status": "success",
        "data": result,
        "message": "킥보드가 잠금되었습니다."
    }


@router.post("/unlock")
def unlock_kickboard(request: UnlockRequest):
    result = lock_service.unlock_kickboard(
        session_id=request.session_id
    )

    if result is None:
        return {
            "status": "error",
            "data": None,
            "message": "존재하지 않는 세션입니다."
        }

    if result == "already_unlocked":
        return {
            "status": "error",
            "data": None,
            "message": "이미 잠금 해제 상태입니다."
        }

    if result == "inactive_session":
        return {
            "status": "error",
            "data": None,
            "message": "종료된 세션은 잠금 해제할 수 없습니다."
        }

    if result == "manual_unlock_disabled":
        return {
            "status": "error",
            "data": None,
            "message": "직접 잠금 해제는 비활성화되어 있습니다. 앱 인증과 안전 검사를 진행하세요."
        }

    if result == "stm32_disconnected":
        return {
            "status": "error",
            "data": None,
            "message": "STM32가 연결되지 않아 잠금 해제할 수 없습니다."
        }

    return {
        "status": "success",
        "data": result,
        "message": "킥보드 잠금이 해제되었습니다."
    }

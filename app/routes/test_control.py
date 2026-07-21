from fastapi import APIRouter
from pydantic import BaseModel

from app.services.safety_service import safety_service

router = APIRouter(prefix="/test", tags=["test-only"])


class AuthenticationCompleteRequest(BaseModel):
    user_id: int


@router.post("/auth-complete")
def complete_authentication(request: AuthenticationCompleteRequest):
    """Simulate the backend's app-authentication-completed event."""
    accepted = safety_service.authentication_completed(request.user_id)
    return {
        "status": "success" if accepted else "error",
        "data": {
            "accepted": accepted,
            **safety_service.status(),
        },
        "message": (
            "테스트 인증 완료 이벤트를 전달했습니다."
            if accepted
            else "활성 세션이 없거나 세션 사용자와 일치하지 않습니다."
        ),
    }


@router.post("/weight-check")
def start_weight_check(request: AuthenticationCompleteRequest):
    """Start the pre-unlock rider check after MQ3 has passed."""
    accepted = safety_service.start_weight_check(request.user_id)
    return {
        "status": "success" if accepted else "error",
        "data": {
            "accepted": accepted,
            **safety_service.status(),
        },
        "message": (
            "탑승 무게 측정을 시작했습니다."
            if accepted
            else "MQ3 통과 대기 상태가 아니거나 세션 사용자가 일치하지 않습니다."
        ),
    }

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


def _motor_test_response(command: str, success_message: str):
    result = safety_service.send_motor_test_command(command)
    accepted = result == "accepted"
    error_messages = {
        "stm32_disconnected": "STM32가 연결되지 않아 테스트 명령을 전송할 수 없습니다.",
        "response_timeout": "STM32가 MOTOR_STATE를 지원하지 않거나 응답 시간이 초과되었습니다.",
        "invalid_command": "허용되지 않은 모터 테스트 명령입니다.",
    }
    return {
        "status": "success" if accepted else "error",
        "data": {
            "accepted": accepted,
            "command": command,
            **safety_service.status(),
        },
        "message": (
            success_message
            if accepted
            else error_messages.get(result, "모터 테스트 명령 처리에 실패했습니다.")
        ),
    }


@router.post("/motor/unlock", summary="릴레이 ON 및 모터 가속 테스트")
def test_motor_unlock():
    """Bypass authentication and send UNLOCK directly to the STM32."""
    return _motor_test_response("UNLOCK", "릴레이 ON과 모터 가속을 시작했습니다.")


@router.post("/motor/warning", summary="부저 및 모터 감속 테스트")
def test_motor_warning():
    """Send BUZZ_ON so the buzzer starts and the motor ramps down."""
    return _motor_test_response("BUZZ_ON", "부저 경고와 모터 감속을 시작했습니다.")


@router.post("/motor/resume", summary="부저 OFF 및 정상 속도 복구 테스트")
def test_motor_resume():
    """Send BUZZ_OFF so the motor returns to normal speed."""
    return _motor_test_response("BUZZ_OFF", "부저를 끄고 정상 속도 복구를 시작했습니다.")


@router.post("/motor/lock", summary="모터 정지 및 릴레이 OFF 테스트")
def test_motor_lock():
    """Send LOCK so PWM becomes zero and the relay turns off."""
    return _motor_test_response("LOCK", "모터를 정지하고 릴레이를 껐습니다.")


@router.post("/motor/state", summary="STM32 모터 상태 조회")
def test_motor_state():
    """Ask the STM32 for its current lock and PWM state."""
    return _motor_test_response("MOTOR_STATE", "STM32 모터 상태를 조회했습니다.")

from fastapi import APIRouter

from app.managers.session_manager import SessionManager
from app.services.safety_service import safety_service

router = APIRouter()


@router.get("/status")
def get_status():
    return {
        "status": "success",
        "data": {
            **safety_service.status(),
            "session_id": SessionManager.get_session_id(),
            "session_active": SessionManager.is_active(),
            **SessionManager.get_sensor_data(),
        },
        "message": "킥보드 상태 조회에 성공했습니다."
    }

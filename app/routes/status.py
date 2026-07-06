from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
def get_status():
    return {
        "status": "success",
        "data": {
            "kickboard_id": "KB-001",
            "is_locked": True,
            "session_active": False
        },
        "message": "킥보드 상태 조회에 성공했습니다."
    }
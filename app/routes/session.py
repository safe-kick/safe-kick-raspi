from typing import List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from app.services import session_service
from app.managers.session_manager import SessionManager

router = APIRouter()


class SessionStartRequest(BaseModel):
    user_id: int
    kickboard_id: str
    face_vector: Optional[List[float]] = None


class WeightCheckRequest(BaseModel):
    user_id: int


@router.post("/session/start")
def start_session(request: SessionStartRequest):
    return session_service.start_session(request)


@router.get("/session/stream")
def stream_session():
    return StreamingResponse(
        session_service.stream_session(),
        media_type="text/event-stream"
    )


@router.post("/session/weight-check")
def start_weight_check(request: WeightCheckRequest):
    accepted = session_service.start_weight_check(request.user_id)
    return {
        "status": "success" if accepted else "error",
        "data": {
            "accepted": accepted,
            "safety_state": session_service.get_safety_state(),
        },
        "message": (
            "탑승 인원 측정을 시작했습니다."
            if accepted
            else "음주 검사 통과 대기 상태가 아니거나 세션 사용자가 일치하지 않습니다."
        ),
    }


@router.post("/session/alcohol-check")
def start_alcohol_check(request: WeightCheckRequest):
    accepted = session_service.start_alcohol_check(request.user_id)
    return {
        "status": "success" if accepted else "error",
        "data": {
            "accepted": accepted,
            "safety_state": session_service.get_safety_state(),
        },
        "message": (
            "음주 측정을 시작했습니다."
            if accepted
            else (
                "MQ-3 기준값 측정이 완료되지 않았습니다. 기준값을 다시 측정해주세요."
                if SessionManager.get_baseline_status() != "ready"
                else "얼굴·헬멧 인증이 완료되지 않았거나 세션 사용자가 일치하지 않습니다."
            )
        ),
    }


@router.post("/session/mq3-baseline")
def start_mq3_baseline(request: WeightCheckRequest):
    result = session_service.start_mq3_baseline(request.user_id)
    accepted = result in {"ready", "in_progress"}
    return {
        "status": "success" if accepted else "error",
        "data": {
            "accepted": accepted,
            "baseline_status": SessionManager.get_baseline_status(),
        },
        "message": (
            "MQ-3 기준값이 준비되었습니다."
            if result == "ready"
            else "MQ-3 기준값 측정을 시작했습니다."
            if result == "in_progress"
            else "MQ-3 기준값 측정을 시작하지 못했습니다."
        ),
    }


@router.post("/session/end")
def end_session():
    return session_service.end_session()

@router.get("/session/summary")
def get_session_summary(session_id: int):
    summary = session_service.get_session_summary(session_id)

    if summary is None:
        return {
            "status": "error",
            "data": None,
            "message": "세션 정보를 찾을 수 없습니다."
        }

    return {
        "status": "success",
        "data": summary,
        "message": "세션 정보 조회에 성공했습니다."
    }

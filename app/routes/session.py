from typing import List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from app.services import session_service

router = APIRouter()


class SessionStartRequest(BaseModel):
    user_id: int
    kickboard_id: str
    face_vector: Optional[List[float]] = None


@router.post("/session/start")
def start_session(request: SessionStartRequest):
    return session_service.start_session(request)


@router.get("/session/stream")
def stream_session():
    return StreamingResponse(
        session_service.stream_session(),
        media_type="text/event-stream"
    )


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
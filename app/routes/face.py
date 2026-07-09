from fastapi import APIRouter
from pydantic import BaseModel

from app.services import face_service
from app.managers.session_manager import SessionManager

router = APIRouter()


class FaceRequest(BaseModel):
    user_id: int
    image: str


@router.post("/face/register")
def register_face(request: FaceRequest):
    result = face_service.register_face(
        request.user_id,
        request.image
    )

    return {
        "status": "success" if result["registered"] else "error",
        "data": result,
        "message": "면허증 얼굴 등록이 완료되었습니다."
        if result["registered"]
        else "면허증 얼굴 등록에 실패했습니다."
    }


@router.post("/face/verify")
def verify_face(request: FaceRequest):
    result = face_service.verify_face(
        request.user_id,
        request.image
    )

    if result["match"]:
        SessionManager.update_face_score(result["confidence"])

    return {
        "status": "success",
        "data": result,
        "message": "얼굴 인증이 완료되었습니다."
        if result["match"]
        else "얼굴 인증에 실패했습니다."
    }
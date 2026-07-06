from fastapi import APIRouter
from pydantic import BaseModel

from app.services import face_service
from app.managers.session_manager import SessionManager

router = APIRouter()


class FaceVerifyRequest(BaseModel):
    image: str


@router.post("/face/verify")
def verify_face(request: FaceVerifyRequest):
    result = face_service.verify_face(request.image)

    if result["match"]:
        SessionManager.update_face_score(result["confidence"])

    return {
        "status": "success",
        "data": result,
        "message": "얼굴 인증이 완료되었습니다." if result["match"] else "얼굴 인증에 실패했습니다."
    }
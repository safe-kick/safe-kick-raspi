from fastapi import APIRouter
from pydantic import BaseModel

from app.services import face_service
from app.managers.session_manager import SessionManager
from app.services.safety_service import safety_service


router = APIRouter()


class FaceRegisterRequest(BaseModel):
    user_id: int
    image: str


class FaceVerifyRequest(BaseModel):
    user_id: int
    image: str


@router.post("/face/register")
def register_face(
    request: FaceRegisterRequest
):
    """
    회원가입 때 촬영한 면허증 이미지에서
    얼굴 embedding을 추출해 저장한다.
    """
    result = face_service.register_face(
        request.user_id,
        request.image
    )

    return {
        "status": (
            "success"
            if result["registered"]
            else "error"
        ),
        "data": result,
        "message": (
            "면허증 얼굴 등록이 완료되었습니다."
            if result["registered"]
            else "면허증에서 얼굴을 인식하지 못했습니다."
        )
    }


@router.post("/face/verify")
def verify_face(
    request: FaceVerifyRequest
):
    """
    현재 셀피와 저장된 면허증 얼굴을 비교한다.
    """
    result = face_service.verify_face(
        request.user_id,
        request.image
    )

    if result["match"]:
        SessionManager.update_face_score(
            result["confidence"]
        )
        result["safety_check_started"] = safety_service.authentication_completed(
            request.user_id
        )

    return {
        "status": (
            "success"
            if result["match"]
            else "error"
        ),
        "data": result,
        "message": (
            "얼굴 인증이 완료되었습니다."
            if result["match"]
            else "얼굴 인증에 실패했습니다."
        )
    }

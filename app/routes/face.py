import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from app.services import face_service
from app.managers.session_manager import SessionManager
from app.services.safety_service import safety_service
from app.services.face_attempt_service import face_attempt_service
from app.services.helmet_service import helmet_service


router = APIRouter()
logger = logging.getLogger("uvicorn.error")


class FaceRegisterRequest(BaseModel):
    user_id: int
    image: str


class FaceVerifyRequest(BaseModel):
    user_id: int
    image: str

class FaceDetectRequest(BaseModel):
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
    attempt_status = face_attempt_service.get_status(request.user_id)
    if not attempt_status.allowed:
        return {
            "status": "error",
            "data": {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "retry_limit_exceeded",
                **attempt_status.to_dict(),
            },
            "message": "얼굴 인증 재시도 제한에 도달했습니다. 잠시 후 다시 시도하세요."
        }

    result = face_service.verify_face(
        request.user_id,
        request.image
    )
    logger.info(
        "Face verification user_id=%s score=%.2f%% threshold=%.2f%% passed=%s reason=%s",
        request.user_id,
        result["confidence"] * 100,
        face_service.REGISTERED_MATCH_THRESHOLD * 100,
        result["match"],
        result["reason"],
    )

    if result["match"]:
        face_attempt_service.reset(request.user_id)
        SessionManager.update_face_score(
            result["confidence"]
        )
        result["safety_check_started"] = safety_service.authentication_completed(
            request.user_id
        )
        result.update(face_attempt_service.get_status(request.user_id).to_dict())
    else:
        result.update(
            face_attempt_service.record_failure(request.user_id).to_dict()
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


@router.post("/face/live-verify")
def live_verify_face(request: FaceVerifyRequest, response: Response):
    """Verify face and helmet from one frame without recording retry failures."""
    image = face_service.face_service.decode_base64_image(request.image)
    if image is None:
        face_result = {
            "match": False,
            "confidence": 0.0,
            "reason": "invalid_image",
        }
        helmet_result = {
            "helmet_verified": False,
            "helmet_score": 0.0,
            "helmet_class": None,
            "reason": "invalid_image",
            "helmet_ok": False,
            "detected_class": None,
            "confidence": None,
            "helmet_bbox": None,
            "without_helmet_score": 0.0,
        }
    else:
        face_result = face_service.face_service.verify_face_image(request.user_id, image)
        helmet_result = helmet_service.verify_image(image)

    face_verified = face_result["match"]
    helmet_verified = helmet_result["helmet_verified"]
    verified = face_verified and helmet_verified
    safety_check_started = False

    helmet_threshold = helmet_service.confidence_threshold()
    logger.info("[LIVE] ========== verification ==========")
    logger.info("[LIVE] user_id=%s", request.user_id)
    logger.info("[LIVE] face_score=%.2f%%", face_result["confidence"] * 100)
    logger.info("[LIVE] face_threshold=%.2f%%", face_service.REGISTERED_MATCH_THRESHOLD * 100)
    logger.info("[LIVE] face_passed=%s", face_verified)
    logger.info("[LIVE] face_reason=%s", face_result["reason"])
    logger.info("[LIVE] helmet_score=%.2f%%", helmet_result["helmet_score"] * 100)
    logger.info("[LIVE] without_helmet_score=%.2f%%", helmet_result["without_helmet_score"] * 100)
    logger.info("[LIVE] helmet_threshold=%.2f%%", helmet_threshold * 100)
    logger.info("[LIVE] without_helmet_max=%.2f%%", helmet_service.without_helmet_max_confidence() * 100)
    logger.info("[LIVE] helmet_passed=%s", helmet_verified)
    logger.info("[LIVE] helmet_reason=%s", helmet_result["reason"])
    logger.info("[LIVE] verified=%s", verified)
    logger.info("[LIVE] ==================================")

    SessionManager.update_helmet_status(
        helmet_verified,
        helmet_result["helmet_score"],
    )
    if verified:
        face_attempt_service.reset(request.user_id)
        SessionManager.update_face_score(face_result["confidence"])
        safety_check_started = safety_service.authentication_completed(request.user_id)

    return {
        "status": "success" if verified else "error",
        "data": {
            "verified": verified,
            "face_verified": face_verified,
            "face_score": face_result["confidence"],
            "helmet_verified": helmet_verified,
            "helmet_score": helmet_result["helmet_score"],
            "helmet_class": helmet_result["helmet_class"],
            "helmet_ok": helmet_result["helmet_ok"],
            "detected_class": helmet_result["detected_class"],
            "confidence": helmet_result["confidence"],
            "helmet_bbox": helmet_result["helmet_bbox"],
            "without_helmet_score": helmet_result["without_helmet_score"],
            "face_reason": face_result["reason"],
            "helmet_reason": helmet_result["reason"],
            "safety_check_started": safety_check_started,
        },
        "message": (
            "얼굴 및 헬멧 인증이 완료되었습니다."
            if verified
            else "얼굴 또는 헬멧 인증에 실패했습니다."
        ),
    }


@router.post("/face/detect")
def detect_face(
    request: FaceDetectRequest
):
    """
    회원가입 전에 면허증 이미지에서
    얼굴 검출 가능 여부만 확인한다.
    """

    result = face_service.detect_face(
        request.image
    )

    reason_messages = {
        "success":
            "면허증에서 얼굴을 검출했습니다.",
        "face_not_detected":
            "면허증에서 얼굴을 인식하지 못했습니다.",
        "invalid_image":
            "면허증 이미지가 올바르지 않습니다."
    }

    return {
        "status": (
            "success"
            if result["detected"]
            else "error"
        ),
        "data": result,
        "message": reason_messages.get(
            result["reason"],
            "면허증 얼굴 검출에 실패했습니다."
        )
    }


@router.delete("/face/embedding/{user_id}")
def delete_face_embedding(
    user_id: int,
    x_internal_api_key: str | None = Header(default=None),
):
    """Delete a user's biometric template after a backend account deletion."""
    expected_key = os.getenv("INTERNAL_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="INTERNAL_API_KEY is not configured",
        )
    if x_internal_api_key is None or not hmac.compare_digest(
        x_internal_api_key,
        expected_key,
    ):
        raise HTTPException(status_code=401, detail="Invalid internal API key")

    result = face_service.delete_face(user_id)
    face_attempt_service.reset(user_id)
    return {
        "status": "success",
        "data": result,
        "message": (
            "얼굴 임베딩을 삭제했습니다."
            if result["deleted"]
            else "저장된 얼굴 임베딩이 없습니다."
        ),
    }

import base64
import os
import threading

import cv2
import numpy as np

from app.services.embedding_store import embedding_store

FACE_MODEL_NAME = "buffalo_sc"
FACE_PROVIDER = ["CPUExecutionProvider"]
FACE_DET_SIZE = (320, 320)

REGISTERED_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.5"))


def get_license_embedding_path(user_id: int):
    return str(embedding_store.path_for(user_id))


class FaceService:
    def __init__(self):
        self._app = None
        self._model_lock = threading.Lock()

    def _get_app(self):
        if self._app is not None:
            return self._app
        with self._model_lock:
            if self._app is None:
                from insightface.app import FaceAnalysis

                app = FaceAnalysis(
                    name=FACE_MODEL_NAME,
                    providers=FACE_PROVIDER,
                )
                app.prepare(ctx_id=0, det_size=FACE_DET_SIZE)
                self._app = app
        return self._app

    def get_license_embedding_path(self, user_id: int):
        """
        사용자별 면허증 얼굴 embedding 저장 경로를 반환한다.

        예:
        db/users/1/license_embedding.npy
        """
        return get_license_embedding_path(user_id)

    def decode_base64_image(self, image_base64: str):
        """
        Base64 문자열을 OpenCV 이미지로 변환한다.
        잘못된 Base64이면 None을 반환한다.
        """
        try:
            if not image_base64:
                return None

            if "," in image_base64:
                image_base64 = image_base64.split(",", 1)[1]

            image_bytes = base64.b64decode(
                image_base64,
                validate=True
            )

            np_arr = np.frombuffer(
                image_bytes,
                np.uint8
            )

            return cv2.imdecode(
                np_arr,
                cv2.IMREAD_COLOR
            )

        except Exception as error:
            print(f"[FACE] 이미지 디코딩 실패: {error}")
            return None

    def cosine_similarity(self, a, b):
        """
        두 얼굴 embedding의 코사인 유사도를 계산한다.
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(
            np.dot(a, b) /
            (norm_a * norm_b)
        )

    def extract_embedding(self, img):
        """
        이미지에서 얼굴을 검출하고 embedding을 반환한다.

        얼굴이 여러 명이면 가장 큰 얼굴을 사용한다.
        얼굴을 찾지 못하면 None을 반환한다.
        """
        if img is None:
            return None

        faces = self._get_app().get(img)

        if len(faces) == 0:
            return None

        face = max(
            faces,
            key=lambda f: (
                (f.bbox[2] - f.bbox[0]) *
                (f.bbox[3] - f.bbox[1])
            )
        )

        return face.embedding

    def register_face(
        self,
        user_id: int,
        image_base64: str
    ):
        """
        면허증 이미지에서 얼굴 embedding을 추출하고
        사용자별 파일로 저장한다.
        """
        img = self.decode_base64_image(
            image_base64
        )

        if img is None:
            return {
                "registered": False,
                "user_id": user_id,
                "reason": "invalid_image"
            }

        embedding = self.extract_embedding(img)

        if embedding is None:
            return {
                "registered": False,
                "user_id": user_id,
                "reason": "face_not_detected"
            }

        embedding_path = embedding_store.save(user_id, embedding)

        print("[FACE] 면허증 얼굴 embedding 저장 완료")
        print(f"[FACE] user_id: {user_id}")
        print(f"[FACE] 경로: {embedding_path}")

        return {
            "registered": True,
            "user_id": user_id,
            "reason": "success"
        }

    def verify_face(
        self,
        user_id: int,
        image_base64: str
    ):
        """
        현재 셀피와 사용자의 면허증 얼굴 embedding을 비교한다.
        """
        registered_embedding = embedding_store.load(user_id)

        if registered_embedding is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "license_embedding_not_found"
            }

        img = self.decode_base64_image(
            image_base64
        )

        if img is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "invalid_image"
            }

        current_embedding = (
            self.extract_embedding(img)
        )

        if current_embedding is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "face_not_detected"
            }

        similarity = self.cosine_similarity(
            registered_embedding,
            current_embedding
        )

        match = (
            similarity >=
            REGISTERED_MATCH_THRESHOLD
        )

        return {
            "match": match,
            "confidence": similarity,
            "face_vector": current_embedding.tolist(),
            "reason": (
                "success"
                if match
                else "not_matched"
            )
        }
    def detect_face(self, image_base64: str):
        """
        이미지에 얼굴이 존재하는지만 확인한다.

        이 단계에서는 임베딩 파일을 저장하지 않는다.
        """

        img = self.decode_base64_image(
            image_base64
        )

        if img is None:
            return {
                "detected": False,
                "reason": "invalid_image"
            }

        embedding = self.extract_embedding(img)

        if embedding is None:
            return {
                "detected": False,
                "reason": "face_not_detected"
            }

        return {
            "detected": True,
            "reason": "success"
        }

    def delete_face(self, user_id: int):
        return {
            "deleted": embedding_store.delete(user_id),
            "user_id": user_id,
            "reason": "success",
        }


face_service = FaceService()


def register_face(
    user_id: int,
    image_base64: str
):
    return face_service.register_face(
        user_id,
        image_base64
    )


def verify_face(
    user_id: int,
    image_base64: str
):
    return face_service.verify_face(
        user_id,
        image_base64
    )

def detect_face(image_base64: str):
    return face_service.detect_face(
        image_base64
    )


def delete_face(user_id: int):
    return face_service.delete_face(user_id)

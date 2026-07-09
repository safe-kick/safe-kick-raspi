import os
import base64
import cv2
import numpy as np

from insightface.app import FaceAnalysis

FACE_MODEL_NAME = "buffalo_sc"
FACE_PROVIDER = ["CPUExecutionProvider"]
FACE_DET_SIZE = (320, 320)

REGISTERED_MATCH_THRESHOLD = 0.4


def get_license_embedding_path(user_id: int):
    return f"db/users/{user_id}/license_embedding.npy"


class FaceService:
    def __init__(self):
        self.app = FaceAnalysis(
            name=FACE_MODEL_NAME,
            providers=FACE_PROVIDER
        )

        self.app.prepare(
            ctx_id=0,
            det_size=FACE_DET_SIZE
        )

    def decode_base64_image(self, image_base64: str):
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]

        image_bytes = base64.b64decode(image_base64)
        np_arr = np.frombuffer(image_bytes, np.uint8)

        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    def cosine_similarity(self, a, b):
        return float(
            np.dot(a, b) /
            (np.linalg.norm(a) * np.linalg.norm(b))
        )

    def extract_embedding(self, img):
        faces = self.app.get(img)

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

    def register_face(self, user_id: int, image_base64: str):
        """
        면허증 이미지에서 얼굴을 검출하고,
        사용자별 license_embedding.npy로 저장한다.
        """
        img = self.decode_base64_image(image_base64)

        if img is None:
            return {
                "registered": False,
                "reason": "invalid_image"
            }

        embedding = self.extract_embedding(img)

        if embedding is None:
            return {
                "registered": False,
                "reason": "face_not_detected"
            }

        embedding_path = get_license_embedding_path(user_id)

        os.makedirs(
            os.path.dirname(embedding_path),
            exist_ok=True
        )

        np.save(
            embedding_path,
            embedding
        )

        print("[FACE] 면허증 얼굴 embedding 저장 완료")
        print(f"[FACE] user_id: {user_id}")
        print(f"[FACE] 경로: {embedding_path}")

        return {
            "registered": True,
            "user_id": user_id,
            "reason": "success"
        }

    def verify_face(self, user_id: int, image_base64: str):
        """
        현재 셀피 얼굴과 해당 사용자의 면허증 얼굴 embedding을 비교한다.
        """
        embedding_path = get_license_embedding_path(user_id)

        if not os.path.exists(embedding_path):
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "license_embedding_not_found"
            }

        license_embedding = np.load(embedding_path)

        img = self.decode_base64_image(image_base64)

        if img is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "invalid_image"
            }

        selfie_embedding = self.extract_embedding(img)

        if selfie_embedding is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "face_not_detected"
            }

        similarity = self.cosine_similarity(
            license_embedding,
            selfie_embedding
        )

        match = similarity >= REGISTERED_MATCH_THRESHOLD

        return {
            "match": match,
            "confidence": similarity,
            "face_vector": selfie_embedding.tolist(),
            "reason": "success" if match else "not_matched"
        }


face_service = FaceService()


def register_face(user_id: int, image_base64: str):
    return face_service.register_face(user_id, image_base64)


def verify_face(user_id: int, image_base64: str):
    return face_service.verify_face(user_id, image_base64)
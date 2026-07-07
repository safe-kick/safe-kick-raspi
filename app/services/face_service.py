import base64
import cv2
import numpy as np

from insightface.app import FaceAnalysis

REGISTERED_EMBEDDING_PATH = "db/known_embedding.npy"

FACE_MODEL_NAME = "buffalo_sc"
FACE_PROVIDER = ["CPUExecutionProvider"]
FACE_DET_SIZE = (320, 320)

REGISTERED_MATCH_THRESHOLD = 0.5


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

        self.registered_embedding = self.load_registered_embedding()

    def load_registered_embedding(self):
        try:
            embedding = np.load(REGISTERED_EMBEDDING_PATH)
            print("[FACE] 등록 운전자 embedding 로드 완료")
            return embedding
        except FileNotFoundError:
            print("[FACE] 등록 운전자 embedding 파일 없음")
            return None

    def decode_base64_image(self, image_base64: str):
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]

        image_bytes = base64.b64decode(image_base64)
        np_arr = np.frombuffer(image_bytes, np.uint8)

        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        return img

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

    def verify_face(self, image_base64: str):
        if self.registered_embedding is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "registered_embedding_not_found"
            }

        img = self.decode_base64_image(image_base64)

        if img is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "invalid_image"
            }

        embedding = self.extract_embedding(img)

        if embedding is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_vector": [],
                "reason": "face_not_detected"
            }

        similarity = self.cosine_similarity(
            self.registered_embedding,
            embedding
        )

        match = similarity >= REGISTERED_MATCH_THRESHOLD

        return {
            "match": match,
            "confidence": similarity,
            "face_vector": embedding.tolist(),
            "reason": "success" if match else "not_matched"
        }


face_service = FaceService()


def verify_face(image_base64: str):
    return face_service.verify_face(image_base64)
def verify_face(image_base64: str):
    if not image_base64:
        return {
            "match": False,
            "confidence": 0.0,
            "face_vector": []
        }

    return {
        "match": True,
        "confidence": 0.92,
        "face_vector": [0.123, -0.456, 0.789]
    }
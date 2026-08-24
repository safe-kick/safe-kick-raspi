from __future__ import annotations

import logging
import os
from typing import Any, Callable


DEFAULT_MODEL_ID = "bike-helmet-detection-2vdjo-mqa2s/1"
DEFAULT_API_URL = "https://detect.roboflow.com"


class HelmetService:
    """Verify bicycle helmet use through Roboflow Hosted Inference."""

    def __init__(self, client_factory: Callable[..., Any] | None = None) -> None:
        self._client_factory = client_factory
        self._logger = logging.getLogger(__name__)

    def verify_image(self, image) -> dict:
        if image is None:
            return self._failure("invalid_image")
        api_key = os.getenv("ROBOFLOW_API_KEY", "").strip()
        if not api_key:
            return self._failure("api_key_not_configured")

        model_id = os.getenv("ROBOFLOW_HELMET_MODEL_ID", DEFAULT_MODEL_ID)
        try:
            threshold = float(os.getenv("HELMET_CONFIDENCE_THRESHOLD", "0.50"))
            client = self._make_client(api_key)
            response = client.infer(image, model_id=model_id)
            return self._parse_response(response, threshold)
        except Exception as error:
            self._logger.warning("Roboflow helmet inference failed: %s", error)
            return self._failure("inference_error")

    def _make_client(self, api_key: str):
        if self._client_factory is not None:
            return self._client_factory(api_key=api_key, api_url=DEFAULT_API_URL)
        from inference_sdk import InferenceHTTPClient

        return InferenceHTTPClient(api_url=DEFAULT_API_URL, api_key=api_key)

    def _parse_response(self, response: Any, threshold: float) -> dict:
        if hasattr(response, "model_dump"):
            response = response.model_dump()
        elif hasattr(response, "dict"):
            response = response.dict()
        if not isinstance(response, dict):
            return self._failure("invalid_response")

        predictions = response.get("predictions", [])
        if isinstance(predictions, dict):
            predictions = predictions.get("predictions", [])
        if not isinstance(predictions, list) or not predictions:
            return self._failure("no_predictions")

        normalized = []
        for prediction in predictions:
            if hasattr(prediction, "model_dump"):
                prediction = prediction.model_dump()
            elif hasattr(prediction, "dict"):
                prediction = prediction.dict()
            if not isinstance(prediction, dict):
                continue
            label = prediction.get("class") or prediction.get("class_name")
            try:
                confidence = float(prediction.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue
            normalized.append((label, confidence))

        without_helmet = [item for item in normalized if item[0] == "Without Helmet"]
        with_helmet = [item for item in normalized if item[0] == "With Helmet"]
        if without_helmet:
            label, score = max(without_helmet, key=lambda item: item[1])
            return self._failure("without_helmet_detected", score, label)
        if not with_helmet:
            return self._failure("helmet_not_detected")

        label, score = max(with_helmet, key=lambda item: item[1])
        verified = score >= threshold
        return {
            "helmet_verified": verified,
            "helmet_score": score,
            "helmet_class": label,
            "reason": "success" if verified else "confidence_below_threshold",
        }

    @staticmethod
    def _failure(reason: str, score: float = 0.0, label: str | None = None) -> dict:
        return {
            "helmet_verified": False,
            "helmet_score": score,
            "helmet_class": label,
            "reason": reason,
        }


helmet_service = HelmetService()

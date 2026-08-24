from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Any, Callable

DEFAULT_MODEL_ID = "helmet-srsz5/2"
DEFAULT_API_URL = "https://serverless.roboflow.com"
HELMET_CLASS = "With Helmet"
WITHOUT_HELMET_CLASS = "Without Helmet"


class HelmetService:
    """Verify bicycle helmet use through Roboflow Serverless Inference."""

    def __init__(self, client_factory: Callable[..., Any] | None = None) -> None:
        self._client_factory = client_factory
        self._logger = logging.getLogger("uvicorn.error")
        self._inference_lock = threading.Lock()

    @staticmethod
    def confidence_threshold() -> float:
        return float(os.getenv("HELMET_WITH_CONFIDENCE", os.getenv("HELMET_CONFIDENCE", "0.90")))

    @staticmethod
    def without_helmet_max_confidence() -> float:
        return float(os.getenv("HELMET_WITHOUT_MAX_CONFIDENCE", "0.50"))

    def verify_image(self, image) -> dict:
        if image is None:
            return self._failure("invalid_image")
        api_key = os.getenv("ROBOFLOW_API_KEY", "").strip()
        if not api_key:
            self._logger.error("[HELMET] API key is not configured; FAIL")
            return self._failure("api_key_not_configured")

        model_id = os.getenv("ROBOFLOW_HELMET_MODEL_ID", DEFAULT_MODEL_ID).strip()
        timeout = float(os.getenv("HELMET_INFERENCE_TIMEOUT_SECONDS", "30"))
        self._logger.info("[HELMET] ---------- frame start ----------")
        self._logger.info("[HELMET] model_id=%s", model_id)
        try:
            client = self._make_client(api_key)
            response = self._infer_with_timeout(client, image, model_id, timeout)
            return self._parse_response(
                response,
                self.confidence_threshold(),
                self.without_helmet_max_confidence(),
            )
        except TimeoutError:
            self._logger.error("[HELMET] Roboflow inference timeout; FAIL")
            return self._failure("inference_timeout")
        except Exception as error:
            self._logger.error("[HELMET] Roboflow inference failed: %s; FAIL", error)
            return self._failure("inference_error")

    def _make_client(self, api_key: str):
        if self._client_factory is not None:
            return self._client_factory(api_key=api_key, api_url=DEFAULT_API_URL)
        from inference_sdk import InferenceHTTPClient

        return InferenceHTTPClient(api_url=DEFAULT_API_URL, api_key=api_key)

    def _infer_with_timeout(self, client, image, model_id: str, timeout: float):
        if timeout <= 0:
            raise ValueError("HELMET_INFERENCE_TIMEOUT_SECONDS must be positive")
        if not self._inference_lock.acquire(blocking=False):
            raise RuntimeError("another helmet inference is still running")
        result_queue: queue.Queue = queue.Queue(maxsize=1)

        def run_inference() -> None:
            try:
                result_queue.put((True, client.infer(image, model_id=model_id)))
            except BaseException as error:
                result_queue.put((False, error))
            finally:
                self._inference_lock.release()

        threading.Thread(target=run_inference, daemon=True).start()
        try:
            succeeded, result = result_queue.get(timeout=timeout)
        except queue.Empty as error:
            raise TimeoutError from error
        if not succeeded:
            raise result
        return result

    def _parse_response(self, response: Any, with_threshold: float, without_max: float) -> dict:
        if hasattr(response, "model_dump"):
            response = response.model_dump()
        elif hasattr(response, "dict"):
            response = response.dict()
        if not isinstance(response, dict):
            return self._logged_failure("invalid_response", "invalid response")

        predictions = response.get("predictions", [])
        if isinstance(predictions, dict):
            predictions = predictions.get("predictions", [])
        if not isinstance(predictions, list) or not predictions:
            return self._logged_failure("no_predictions", "no helmet classification detected")

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
            self._logger.info("[HELMET] prediction class=%s confidence=%.4f", label, confidence)
            normalized.append((label, confidence, prediction))

        without_helmet = [item for item in normalized if item[0] == WITHOUT_HELMET_CLASS]
        with_helmet = [item for item in normalized if item[0] == HELMET_CLASS]
        best_without = max(without_helmet, key=lambda item: item[1], default=None)
        without_score = best_without[1] if best_without is not None else 0.0
        if not with_helmet:
            result = self._logged_failure("helmet_not_detected", "With Helmet not detected")
            result["without_helmet_score"] = without_score
            return result

        label, score, prediction = max(with_helmet, key=lambda item: item[1])
        with_passed = score >= with_threshold
        without_passed = without_score <= without_max
        verified = with_passed and without_passed
        reason = "success"
        if not without_passed:
            reason = "without_helmet_detected"
        elif not with_passed:
            reason = "confidence_below_threshold"

        self._logger.info("[HELMET] With Helmet confidence=%.4f", score)
        self._logger.info("[HELMET] With Helmet threshold_min=%.4f", with_threshold)
        self._logger.info("[HELMET] With Helmet passed=%s", with_passed)
        self._logger.info("[HELMET] Without Helmet confidence=%.4f", without_score)
        self._logger.info("[HELMET] Without Helmet threshold_max=%.4f", without_max)
        self._logger.info("[HELMET] Without Helmet passed=%s", without_passed)
        self._logger.info("[HELMET] result=%s", "PASS" if verified else f"FAIL ({reason})")
        self._logger.info("[HELMET] ----------- frame end -----------")
        result = self._result(verified, reason, score, label, prediction)
        result["without_helmet_score"] = without_score
        return result

    def _logged_failure(self, reason: str, message: str) -> dict:
        self._logger.info("[HELMET] %s", message)
        self._logger.info("[HELMET] FAIL")
        return self._failure(reason)

    @classmethod
    def _failure(cls, reason: str, score: float = 0.0, label: str | None = None, prediction: dict | None = None) -> dict:
        return cls._result(False, reason, score, label, prediction)

    @staticmethod
    def _result(verified: bool, reason: str, score: float, label: str | None, prediction: dict | None) -> dict:
        bbox = None
        if prediction is not None:
            bbox = {key: prediction[key] for key in ("x", "y", "width", "height") if key in prediction} or None
        return {
            "helmet_verified": verified,
            "helmet_score": score,
            "helmet_class": label,
            "reason": reason,
            "helmet_ok": verified,
            "detected_class": label,
            "confidence": score if label is not None else None,
            "helmet_bbox": bbox,
            "without_helmet_score": 0.0,
        }


helmet_service = HelmetService()

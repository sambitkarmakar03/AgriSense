"""Compatibility wrapper for callers of the original Phase 1 disease stub."""

from app.ml.inference import get_inference_service


def predict_disease(image_bytes: bytes) -> dict[str, object]:
    """Return the raw class prediction and probabilities from the ONNX model."""
    return get_inference_service().predict(image_bytes).as_dict()

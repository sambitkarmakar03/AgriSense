"""Extension point for the future ONNX disease-inference service.

Disease classification, image handling, heatmaps, and diagnosis endpoints are intentionally
not implemented in this backend phase. This module keeps the future integration boundary
explicit without importing a machine-learning runtime into the API service.
"""


class DiseaseInferenceNotConfigured(RuntimeError):
    """Raised if a future caller attempts inference before the ML phase is implemented."""


def predict_disease(_image_bytes: bytes) -> dict[str, object]:
    raise DiseaseInferenceNotConfigured("Disease inference will be added in a later project phase.")

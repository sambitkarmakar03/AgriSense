"""CPU-only inference for the AgriSense four-class ONNX leaf classifier."""

from __future__ import annotations

import io
import json
import os
import threading
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

EXPECTED_CLASS_ORDER = ("Leaf Blight", "Rust", "Powdery Mildew", "Healthy")
IMAGE_SIZE = 224
MAX_IMAGE_PIXELS = 40_000_000
MAX_BATCH_SIZE = 32
IMAGENET_MEAN = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
IMAGENET_STD = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)


class InferenceError(RuntimeError):
    """Base error for model loading, metadata, and execution failures."""


class ModelUnavailableError(InferenceError):
    """The model, labels, or ONNX Runtime installation is unavailable."""


class ModelMetadataError(InferenceError):
    """The model graph and labels metadata do not describe the same contract."""


class ModelExecutionError(InferenceError):
    """ONNX Runtime failed to execute the model or returned invalid output."""


class InvalidImageError(ValueError):
    """Uploaded image bytes are empty, corrupt, unsupported, or too large."""


@dataclass(frozen=True)
class InferenceResult:
    predicted_label: str
    confidence: float
    probabilities: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "predicted_label": self.predicted_label,
            "confidence": self.confidence,
            "probabilities": dict(self.probabilities),
        }


def _parse_input_size(raw_value: str | None) -> bool:
    if raw_value is None:
        return False
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value
    return value in (IMAGE_SIZE, str(IMAGE_SIZE), [IMAGE_SIZE, IMAGE_SIZE])


class DiseaseInferenceService:
    """Loads one ONNX model and reuses its CPU session for all predictions."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        labels_path: str | Path | None = None,
        *,
        session: Any | None = None,
    ) -> None:
        module_dir = Path(__file__).resolve().parent
        self.model_path = Path(model_path) if model_path is not None else module_dir / "model.onnx"
        self.labels_path = Path(labels_path) if labels_path is not None else module_dir / "labels.json"
        self.model_path = self.model_path.expanduser().resolve()
        self.labels_path = self.labels_path.expanduser().resolve()

        if not self.labels_path.is_file():
            raise ModelUnavailableError(f"Model labels file is missing: {self.labels_path}")
        try:
            self.labels = json.loads(self.labels_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelMetadataError("Model labels file is not valid UTF-8 JSON.") from exc
        self.class_order = self._validate_labels(self.labels)

        if session is None:
            if not self.model_path.is_file():
                raise ModelUnavailableError(f"ONNX model file is missing: {self.model_path}")
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise ModelUnavailableError(
                    "ONNX Runtime is not installed. Install backend/requirements.txt before inference."
                ) from exc
            options = ort.SessionOptions()
            options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
            options.inter_op_num_threads = 1
            try:
                session = ort.InferenceSession(
                    str(self.model_path),
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
            except Exception as exc:
                raise ModelUnavailableError("ONNX Runtime could not load the disease model.") from exc
        self._session = session
        self.model_metadata = self._validate_session(session)

    @staticmethod
    def _normalization_matches(actual: Any, expected: np.ndarray) -> bool:
        try:
            values = np.asarray(actual, dtype=np.float32)
        except (TypeError, ValueError):
            return False
        return values.shape == expected.shape and bool(np.allclose(values, expected, rtol=0, atol=1e-7))

    @staticmethod
    def _validate_labels(labels: Any) -> tuple[str, ...]:
        if not isinstance(labels, dict):
            raise ModelMetadataError("Model labels must be a JSON object.")
        order = labels.get("class_order")
        if not isinstance(order, list) or tuple(order) != EXPECTED_CLASS_ORDER:
            raise ModelMetadataError("labels.json class_order does not match the four supported model outputs.")

        classes = labels.get("classes")
        if not isinstance(classes, list) or len(classes) != len(EXPECTED_CLASS_ORDER):
            raise ModelMetadataError("labels.json must describe each of the four output classes.")
        for index, (entry, expected_label) in enumerate(zip(classes, EXPECTED_CLASS_ORDER)):
            if not isinstance(entry, dict) or entry.get("index") != index or entry.get("label") != expected_label:
                raise ModelMetadataError("labels.json class indices do not match class_order.")

        input_info = labels.get("input")
        output_info = labels.get("output")
        if not isinstance(input_info, dict) or not isinstance(output_info, dict):
            raise ModelMetadataError("labels.json must describe model input and output tensors.")
        if (
            input_info.get("name") != "images"
            or input_info.get("layout") != "NCHW"
            or input_info.get("color") != "RGB"
            or input_info.get("size") != [IMAGE_SIZE, IMAGE_SIZE]
            or input_info.get("dtype") != "float32"
        ):
            raise ModelMetadataError("labels.json input contract does not match RGB NCHW float32 224x224.")
        normalization = input_info.get("normalization")
        if not isinstance(normalization, dict):
            raise ModelMetadataError("labels.json is missing ImageNet input normalization values.")
        if not DiseaseInferenceService._normalization_matches(normalization.get("mean"), IMAGENET_MEAN):
            raise ModelMetadataError("labels.json ImageNet mean is not the expected value.")
        if not DiseaseInferenceService._normalization_matches(normalization.get("std"), IMAGENET_STD):
            raise ModelMetadataError("labels.json ImageNet standard deviation is not the expected value.")
        if output_info.get("name") != "probabilities" or output_info.get("type") != "softmax probabilities":
            raise ModelMetadataError("labels.json output contract must identify softmax probabilities.")
        return tuple(order)

    def _validate_session(self, session: Any) -> dict[str, str]:
        try:
            providers = session.get_providers()
            metadata = dict(session.get_modelmeta().custom_metadata_map)
            inputs = session.get_inputs()
            outputs = session.get_outputs()
        except Exception as exc:
            raise ModelMetadataError("ONNX Runtime did not expose model metadata and tensor information.") from exc

        if providers != ["CPUExecutionProvider"]:
            raise ModelMetadataError(f"Expected CPUExecutionProvider only; active providers are {providers}.")
        try:
            model_order = json.loads(metadata.get("agrisense.class_order", ""))
        except json.JSONDecodeError as exc:
            raise ModelMetadataError("ONNX metadata has no valid agrisense.class_order.") from exc
        if model_order != list(self.class_order):
            raise ModelMetadataError("ONNX agrisense.class_order does not match labels.json.")
        if not _parse_input_size(metadata.get("agrisense.input_size")):
            raise ModelMetadataError("ONNX agrisense.input_size metadata must be 224.")
        if metadata.get("agrisense.output") != "softmax probabilities":
            raise ModelMetadataError("ONNX agrisense.output metadata must identify softmax probabilities.")

        if len(inputs) != 1 or len(outputs) != 1:
            raise ModelMetadataError("The disease ONNX graph must have exactly one input and one output.")
        model_input, model_output = inputs[0], outputs[0]
        if model_input.name != "images" or model_input.type != "tensor(float)":
            raise ModelMetadataError("ONNX input must be float32 tensor named 'images'.")
        if model_output.name != "probabilities" or model_output.type != "tensor(float)":
            raise ModelMetadataError("ONNX output must be float32 tensor named 'probabilities'.")
        input_shape = list(model_input.shape)
        output_shape = list(model_output.shape)
        if (
            len(input_shape) != 4
            or isinstance(input_shape[0], int)
            or input_shape[1:] != [3, IMAGE_SIZE, IMAGE_SIZE]
        ):
            raise ModelMetadataError(f"ONNX input must have dynamic [batch, 3, 224, 224] shape; found {input_shape}.")
        if (
            len(output_shape) != 2
            or isinstance(output_shape[0], int)
            or output_shape[1] != len(self.class_order)
        ):
            raise ModelMetadataError(f"ONNX output must have dynamic [batch, 4] shape; found {output_shape}.")
        return metadata

    @staticmethod
    def _decode_rgb(image_bytes: bytes | bytearray | memoryview) -> Image.Image:
        if not isinstance(image_bytes, (bytes, bytearray, memoryview)) or not image_bytes:
            raise InvalidImageError("Image data must be non-empty bytes.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(bytes(image_bytes))) as source:
                    if source.width <= 0 or source.height <= 0 or source.width * source.height > MAX_IMAGE_PIXELS:
                        raise InvalidImageError("Image dimensions exceed the supported limit.")
                    source.load()
                    image = ImageOps.exif_transpose(source).convert("RGB")
            return image
        except InvalidImageError:
            raise
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            SyntaxError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise InvalidImageError("Uploaded file is not a readable image.") from exc

    @classmethod
    def preprocess_image(cls, image_bytes: bytes | bytearray | memoryview) -> np.ndarray:
        """Convert one image to normalized CHW float32 using the training preprocessing."""
        image = cls._decode_rgb(image_bytes)
        resized = image.resize((IMAGE_SIZE, IMAGE_SIZE), resample=Image.Resampling.BILINEAR)
        array = np.asarray(resized, dtype=np.float32) / np.float32(255.0)
        array = (array - IMAGENET_MEAN) / IMAGENET_STD
        return np.ascontiguousarray(array.transpose(2, 0, 1), dtype=np.float32)

    @classmethod
    def make_thumbnail(cls, image_bytes: bytes | bytearray | memoryview) -> bytes:
        """Create a small re-encoded JPEG without carrying through EXIF metadata."""
        image = cls._decode_rgb(image_bytes).resize(
            (IMAGE_SIZE, IMAGE_SIZE), resample=Image.Resampling.BILINEAR
        )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82, optimize=True)
        return buffer.getvalue()

    def predict(self, image_bytes: bytes | bytearray | memoryview) -> InferenceResult:
        return self.predict_batch([image_bytes])[0]

    def predict_batch(
        self,
        images: Sequence[bytes | bytearray | memoryview] | bytes | bytearray | memoryview,
    ) -> list[InferenceResult]:
        """Run a batch of images; one corrupt input rejects the whole batch."""
        if isinstance(images, (bytes, bytearray, memoryview)):
            image_items = [images]
        elif isinstance(images, Sequence) and not isinstance(images, (str, bytes, bytearray)):
            image_items = list(images)
        else:
            raise InvalidImageError("Provide image bytes or a sequence of image byte strings.")
        if not image_items:
            raise InvalidImageError("At least one image is required.")
        if len(image_items) > MAX_BATCH_SIZE:
            raise InvalidImageError(f"A batch may contain at most {MAX_BATCH_SIZE} images.")

        batch = np.stack([self.preprocess_image(item) for item in image_items], axis=0).astype(np.float32, copy=False)
        try:
            output = self._session.run(["probabilities"], {"images": batch})[0]
        except Exception as exc:
            raise ModelExecutionError("ONNX Runtime failed to evaluate the image batch.") from exc
        probabilities = np.asarray(output, dtype=np.float32)
        expected_shape = (len(image_items), len(self.class_order))
        if probabilities.shape != expected_shape or not np.isfinite(probabilities).all():
            raise ModelExecutionError(f"Model output must be finite with shape {expected_shape}.")
        if np.any(probabilities < -1e-5) or np.any(probabilities > 1.00001):
            raise ModelExecutionError("Model output values are outside the probability range [0, 1].")
        if not np.allclose(probabilities.sum(axis=1), 1.0, rtol=0, atol=0.03):
            raise ModelExecutionError("Model output does not sum to softmax probabilities.")

        results: list[InferenceResult] = []
        for row in probabilities:
            class_index = int(row.argmax())
            distribution = {label: float(row[index]) for index, label in enumerate(self.class_order)}
            results.append(
                InferenceResult(
                    predicted_label=self.class_order[class_index],
                    confidence=float(row[class_index]),
                    probabilities=distribution,
                )
            )
        return results


_service: DiseaseInferenceService | None = None
_service_lock = threading.Lock()


def get_inference_service() -> DiseaseInferenceService:
    """Return a process-wide model session, loading it lazily on first use."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = DiseaseInferenceService()
    return _service

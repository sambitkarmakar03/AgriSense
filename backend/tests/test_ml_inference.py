import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import select

from app.api import diagnosis as diagnosis_api
from app.db.models import Diagnosis
from app.ml.inference import (
    EXPECTED_CLASS_ORDER,
    DiseaseInferenceService,
    InvalidImageError,
    ModelMetadataError,
)


MODEL_METADATA = {
    "agrisense.class_order": json.dumps(list(EXPECTED_CLASS_ORDER)),
    "agrisense.input_size": "224",
    "agrisense.output": "softmax probabilities",
}
MODEL_PROBABILITIES = np.asarray([[0.01, 0.93, 0.04, 0.02]], dtype=np.float32)


class _TensorInfo:
    def __init__(self, name, shape):
        self.name = name
        self.shape = shape
        self.type = "tensor(float)"


class FakeInferenceSession:
    def __init__(self, metadata=None, probabilities=MODEL_PROBABILITIES):
        self.metadata = metadata or MODEL_METADATA
        self.probabilities = probabilities
        self.run_calls = []

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def get_modelmeta(self):
        return type("Metadata", (), {"custom_metadata_map": self.metadata})()

    def get_inputs(self):
        return [_TensorInfo("images", ["batch_size", 3, 224, 224])]

    def get_outputs(self):
        return [_TensorInfo("probabilities", ["batch_size", 4])]

    def run(self, output_names, inputs):
        self.run_calls.append((output_names, inputs))
        return [np.repeat(self.probabilities, len(inputs["images"]), axis=0)]


def _image_bytes(mode="RGB", fmt="PNG"):
    image = Image.new(mode, (30, 19), color=128 if mode == "L" else (10, 120, 220, 80) if mode == "RGBA" else (10, 120, 220))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _service(session=None):
    labels_path = Path(__file__).resolve().parents[1] / "app" / "ml" / "labels.json"
    return DiseaseInferenceService(labels_path=labels_path, session=session or FakeInferenceSession())


def test_loaded_contract_and_grayscale_rgba_preprocessing():
    service = _service()
    assert service.class_order == EXPECTED_CLASS_ORDER
    for payload in (_image_bytes("L"), _image_bytes("RGBA")):
        tensor = service.preprocess_image(payload)
        assert tensor.shape == (3, 224, 224)
        assert tensor.dtype == np.float32
        assert np.isfinite(tensor).all()

    black = Image.new("RGB", (8, 8), color=(0, 0, 0))
    buffer = io.BytesIO()
    black.save(buffer, format="PNG")
    tensor = service.preprocess_image(buffer.getvalue())
    expected = -(np.asarray((0.485, 0.456, 0.406), dtype=np.float32)) / np.asarray(
        (0.229, 0.224, 0.225), dtype=np.float32
    )
    assert np.allclose(tensor[:, 0, 0], expected, atol=1e-6)


def test_prediction_returns_graph_probabilities_without_another_softmax_and_batches():
    session = FakeInferenceSession()
    service = _service(session)
    result = service.predict_batch([_image_bytes(), _image_bytes("L")])

    assert len(result) == 2
    assert result[0].predicted_label == "Rust"
    assert result[0].confidence == pytest.approx(0.93)
    assert result[0].probabilities == {
        "Leaf Blight": pytest.approx(0.01),
        "Rust": pytest.approx(0.93),
        "Powdery Mildew": pytest.approx(0.04),
        "Healthy": pytest.approx(0.02),
    }
    outputs, inputs = session.run_calls[0]
    assert outputs == ["probabilities"]
    assert inputs["images"].shape == (2, 3, 224, 224)
    # The model output remains the original softmax distribution, not softmax(log(probabilities)).
    assert np.allclose(np.asarray(list(result[0].probabilities.values())), MODEL_PROBABILITIES[0])


def test_corrupt_image_is_rejected_before_model_execution():
    session = FakeInferenceSession()
    with pytest.raises(InvalidImageError):
        _service(session).predict(b"not an image")
    assert session.run_calls == []


def test_thumbnail_reencoding_removes_exif_metadata():
    source = Image.new("RGB", (24, 24), color=(45, 80, 120))
    exif = source.getexif()
    exif[270] = "private image description"
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", exif=exif)

    thumbnail_bytes = _service().make_thumbnail(buffer.getvalue())
    with Image.open(io.BytesIO(thumbnail_bytes)) as thumbnail:
        assert thumbnail.format == "JPEG"
        assert thumbnail.size == (224, 224)
        assert not thumbnail.getexif()


def test_model_class_metadata_must_match_labels_file():
    wrong_metadata = dict(MODEL_METADATA)
    wrong_metadata["agrisense.class_order"] = json.dumps(list(reversed(EXPECTED_CLASS_ORDER)))
    with pytest.raises(ModelMetadataError, match="class_order"):
        _service(FakeInferenceSession(metadata=wrong_metadata))


def test_bundled_onnx_model_matches_metadata_and_returns_probabilities():
    service = DiseaseInferenceService()
    result = service.predict(_image_bytes("L"))
    assert service.class_order == EXPECTED_CLASS_ORDER
    assert service.model_metadata["agrisense.output"] == "softmax probabilities"
    assert tuple(result.probabilities) == EXPECTED_CLASS_ORDER
    assert result.predicted_label in EXPECTED_CLASS_ORDER
    assert result.confidence == pytest.approx(max(result.probabilities.values()))
    assert sum(result.probabilities.values()) == pytest.approx(1.0, abs=0.03)


def _register(client, email):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct-horse-123",
            "consent_accepted": True,
            "consent_text_version": "privacy-v1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_field(client, token):
    response = client.post(
        "/fields",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Leaf test plot", "crop": "Maize", "crop_stage": "Vegetative"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _install_fake_service(client, monkeypatch):
    service = _service()
    monkeypatch.setitem(client.app.dependency_overrides, diagnosis_api.require_disease_inference, lambda: service)
    monkeypatch.setattr(diagnosis_api, "diagnosis_upload_limiter", diagnosis_api.UploadRateLimiter(100, 60))
    return service


def test_diagnosis_endpoint_persists_owned_prediction_and_sanitized_thumbnail(client, database_session, monkeypatch):
    service = _install_fake_service(client, monkeypatch)
    owner = _register(client, "leaf-owner@example.test")
    field = _create_field(client, owner["access_token"])
    response = client.post(
        f"/fields/{field['id']}/diagnose",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        files={"file": ("leaf.png", _image_bytes(), "image/png")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["predicted_label"] == "Rust"
    assert body["confidence"] == pytest.approx(0.93)
    assert body["probabilities"]["Powdery Mildew"] == pytest.approx(0.04)
    row = database_session.scalar(select(Diagnosis).where(Diagnosis.id == body["diagnosis_id"]))
    assert row is not None
    assert row.field_id == field["id"]
    assert row.cnn_label == "Rust"
    assert row.cnn_probs_json["Rust"] == pytest.approx(0.93)
    assert row.final_label is None  # Rule fusion is intentionally not represented as complete.
    assert row.thumb_bytes.startswith(b"\xff\xd8")
    with Image.open(io.BytesIO(row.thumb_bytes)) as thumbnail:
        assert thumbnail.size == (224, 224)
        assert thumbnail.format == "JPEG"
        assert not thumbnail.getexif()
    assert service.class_order == EXPECTED_CLASS_ORDER


def test_diagnosis_endpoint_runs_the_bundled_model(client):
    owner = _register(client, "diagnose-real-model@example.test")
    field = _create_field(client, owner["access_token"])
    response = client.post(
        f"/fields/{field['id']}/diagnose",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        files={"file": ("leaf-gray.png", _image_bytes("L"), "image/png")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["predicted_label"] in EXPECTED_CLASS_ORDER
    assert tuple(body["probabilities"]) == EXPECTED_CLASS_ORDER
    assert sum(body["probabilities"].values()) == pytest.approx(1.0, abs=0.03)


def test_diagnosis_endpoint_enforces_auth_ownership_and_image_validation(client, monkeypatch):
    _install_fake_service(client, monkeypatch)
    owner = _register(client, "diagnose-owner@example.test")
    other = _register(client, "diagnose-other@example.test")
    field = _create_field(client, owner["access_token"])
    path = f"/fields/{field['id']}/diagnose"

    assert client.post(path, files={"file": ("leaf.png", _image_bytes(), "image/png")}).status_code == 401
    foreign = client.post(
        path,
        headers={"Authorization": f"Bearer {other['access_token']}"},
        files={"file": ("leaf.png", _image_bytes(), "image/png")},
    )
    assert foreign.status_code == 404
    corrupt = client.post(
        path,
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        files={"file": ("broken.png", b"broken", "image/png")},
    )
    assert corrupt.status_code == 422
    oversized = client.post(
        path,
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        files={"file": ("large.png", b"x" * (diagnosis_api.MAX_IMAGE_BYTES + 1), "image/png")},
    )
    assert oversized.status_code == 413


def test_diagnosis_endpoint_rate_limits_uploads(client, monkeypatch):
    _install_fake_service(client, monkeypatch)
    monkeypatch.setattr(diagnosis_api, "diagnosis_upload_limiter", diagnosis_api.UploadRateLimiter(1, 60))
    user = _register(client, "diagnose-rate@example.test")
    field = _create_field(client, user["access_token"])
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    upload = {"file": ("leaf.png", _image_bytes(), "image/png")}
    path = f"/fields/{field['id']}/diagnose"
    first = client.post(path, headers=headers, files=upload)
    second = client.post(path, headers=headers, files=upload)
    assert first.status_code == 201
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0


def test_diagnosis_endpoint_returns_service_unavailable_when_model_cannot_load(client, monkeypatch):
    from app.ml.inference import ModelUnavailableError

    owner = _register(client, "diagnose-unavailable@example.test")
    field = _create_field(client, owner["access_token"])

    def unavailable():
        raise ModelUnavailableError("model file missing")

    monkeypatch.setattr(diagnosis_api, "get_inference_service", unavailable)
    response = client.post(
        f"/fields/{field['id']}/diagnose",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        files={"file": ("leaf.png", _image_bytes(), "image/png")},
    )
    assert response.status_code == 503

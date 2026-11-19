"""Authenticated field-image inference endpoint."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, get_owned_field
from app.api.schemas import DiagnosisInferenceRead
from app.core.rate_limit import UploadRateLimiter
from app.db.models import Diagnosis, User
from app.db.session import get_db
from app.ml.inference import (
    DiseaseInferenceService,
    InferenceError,
    InvalidImageError,
    get_inference_service,
)

router = APIRouter(tags=["diagnosis"])
MAX_IMAGE_BYTES = 5 * 1024 * 1024
diagnosis_upload_limiter = UploadRateLimiter(max_requests=10, window_seconds=60)


def require_disease_inference() -> DiseaseInferenceService:
    try:
        return get_inference_service()
    except InferenceError as exc:
        raise HTTPException(status_code=503, detail="Disease inference is unavailable; try again later.") from exc


@router.post(
    "/fields/{field_id}/diagnose",
    response_model=DiagnosisInferenceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Classify a leaf image",
    description=(
        "Runs the four-class MobileNetV2 ONNX model and stores the model prediction and a sanitized "
        "224x224 JPEG thumbnail for the farmer's field. This endpoint returns CNN output only; "
        "disease-rule fusion, confidence bands, and human review are not yet applied."
    ),
    responses={
        404: {"description": "Field not found for the current user."},
        413: {"description": "Image exceeds the 5 MiB limit."},
        422: {"description": "Uploaded file is not a readable image."},
        429: {"description": "Per-user image upload rate limit exceeded."},
        503: {"description": "ONNX model or runtime is unavailable."},
    },
)
async def diagnose_field_image(
    field_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    inference: DiseaseInferenceService = Depends(require_disease_inference),
) -> DiagnosisInferenceRead:
    get_owned_field(field_id, db, user)
    diagnosis_upload_limiter.check(f"user:{user.id}")
    try:
        image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
    finally:
        await file.close()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image upload exceeds the 5 MiB limit.")

    try:
        prediction = await run_in_threadpool(inference.predict, image_bytes)
        thumbnail = await run_in_threadpool(inference.make_thumbnail, image_bytes)
    except InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InferenceError as exc:
        raise HTTPException(status_code=503, detail="Disease inference is unavailable; try again later.") from exc

    diagnosis = Diagnosis(
        field_id=field_id,
        thumb_bytes=thumbnail,
        cnn_probs_json=prediction.probabilities,
        cnn_label=prediction.predicted_label,
        cnn_confidence=prediction.confidence,
        fired_rules_json=[],
        status="auto",
    )
    db.add(diagnosis)
    db.commit()
    db.refresh(diagnosis)
    return DiagnosisInferenceRead(
        diagnosis_id=diagnosis.id,
        field_id=field_id,
        predicted_label=prediction.predicted_label,
        confidence=prediction.confidence,
        probabilities=prediction.probabilities,
        status="auto",
    )

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_field
from app.api.knowledge_base import get_effective_knowledge_base
from app.api.schemas import IrrigationDecisionRead, IrrigationDecisionRequest, OverrideRequest
from app.api.weather import get_field_weather
from app.db.models import Diagnosis, Field, IrrigationDecision, Reading, User
from app.db.session import get_db
from app.expert.engine import IrrigationInputs, evaluate_irrigation, parse_knowledge_base

router = APIRouter(tags=["irrigation"])


def _latest_reading(db: Session, field_id: int) -> Reading | None:
    return db.scalar(select(Reading).where(Reading.field_id == field_id).order_by(Reading.ts.desc()).limit(1))


def _recent_fungal_diagnosis(db: Session, field_id: int, days: float, labels: set[str]) -> Diagnosis | None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    candidates = db.scalars(
        select(Diagnosis).where(Diagnosis.field_id == field_id, Diagnosis.ts >= cutoff).order_by(Diagnosis.ts.desc())
    ).all()
    normalized = {label.strip().casefold() for label in labels}
    for diagnosis in candidates:
        label = (diagnosis.corrected_label or diagnosis.final_label or "").strip().casefold()
        if label in normalized:
            return diagnosis
    return None


@router.post(
    "/fields/{field_id}/irrigation/decide",
    response_model=IrrigationDecisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def decide_irrigation(
    field_id: int,
    body: IrrigationDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IrrigationDecision:
    field = get_owned_field(field_id, db, user)
    latest = _latest_reading(db, field_id)
    soil = body.soil_moisture_pct if body.soil_moisture_pct is not None else (latest.soil_moisture_pct if latest else None)
    temp = body.temp_c if body.temp_c is not None else (latest.temp_c if latest else None)
    humidity = body.humidity_pct if body.humidity_pct is not None else (latest.humidity_pct if latest else None)
    if soil is None or temp is None or humidity is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide soil moisture, temperature, and humidity or add a sensor reading first.",
        )
    rain = body.rain_forecast_mm_24h
    if rain is None:
        weather = await get_field_weather(field, db)
        rain = weather.rain_forecast_mm_24h

    version, yaml_text, _record = get_effective_knowledge_base(db)
    knowledge_base = parse_knowledge_base(yaml_text)
    now = datetime.now(timezone.utc)
    diagnosis = _recent_fungal_diagnosis(
        db,
        field_id,
        float(knowledge_base["thresholds"]["fungal_diagnosis_within_days"]),
        set(map(str, knowledge_base["thresholds"].get("fungal_labels", []))),
    )
    result = evaluate_irrigation(
        IrrigationInputs(
            soil_moisture_pct=soil,
            rain_forecast_mm_24h=rain,
            temp_c=temp,
            humidity_pct=humidity,
            crop_stage=field.crop_stage,
            recent_diagnosis_label=(diagnosis.corrected_label or diagnosis.final_label) if diagnosis else None,
            recent_diagnosis_ts=diagnosis.ts if diagnosis else None,
            now=now,
        ),
        knowledge_base,
        version=version,
    )
    decision = IrrigationDecision(
        field_id=field_id,
        kb_version=version,
        inputs_json=result["inputs"],
        fired_rules_json=result["fired_rule_ids"],
        action=result["action"],
        duration_level=result["duration_level"],
        explanation=result["explanation"],
        needs_review=result["needs_review"],
        decision_type=result["decision_type"],
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


@router.get("/fields/{field_id}/irrigation/history", response_model=list[IrrigationDecisionRead])
def irrigation_history(
    field_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[IrrigationDecision]:
    get_owned_field(field_id, db, user)
    query = (
        select(IrrigationDecision)
        .where(IrrigationDecision.field_id == field_id)
        .order_by(IrrigationDecision.ts.desc())
        .limit(limit)
    )
    return list(db.scalars(query).all())


@router.post("/irrigation/{decision_id}/override", response_model=IrrigationDecisionRead)
def override_irrigation(
    decision_id: int,
    body: OverrideRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IrrigationDecision:
    decision = db.scalar(
        select(IrrigationDecision)
        .join(Field, Field.id == IrrigationDecision.field_id)
        .where(IrrigationDecision.id == decision_id, Field.user_id == user.id)
    )
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Irrigation decision not found.")
    decision.override_action = body.override_action
    decision.override_note = body.override_note
    decision.override_by = user.id
    db.commit()
    db.refresh(decision)
    return decision

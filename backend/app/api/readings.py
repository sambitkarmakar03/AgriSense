import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_field
from app.api.schemas import CSVImportResponse, ReadingCreate, ReadingRead
from app.db.models import Reading, User
from app.db.session import get_db

router = APIRouter(tags=["readings"])
MAX_CSV_BYTES = 10 * 1024 * 1024


def _utc_datetime(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Timestamp must be ISO 8601.") from exc
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _parse_csv(payload: bytes) -> list[dict]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.") from exc
    reader = csv.DictReader(io.StringIO(text))
    required = {"soil_moisture_pct", "temp_c", "humidity_pct"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=422,
            detail="CSV headers must include soil_moisture_pct, temp_c, and humidity_pct; ts is optional.",
        )
    rows = []
    for line_number, row in enumerate(reader, start=2):
        try:
            values = {
                "soil_moisture_pct": float(row["soil_moisture_pct"]),
                "temp_c": float(row["temp_c"]),
                "humidity_pct": float(row["humidity_pct"]),
                "ts": _utc_datetime(row.get("ts")),
            }
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid CSV value on line {line_number}: {exc}") from exc
        if not (0 <= values["soil_moisture_pct"] <= 100 and 0 <= values["humidity_pct"] <= 100):
            raise HTTPException(status_code=422, detail=f"Percent values are out of range on line {line_number}.")
        if not -80 <= values["temp_c"] <= 70:
            raise HTTPException(status_code=422, detail=f"Temperature is out of range on line {line_number}.")
        rows.append(values)
    if not rows:
        raise HTTPException(status_code=422, detail="CSV contains no readings.")
    return rows


@router.post("/fields/{field_id}/readings", response_model=ReadingRead, status_code=status.HTTP_201_CREATED)
def create_reading(
    field_id: int,
    body: ReadingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Reading:
    get_owned_field(field_id, db, user)
    values = body.model_dump(exclude={"ts"})
    reading = Reading(field_id=field_id, source="manual", **values)
    if body.ts is not None:
        reading.ts = body.ts.replace(tzinfo=timezone.utc) if body.ts.tzinfo is None else body.ts
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


@router.post("/fields/{field_id}/readings/csv", response_model=CSVImportResponse, status_code=status.HTTP_201_CREATED)
async def upload_readings_csv(
    field_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CSVImportResponse:
    get_owned_field(field_id, db, user)
    payload = await file.read(MAX_CSV_BYTES + 1)
    if len(payload) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV upload exceeds the 10 MB limit.")
    rows = _parse_csv(payload)
    readings = [Reading(field_id=field_id, source="csv", **row) for row in rows]
    db.add_all(readings)
    db.commit()
    for reading in readings:
        db.refresh(reading)
    return CSVImportResponse(imported=len(readings), readings=[ReadingRead.model_validate(row) for row in readings])


@router.get("/fields/{field_id}/readings", response_model=list[ReadingRead])
def get_readings(
    field_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Reading]:
    get_owned_field(field_id, db, user)
    query = select(Reading).where(Reading.field_id == field_id).order_by(Reading.ts.desc()).limit(limit)
    return list(db.scalars(query).all())

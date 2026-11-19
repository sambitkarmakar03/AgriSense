from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_field
from app.api.schemas import WeatherRead
from app.core.config import get_settings
from app.db.models import Field, Reading, User
from app.db.session import get_db

router = APIRouter(tags=["weather"])


async def fetch_open_meteo(lat: float, lon: float) -> dict[str, float]:
    settings = get_settings()
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m",
        "hourly": "precipitation",
        "forecast_days": 2,
        "timezone": "UTC",
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(settings.open_meteo_url, params=params)
        response.raise_for_status()
        payload = response.json()

    current = payload["current"]
    hourly = payload["hourly"]
    times = hourly["time"]
    precipitation = hourly["precipitation"]
    if len(times) != len(precipitation):
        raise ValueError("Weather provider returned mismatched hourly arrays.")
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=24)
    rain_24h = 0.0
    for raw_time, mm in zip(times, precipitation):
        point = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        if point.tzinfo is None:
            point = point.replace(tzinfo=timezone.utc)
        if start <= point < end and mm is not None:
            rain_24h += float(mm)
    return {
        "temp_c": float(current["temperature_2m"]),
        "humidity_pct": float(current["relative_humidity_2m"]),
        "rain_forecast_mm_24h": rain_24h,
    }


async def get_field_weather(field: Field, db: Session) -> WeatherRead:
    latest = db.scalar(
        select(Reading).where(Reading.field_id == field.id).order_by(Reading.ts.desc()).limit(1)
    )
    fallback_temp = latest.temp_c if latest else None
    fallback_humidity = latest.humidity_pct if latest else None
    if field.lat is None or field.lon is None:
        return WeatherRead(
            field_id=field.id,
            status="fallback",
            source="latest_reading" if latest else "unavailable",
            temp_c=fallback_temp,
            humidity_pct=fallback_humidity,
            rain_forecast_mm_24h=None,
            warning="Field coordinates are missing; weather forecast is unavailable.",
        )
    try:
        values = await fetch_open_meteo(field.lat, field.lon)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        return WeatherRead(
            field_id=field.id,
            status="fallback",
            source="latest_reading" if latest else "unavailable",
            temp_c=fallback_temp,
            humidity_pct=fallback_humidity,
            rain_forecast_mm_24h=None,
            warning=f"Open-Meteo is unavailable; using the latest reading where available ({type(exc).__name__}).",
        )
    return WeatherRead(field_id=field.id, status="ok", source="open-meteo", **values)


@router.get("/fields/{field_id}/weather", response_model=WeatherRead)
async def field_weather(
    field_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WeatherRead:
    field = get_owned_field(field_id, db, user)
    return await get_field_weather(field, db)

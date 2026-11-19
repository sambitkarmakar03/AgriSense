from fastapi import APIRouter

from app.api.schemas import AboutSystemRead, HealthRead

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    return HealthRead(status="ok")


@router.get("/about/system", response_model=AboutSystemRead)
def about_system() -> AboutSystemRead:
    return AboutSystemRead(
        inputs=["Field crop and growth stage", "Soil moisture and environmental readings", "24-hour weather forecast", "Recent disease diagnosis when available"],
        outputs=["Irrigation ON/OFF", "Duration level", "Fired-rule trace", "Plain-language explanation and review flag"],
        processor=["YAML-versioned knowledge base", "Forward-chaining inference engine", "Open-Meteo forecast proxy"],
        feedback=["Farmer irrigation overrides and notes", "Consent log", "Future diagnosis confirmations and corrections"],
        interfaces=["Farmer web client", "Agronomist knowledge-base editor", "FastAPI JSON API"],
        boundary="Advice is decision support only. It does not replace an agronomist, sensor validation, or local judgment.",
        environment=["Field conditions and crop stage", "Weather services", "Local SQLite or hosted PostgreSQL", "Windows and macOS development environments"],
    )

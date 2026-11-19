import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CropStage = Literal["Seedling", "Vegetative", "Flowering", "Fruiting"]
Action = Literal["ON", "OFF"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserPublic(ORMModel):
    id: int
    email: str
    full_name: str | None
    role: str
    created_at: datetime


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    full_name: str | None = Field(default=None, max_length=160)
    consent_accepted: bool
    consent_text_version: str = Field(default="v1", min_length=1, max_length=64)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address.")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class FieldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    crop: str = Field(min_length=1, max_length=120)
    crop_stage: CropStage
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class FieldUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    crop: str | None = Field(default=None, min_length=1, max_length=120)
    crop_stage: CropStage | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def reject_null_required_values(self):
        for name in ("name", "crop", "crop_stage"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class FieldRead(ORMModel):
    id: int
    user_id: int
    name: str
    crop: str
    crop_stage: CropStage
    lat: float | None
    lon: float | None
    created_at: datetime


class ReadingCreate(BaseModel):
    soil_moisture_pct: float = Field(ge=0, le=100)
    temp_c: float = Field(ge=-80, le=70)
    humidity_pct: float = Field(ge=0, le=100)
    ts: datetime | None = None


class ReadingRead(ORMModel):
    id: int
    field_id: int
    ts: datetime
    soil_moisture_pct: float
    temp_c: float
    humidity_pct: float
    source: str


class CSVImportResponse(BaseModel):
    imported: int
    readings: list[ReadingRead]


class WeatherRead(BaseModel):
    field_id: int
    status: Literal["ok", "fallback"]
    source: str
    temp_c: float | None
    humidity_pct: float | None
    rain_forecast_mm_24h: float | None
    warning: str | None = None


class IrrigationDecisionRequest(BaseModel):
    soil_moisture_pct: float | None = Field(default=None, ge=0, le=100)
    temp_c: float | None = Field(default=None, ge=-80, le=70)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    rain_forecast_mm_24h: float | None = Field(default=None, ge=0)


class IrrigationDecisionRead(ORMModel):
    id: int
    field_id: int
    ts: datetime
    kb_version: str
    inputs_json: dict
    fired_rules_json: list[str]
    action: Action
    duration_level: Literal["normal", "increased", "short", "low_volume"]
    explanation: str
    needs_review: bool
    decision_type: Literal["structured", "semi-structured"]
    override_action: Action | None
    override_note: str | None


class OverrideRequest(BaseModel):
    override_action: Action
    override_note: str | None = Field(default=None, max_length=1000)


class KBRead(BaseModel):
    kind: str
    version: str
    yaml_text: str
    author_id: int | None = None
    ts: datetime | None = None


class KBUpdateRequest(BaseModel):
    yaml_text: str = Field(min_length=1, max_length=100_000)
    expected_version: str | None = None


class KBVersionRead(BaseModel):
    kind: str
    version: str
    author_id: int | None
    ts: datetime | None
    source: Literal["packaged", "database"]


class HealthRead(BaseModel):
    status: Literal["ok"]


class AboutSystemRead(BaseModel):
    inputs: list[str]
    outputs: list[str]
    processor: list[str]
    feedback: list[str]
    interfaces: list[str]
    boundary: str
    environment: list[str]

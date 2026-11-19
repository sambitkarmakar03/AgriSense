from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="farmer", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    fields: Mapped[list["Field"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    consent_logs: Mapped[list["ConsentLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    kb_versions: Mapped[list["KBVersion"]] = relationship(
        back_populates="author", foreign_keys="KBVersion.author_id"
    )


class Field(Base):
    __tablename__ = "fields"
    __table_args__ = (Index("ix_fields_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    crop: Mapped[str] = mapped_column(String(120), nullable=False)
    crop_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="fields")
    readings: Mapped[list["Reading"]] = relationship(back_populates="field", cascade="all, delete-orphan")
    irrigation_decisions: Mapped[list["IrrigationDecision"]] = relationship(
        back_populates="field", cascade="all, delete-orphan"
    )
    diagnoses: Mapped[list["Diagnosis"]] = relationship(back_populates="field", cascade="all, delete-orphan")


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (Index("ix_readings_field_ts", "field_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    soil_moisture_pct: Mapped[float] = mapped_column(nullable=False)
    temp_c: Mapped[float] = mapped_column(nullable=False)
    humidity_pct: Mapped[float] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)

    field: Mapped[Field] = relationship(back_populates="readings")


class IrrigationDecision(Base):
    __tablename__ = "irrigation_decisions"
    __table_args__ = (Index("ix_irrigation_decisions_field_ts", "field_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    kb_version: Mapped[str] = mapped_column(String(32), nullable=False)
    inputs_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    fired_rules_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    duration_level: Mapped[str] = mapped_column(String(24), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    needs_review: Mapped[bool] = mapped_column(default=False, nullable=False)
    decision_type: Mapped[str] = mapped_column(String(24), nullable=False)
    override_action: Mapped[str | None] = mapped_column(String(8))
    override_note: Mapped[str | None] = mapped_column(Text)
    override_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    field: Mapped[Field] = relationship(back_populates="irrigation_decisions")


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (Index("ix_diagnoses_field_ts", "field_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    thumb_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    cnn_probs_json: Mapped[dict | None] = mapped_column(JSON)
    cnn_label: Mapped[str | None] = mapped_column(String(64))
    cnn_confidence: Mapped[float | None]
    fired_rules_json: Mapped[list[str] | None] = mapped_column(JSON)
    final_label: Mapped[str | None] = mapped_column(String(64))
    confidence_band: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    corrected_label: Mapped[str | None] = mapped_column(String(64))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    advice: Mapped[str | None] = mapped_column(Text)

    field: Mapped[Field] = relationship(back_populates="diagnoses")


class KBVersion(Base):
    __tablename__ = "kb_versions"
    __table_args__ = (UniqueConstraint("kind", "version", name="uq_kb_versions_kind_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    yaml_text: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    author: Mapped[User | None] = relationship(back_populates="kb_versions", foreign_keys=[author_id])


class ConsentLog(Base):
    __tablename__ = "consent_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    text_version: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped[User] = relationship(back_populates="consent_logs")

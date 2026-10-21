"""M8.2 medical device integration models (migration 0019)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, \
    UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.functions import now

from .db import Base


def _org_fk() -> ForeignKey:
    return ForeignKey("organizations.id", ondelete="CASCADE")


def _user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="SET NULL")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                         server_default=text("gen_random_uuid()"))


class MedicalDevice(Base):
    """A device on the tenant's allow-list. Identity is immutable (trigger);
    the only change is active → retired."""

    __tablename__ = "medical_devices"
    __table_args__ = (
        CheckConstraint("kind IN ('bp_monitor','pulse_oximeter')", name="ck_meddev_kind"),
        CheckConstraint("status IN ('active','retired')", name="ck_meddev_status"),
        CheckConstraint("(status = 'retired') = (retired_at IS NOT NULL)",
                        name="ck_meddev_retired"),
        Index("uq_meddev_active_address", "organization_id", "address_hash", unique=True,
              postgresql_where=text("status = 'active'")),
        Index("ix_meddev_org", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _org_fk(),
                                                       nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(80), nullable=False, server_default="")
    model: Mapped[str] = mapped_column(String(80), nullable=False, server_default="")
    serial: Mapped[str] = mapped_column(String(80), nullable=False, server_default="")
    firmware: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    address_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_simulator: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                               server_default=text("false"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    registered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=now())
    retired_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk())
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceReading(Base):
    """APPEND-ONLY raw device reading with provenance (trigger + no grants)."""

    __tablename__ = "device_readings"
    __table_args__ = (
        CheckConstraint("kind IN ('blood_pressure','spo2')", name="ck_devread_kind"),
        CheckConstraint("characteristic IN ('2a35','2a5e','2a5f')", name="ck_devread_char"),
        CheckConstraint("source IN ('ble','simulator')", name="ck_devread_source"),
        CheckConstraint("raw_sha256 ~ '^[0-9a-f]{64}$'", name="ck_devread_sha"),
        UniqueConstraint("organization_id", "capture_id", name="uq_devread_capture"),
        Index("ix_devread_encounter", "organization_id", "encounter_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _org_fk(),
                                                       nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medical_devices.id", ondelete="CASCADE"),
        nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False)
    capture_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    characteristic: Mapped[str] = mapped_column(String(4), nullable=False)
    raw_hex: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parsed: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    device_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=now())
    clock_skew: Mapped[bool] = mapped_column(Boolean, nullable=False)
    captured_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk())
    app_version: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")


class DeviceReadingDecision(Base):
    """APPEND-ONLY clinician decision; at most one per reading."""

    __tablename__ = "device_reading_decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('accepted','rejected')", name="ck_devdec_decision"),
        CheckConstraint("surface IN ('web','android')", name="ck_devdec_surface"),
        CheckConstraint("decision = 'accepted' OR length(btrim(reason)) >= 3",
                        name="ck_devdec_reason"),
        UniqueConstraint("reading_id", name="uq_devdec_reading"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _org_fk(),
                                                       nullable=False)
    reading_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_readings.id", ondelete="CASCADE"),
        nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False, server_default="")
    surface: Mapped[str] = mapped_column(String(10), nullable=False)
    vitals_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounter_vitals.id", ondelete="SET NULL"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk())
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=now())

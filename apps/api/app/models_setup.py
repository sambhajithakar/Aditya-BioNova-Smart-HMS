"""ORM models for the Smart Setup Wizard, QR check-in and printer profiles
(migration 0015). Kept apart from ``models.py`` so parallel workstreams do
not collide; the declarative ``Base`` is shared."""
from __future__ import annotations

import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Time, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


def _uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _org():
    return mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                         nullable=False)


def _user(nullable: bool = True):
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=nullable)


def _now():
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class OrgSettings(Base):
    __tablename__ = "org_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    wizard: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_by: Mapped[uuid.UUID | None] = _user()
    updated_at: Mapped[datetime] = _now()


class BranchWorkingHours(Base):
    __tablename__ = "branch_working_hours"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    opens_at: Mapped[time] = mapped_column(Time, nullable=False)
    closes_at: Mapped[time] = mapped_column(Time, nullable=False)
    break_starts_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_ends_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = _now()


class FeeSchedule(Base):
    __tablename__ = "fee_schedule"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    provider_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    consultation_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    follow_up_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    follow_up_valid_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class CheckinToken(Base):
    __tablename__ = "checkin_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by: Mapped[uuid.UUID | None] = _user()
    queue_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opd_queue.id", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = _now()


class PrinterProfile(Base):
    __tablename__ = "printer_profiles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    default_for: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False,
                                                   default=list)
    margin_top_mm: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    margin_right_mm: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    margin_bottom_mm: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    margin_left_mm: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    font_scale: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    notes: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()

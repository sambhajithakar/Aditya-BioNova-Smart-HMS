"""ORM models for communications v2 + follow-up CRM (migration 0014).

Kept out of ``models.py`` so parallel workstreams merge cleanly. All tables
are tenant-scoped (``organization_id`` + strict RLS); the delivery log and
consent history are append-only in the database.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


def _now():
    return text("now()")


def _org_fk(**kw):
    return mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                         nullable=False, **kw)


def _user_fk():
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True)


class CommsTenantSettings(Base):
    __tablename__ = "comms_tenant_settings"

    organization_id: Mapped[uuid.UUID] = _org_fk(primary_key=True)
    monthly_spend_cap_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quiet_start_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=21,
                                                  server_default="21")
    quiet_end_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=8,
                                                server_default="8")
    reminder_hours_ahead: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=24,
                                                      server_default="24")
    reminder_channels: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, default=lambda: ["sms"], server_default="{sms}")
    updated_by: Mapped[uuid.UUID | None] = _user_fk()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=_now())


class CommsTemplate(Base):
    __tablename__ = "comms_templates"
    __table_args__ = (
        Index("ix_commstpl_org", "organization_id", "channel"),
        Index("uq_commstpl_active", "organization_id", "channel", "purpose", "language",
              unique=True, postgresql_where=text("is_active")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = _org_fk()
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False, default="",
                                         server_default="")
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    dlt_template_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    whatsapp_template_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                            server_default=text("true"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                             server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = _user_fk()
    updated_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=_now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=_now())


class CommsPatientPreference(Base):
    __tablename__ = "comms_patient_preferences"

    organization_id: Mapped[uuid.UUID] = _org_fk(primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    preferred_language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = _user_fk()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=_now())


class CommsConsent(Base):
    __tablename__ = "comms_consents"

    organization_id: Mapped[uuid.UUID] = _org_fk(primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), primary_key=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk()
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=_now())


class CommsConsentEvent(Base):
    __tablename__ = "comms_consent_events"
    __table_args__ = (
        Index("ix_commsconsentev_patient", "organization_id", "patient_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[uuid.UUID] = _org_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk()
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=_now())


class FollowUp(Base):
    __tablename__ = "follow_ups"
    __table_args__ = (
        Index("ix_followup_org_due", "organization_id", "status", "due_date"),
        Index("ix_followup_org_patient", "organization_id", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = _org_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="planned",
                                        server_default="planned")
    assigned_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_by: Mapped[uuid.UUID | None] = _user_fk()
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    status_note: Mapped[str] = mapped_column(String(200), nullable=False, default="",
                                             server_default="")
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=_now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=_now())


class CommsDelivery(Base):
    __tablename__ = "comms_delivery_log"
    __table_args__ = (
        Index("ix_commslog_org_created", "organization_id", "created_at"),
        Index("ix_commslog_org_period", "organization_id", "period", "channel"),
        Index("uq_commslog_dedupe", "organization_id", "dedupe_key", unique=True,
              postgresql_where=text("dedupe_key IS NOT NULL AND status IN "
                                    "('queued','sent','sent_mock','suppressed')")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[uuid.UUID] = _org_fk()
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comms_templates.id", ondelete="SET NULL"),
        nullable=True)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    follow_up_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("follow_ups.id", ondelete="SET NULL"), nullable=True)
    recipient_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(25), nullable=False)
    cost_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                            server_default="0")
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual",
                                         server_default="manual")
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk()
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=_now())

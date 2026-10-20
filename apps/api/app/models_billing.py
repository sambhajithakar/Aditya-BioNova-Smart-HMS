"""ORM models for SaaS subscription billing (migration 0013).

The vendor's billing of clinics for the software — never mixed with clinical
patient billing (``models.Invoice`` / ``Payment`` / ``LedgerEntry``)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Index, Integer, \
    String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.functions import now

from .db import Base


def _org_fk() -> ForeignKey:
    return ForeignKey("organizations.id", ondelete="RESTRICT")


def _user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="SET NULL")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                         server_default=text("gen_random_uuid()"))


class AiCreditPack(Base):
    __tablename__ = "ai_credit_packs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    price_paise: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=now())


class SaasOrder(Base):
    __tablename__ = "saas_orders"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_saasorder_idem"),
        Index("ix_saasorder_org_created", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _org_fk(), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                      ForeignKey("plans.id"))
    billing_cycle: Mapped[str | None] = mapped_column(String(10))
    pack_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                      ForeignKey("ai_credit_packs.id"))
    credits: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    gst_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="created")
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                         _user_fk())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SaasPayment(Base):
    __tablename__ = "saas_payments"
    __table_args__ = (Index("ix_saaspay_order", "order_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _org_fk(), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                ForeignKey("saas_orders.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    method: Mapped[str | None] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=now())


class SaasInvoice(Base):
    __tablename__ = "saas_invoices"
    __table_args__ = (Index("uq_saasinv_order_invoice", "order_id", unique=True,
                            postgresql_where=text("kind = 'invoice'")),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _org_fk(), nullable=False)
    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                ForeignKey("saas_orders.id"), nullable=False)
    refund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saas_invoices.id"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                server_default=now())
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seller: Mapped[dict] = mapped_column(JSONB, nullable=False)
    buyer: Mapped[dict] = mapped_column(JSONB, nullable=False)
    lines: Mapped[list] = mapped_column(JSONB, nullable=False)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tax_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class SaasRefund(Base):
    __tablename__ = "saas_refunds"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _org_fk(), nullable=False)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("saas_payments.id"),
                                                  nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="requested")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                           _user_fk())
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                         _user_fk())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    provider_refund_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=now())


class SaasWebhookEvent(Base):
    __tablename__ = "saas_webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_saaswebhook_event"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str] = mapped_column(String(300), nullable=False, server_default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=now())

"""Pydantic schemas for SaaS subscription billing (M7.2)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogPlan(BaseModel):
    code: str
    name: str
    tier: int
    price_monthly_paise: int | None
    price_annual_paise: int | None
    purchasable: bool


class CatalogPack(BaseModel):
    code: str
    name: str
    credits: int
    price_paise: int | None
    purchasable: bool


class BillingCatalog(BaseModel):
    provider: str
    mode: str                        # sandbox | simulator
    gst_rate_bp: int
    currency: str = "INR"
    plans: list[CatalogPlan]
    credit_packs: list[CatalogPack]
    notice: str


class OrderIn(_In):
    kind: Literal["subscription", "ai_credits"]
    plan_code: str | None = Field(default=None, max_length=40)
    billing_cycle: Literal["monthly", "annual"] | None = None
    pack_code: str | None = Field(default=None, max_length=40)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    description: str
    billing_cycle: str | None
    credits: int | None
    amount_paise: int
    tax_paise: int
    total_paise: int
    currency: str
    provider: str
    provider_order_id: str
    status: str
    failure_reason: str | None
    created_at: datetime
    paid_at: datetime | None


class CheckoutParams(BaseModel):
    provider: str
    mode: str
    key_id: str
    provider_order_id: str
    amount: int
    currency: str


class OrderCreated(BaseModel):
    order: OrderOut
    checkout: CheckoutParams


class VerifyIn(_In):
    provider_payment_id: str = Field(min_length=4, max_length=64)
    signature: str = Field(min_length=16, max_length=200)


class SimulateIn(_In):
    outcome: Literal["success", "failure"] = "success"


class PaymentResult(BaseModel):
    outcome: str
    order: OrderOut


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    provider: str
    provider_payment_id: str
    amount_paise: int
    currency: str
    status: str
    method: str | None
    source: str
    error: str | None
    created_at: datetime


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    kind: str
    order_id: uuid.UUID
    related_invoice_id: uuid.UUID | None
    issued_at: datetime
    period_start: datetime | None
    period_end: datetime | None
    seller: dict
    buyer: dict
    lines: list
    subtotal_paise: int
    tax_breakdown: dict
    tax_paise: int
    total_paise: int
    currency: str


class RefundIn(_In):
    payment_id: uuid.UUID
    amount_paise: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=500)


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    payment_id: uuid.UUID
    amount_paise: int
    reason: str
    status: str
    requested_by: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    provider_refund_id: str | None
    error: str | None
    created_at: datetime


class RefundDecisionIn(_In):
    approve: bool
    note: str = Field(default="", max_length=500)


class CreditsOut(BaseModel):
    """``plan_allowance`` resets every month. Purchased credits do NOT expire:
    ``purchased`` is the balance still available from every pack ever bought."""
    period: str
    plan_allowance: int | None
    allowance_used: int
    purchased: int
    purchased_total: int
    used: int
    remaining: int | None
    purchased_expire: bool = False


class CreditPackIn(_In):
    name: str = Field(min_length=2, max_length=120)
    credits: int = Field(gt=0, le=1_000_000)
    price_paise: int | None = Field(default=None, gt=0)
    is_active: bool = True


class LifecycleOut(BaseModel):
    past_due: int
    read_only: int
    orders_expired: int


class ReconciliationOut(BaseModel):
    checked_at: datetime
    issues: list[dict]

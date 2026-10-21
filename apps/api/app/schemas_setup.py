"""Request/response schemas for the Smart Setup Wizard, QR check-in and
printer profiles. ``OrgSettings`` is THE validated shape of the
``org_settings.settings`` JSONB document (versioned)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .schemas import StrictModel
from .services.setup_rules import Session, working_hours_errors

SETTINGS_SCHEMA_VERSION = 1

WIZARD_STEPS = (
    "identity", "branch", "staff", "language", "working_hours", "fees",
    "prescription", "billing", "printer", "schedule", "edition",
)
PAYMENT_METHODS = ("cash", "upi", "card", "insurance", "other")
PRINT_DOCUMENTS = ("prescription", "receipt", "lab_report")
PRINTER_KINDS = ("a4", "a5", "thermal_80mm", "thermal_58mm")
SLOT_LENGTHS = (5, 10, 15, 20, 30, 45, 60)


# --- settings document -----------------------------------------------------------
class PrescriptionSettings(StrictModel):
    header_text: str = Field(default="", max_length=500)
    footer_text: str = Field(default="", max_length=500)
    show_registration_number: bool = True
    paper_size: Literal["A4", "A5"] = "A4"
    language: Literal["en", "mr", "hi", "trilingual"] = "trilingual"


class BillingSettings(StrictModel):
    """Clinic (patient) billing defaults — unrelated to the SaaS subscription."""

    invoice_prefix: str = Field(default="INV", pattern=r"^[A-Z0-9][A-Z0-9/-]{0,11}$")
    show_gstin: bool = True
    default_payment_methods: list[Literal["cash", "upi", "card", "insurance", "other"]] = \
        Field(default_factory=lambda: ["cash", "upi"], min_length=1, max_length=5)
    receipt_footer: str = Field(default="", max_length=300)

    @field_validator("default_payment_methods")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("payment methods must not repeat")
        return v


class ScheduleSettings(StrictModel):
    slot_minutes: int = 15
    max_per_slot: int = Field(default=1, ge=1, le=20)
    online_booking_enabled: bool = False

    @field_validator("slot_minutes")
    @classmethod
    def _slot(cls, v: int) -> int:
        if v not in SLOT_LENGTHS:
            raise ValueError(f"slot_minutes must be one of {list(SLOT_LENGTHS)}")
        return v


class OrgSettings(StrictModel):
    version: Literal[1] = SETTINGS_SCHEMA_VERSION
    prescription: PrescriptionSettings = Field(default_factory=PrescriptionSettings)
    billing: BillingSettings = Field(default_factory=BillingSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)


class OrgSettingsPatch(StrictModel):
    """Each given section REPLACES the stored section (validated in full)."""

    prescription: PrescriptionSettings | None = None
    billing: BillingSettings | None = None
    schedule: ScheduleSettings | None = None


class OrgSettingsOut(BaseModel):
    schema_version: int
    settings: OrgSettings
    updated_at: datetime | None


# --- wizard ------------------------------------------------------------------------
StepKey = Literal["identity", "branch", "staff", "language", "working_hours", "fees",
                  "prescription", "billing", "printer", "schedule", "edition"]


class WizardStepIn(StrictModel):
    status: Literal["done", "skipped", "todo"]


class WizardPatchIn(StrictModel):
    current_step: StepKey | None = None
    finished: bool | None = None


class WizardStepOut(BaseModel):
    key: str
    status: Literal["done", "skipped", "todo"]
    # what the clinic's data says, independent of the owner's clicks
    data_ready: bool


class WizardOut(BaseModel):
    steps: list[WizardStepOut]
    current_step: str
    finished: bool
    finished_at: datetime | None
    should_show: bool
    progress_percent: int


# --- working hours -----------------------------------------------------------------
class WorkingSessionIn(StrictModel):
    weekday: int = Field(ge=0, le=6)
    opens_at: time
    closes_at: time
    break_starts_at: time | None = None
    break_ends_at: time | None = None


class WorkingHoursIn(StrictModel):
    sessions: list[WorkingSessionIn] = Field(max_length=21)

    @model_validator(mode="after")
    def _valid(self) -> "WorkingHoursIn":
        errors = working_hours_errors([Session(**s.model_dump()) for s in self.sessions])
        if errors:
            raise ValueError("; ".join(errors))
        return self


class WorkingSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: int
    opens_at: time
    closes_at: time
    break_starts_at: time | None
    break_ends_at: time | None


class WorkingHoursOut(BaseModel):
    branch_id: uuid.UUID
    sessions: list[WorkingSessionOut]


# --- fees ----------------------------------------------------------------------------
_MONEY = dict(ge=0, le=1_000_000, max_digits=12, decimal_places=2)


class FeeIn(StrictModel):
    consultation_fee: Decimal = Field(**_MONEY)
    follow_up_fee: Decimal | None = Field(default=None, **_MONEY)
    follow_up_valid_days: int | None = Field(default=None, ge=0, le=365)


class FeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider_user_id: uuid.UUID | None
    consultation_fee: Decimal
    follow_up_fee: Decimal | None
    follow_up_valid_days: int | None
    updated_at: datetime


class FeesOut(BaseModel):
    default: FeeOut | None
    providers: list[FeeOut]


class EffectiveFeeOut(BaseModel):
    provider_user_id: uuid.UUID | None
    source: Literal["provider", "default", "none"]
    consultation_fee: Decimal | None
    follow_up_fee: Decimal | None
    follow_up_valid_days: int | None


# --- slots ---------------------------------------------------------------------------
class SlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    booked: int
    available: bool


class SlotsOut(BaseModel):
    branch_id: uuid.UUID
    date: date
    provider_user_id: uuid.UUID | None
    configured: bool
    slot_minutes: int
    max_per_slot: int
    slots: list[SlotOut]


# --- check-in ------------------------------------------------------------------------
class CheckinIssueOut(BaseModel):
    appointment_id: uuid.UUID
    # the ONLY content of the QR code: random, single-purpose, no PHI
    token: str
    expires_at: datetime


class CheckinCodeIn(StrictModel):
    code: str = Field(min_length=10, max_length=64)


class CheckinVerifyOut(BaseModel):
    """Minimal context for AUTHENTICATED staff to confirm identity verbally."""

    status: Literal["ready", "already_checked_in"]
    appointment_id: uuid.UUID
    patient_display_name: str
    appointment_starts_at: datetime
    branch_name: str
    queue_token_number: int | None


class CheckinQueueOut(BaseModel):
    id: uuid.UUID
    token_number: int
    status: str
    service_date: date


class CheckinConfirmOut(BaseModel):
    status: Literal["checked_in", "already_checked_in"]
    appointment_id: uuid.UUID
    queue_entry: CheckinQueueOut


class KioskCheckinOut(BaseModel):
    """Self check-in kiosk answer: no name, no appointment details."""

    status: Literal["checked_in", "already_checked_in"]
    token_number: int


# --- printers ------------------------------------------------------------------------
_MARGIN = dict(ge=0, le=50, max_digits=4, decimal_places=1)
PrintDocument = Literal["prescription", "receipt", "lab_report"]


class PrinterProfileIn(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["a4", "a5", "thermal_80mm", "thermal_58mm"]
    default_for: list[PrintDocument] = Field(default_factory=list, max_length=3)
    margin_top_mm: Decimal = Field(default=Decimal("10"), **_MARGIN)
    margin_right_mm: Decimal = Field(default=Decimal("10"), **_MARGIN)
    margin_bottom_mm: Decimal = Field(default=Decimal("10"), **_MARGIN)
    margin_left_mm: Decimal = Field(default=Decimal("10"), **_MARGIN)
    font_scale: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0.5"), le=Decimal("2.0"),
                                max_digits=3, decimal_places=2)
    notes: str = Field(default="", max_length=300)

    @field_validator("default_for")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return sorted(set(v))


class PrinterProfileUpdateIn(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: Literal["a4", "a5", "thermal_80mm", "thermal_58mm"] | None = None
    default_for: list[PrintDocument] | None = Field(default=None, max_length=3)
    margin_top_mm: Decimal | None = Field(default=None, **_MARGIN)
    margin_right_mm: Decimal | None = Field(default=None, **_MARGIN)
    margin_bottom_mm: Decimal | None = Field(default=None, **_MARGIN)
    margin_left_mm: Decimal | None = Field(default=None, **_MARGIN)
    font_scale: Decimal | None = Field(default=None, ge=Decimal("0.5"), le=Decimal("2.0"),
                                       max_digits=3, decimal_places=2)
    notes: str | None = Field(default=None, max_length=300)

    @field_validator("default_for")
    @classmethod
    def _unique(cls, v: list[str] | None) -> list[str] | None:
        return sorted(set(v)) if v is not None else None


class PrinterProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str
    default_for: list[str]
    margin_top_mm: Decimal
    margin_right_mm: Decimal
    margin_bottom_mm: Decimal
    margin_left_mm: Decimal
    font_scale: Decimal
    notes: str
    created_at: datetime
    updated_at: datetime


class PrinterDefaultsOut(BaseModel):
    prescription: PrinterProfileOut | None
    receipt: PrinterProfileOut | None
    lab_report: PrinterProfileOut | None

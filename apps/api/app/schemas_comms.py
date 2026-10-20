"""Pydantic schemas for communications v2 and the follow-up CRM."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


Channel = Literal["email", "sms", "whatsapp"]
Purpose = Literal["appointment_reminder", "follow_up", "missed_appointment", "generic"]
Language = Literal["en", "mr", "hi"]
ConsentStatus = Literal["opted_in", "opted_out"]
ConsentSource = Literal["registration_form", "patient_request", "patient_reply", "staff_update"]
FollowUpStatus = Literal["planned", "reminded", "booked", "completed", "missed", "cancelled"]

_DLT_RE = re.compile(r"^[0-9]{10,30}$")
_WA_RE = re.compile(r"^[a-z0-9_]{1,120}$")
# Follow-up reasons are short administrative labels shown on worklists; they
# are never inserted into patient messages.
_REASON_RE = re.compile(r"^[\w .,'()/&+-]{2,80}$", re.UNICODE)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------- templates
def _check_dlt(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    if not _DLT_RE.match(v):
        raise ValueError("DLT template id must be 10-30 digits")
    return v


def _check_wa(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    if not _WA_RE.match(v):
        raise ValueError("WhatsApp template name: lowercase letters, digits, underscore")
    return v


class TemplateIn(StrictModel):
    channel: Channel
    purpose: Purpose
    language: Language
    name: str = Field(min_length=2, max_length=120)
    subject: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=2000)
    dlt_template_id: str | None = Field(default=None, max_length=40)
    whatsapp_template_name: str | None = Field(default=None, max_length=120)
    is_active: bool = True

    _dlt = field_validator("dlt_template_id")(_check_dlt)
    _wa = field_validator("whatsapp_template_name")(_check_wa)


class TemplateUpdateIn(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=2000)
    dlt_template_id: str | None = Field(default=None, max_length=40)
    whatsapp_template_name: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None

    _dlt = field_validator("dlt_template_id")(_check_dlt)
    _wa = field_validator("whatsapp_template_name")(_check_wa)


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: str
    purpose: str
    language: str
    name: str
    subject: str
    body: str
    dlt_template_id: str | None
    whatsapp_template_name: str | None
    is_active: bool
    is_default: bool
    placeholders: list[str] = []
    updated_at: datetime


class PreviewIn(StrictModel):
    channel: Channel = "sms"
    body: str = Field(max_length=4000)
    subject: str = Field(default="", max_length=400)


class PreviewOut(BaseModel):
    body: str
    subject: str
    errors: list[str]
    characters: int
    sms_segments: int
    sample_values: dict[str, str]


class PlaceholderCatalog(BaseModel):
    allowed: dict[str, str]
    disallowed: list[str]
    sample_values: dict[str, str]
    rule: str


# --------------------------------------------------------------------- settings / overview
class CommsSettingsIn(StrictModel):
    monthly_spend_cap_paise: int | None = Field(default=None, ge=0, le=10**12)
    quiet_start_hour: int = Field(default=21, ge=0, le=23)
    quiet_end_hour: int = Field(default=8, ge=0, le=23)
    reminder_hours_ahead: int = Field(default=24, ge=1, le=168)
    reminder_channels: list[Channel] = ["sms"]


class CommsSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monthly_spend_cap_paise: int | None
    quiet_start_hour: int
    quiet_end_hour: int
    reminder_hours_ahead: int
    reminder_channels: list[str]
    updated_at: datetime


class ChannelUsage(BaseModel):
    channel: str
    entitled: bool
    provider: str
    mock: bool
    live: bool
    used: int
    limit: int | None
    cost_paise: int
    cost_per_message_paise: int


class ConsentStats(BaseModel):
    channel: str
    opted_in: int
    opted_out: int
    unknown: int


class CommsOverview(BaseModel):
    period: str
    live_enabled: bool
    mock_notice: str
    channels: list[ChannelUsage]
    spend_paise: int
    spend_cap_paise: int | None
    consent: list[ConsentStats]
    active_patients: int
    settings: CommsSettingsOut
    in_quiet_hours: bool


# --------------------------------------------------------------------- delivery log
class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel: str
    purpose: str
    language: str | None
    template_id: uuid.UUID | None
    patient_id: uuid.UUID | None
    appointment_id: uuid.UUID | None
    follow_up_id: uuid.UUID | None
    recipient_masked: str | None
    provider: str
    status: str
    cost_paise: int
    trigger: str
    error: str | None
    created_at: datetime


class DeliveryPage(BaseModel):
    items: list[DeliveryOut]
    total: int
    limit: int
    offset: int


class ReminderRunIn(StrictModel):
    hours_ahead: int | None = Field(default=None, ge=1, le=168)
    include_follow_ups: bool = True


class ReminderRunOut(BaseModel):
    window_start: datetime
    window_end: datetime
    channels: list[str]
    quiet_hours: bool
    appointments: int
    follow_ups: int
    sent: int
    by_status: dict[str, int]
    mock_notice: str


class SendResultOut(BaseModel):
    results: list[dict[str, str | int | None]]
    mock_notice: str


# --------------------------------------------------------------------- consent
class ConsentIn(StrictModel):
    channel: Channel
    status: ConsentStatus
    source: ConsentSource


class OptOutIn(StrictModel):
    channels: list[Channel] | None = None   # None = every channel
    source: ConsentSource = "patient_request"


class PreferencesIn(StrictModel):
    preferred_language: Language | None = None
    email: EmailStr | None = None


class ConsentOut(BaseModel):
    channel: str
    status: str | None
    source: str | None
    recorded_at: datetime | None
    actor_name: str | None


class ConsentEventOut(BaseModel):
    channel: str
    status: str
    source: str
    recorded_at: datetime
    actor_name: str | None


class PatientCommsOut(BaseModel):
    patient_id: uuid.UUID
    preferred_language: str | None
    email: str | None
    phone_masked: str | None
    consents: list[ConsentOut]
    history: list[ConsentEventOut]


# --------------------------------------------------------------------- follow-ups
class FollowUpIn(StrictModel):
    patient_id: uuid.UUID
    due_date: date
    reason: str = Field(min_length=2, max_length=80)
    branch_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        if not _REASON_RE.match(v):
            raise ValueError("reason: a short label (letters, digits, basic punctuation)")
        return v


class FollowUpActionIn(StrictModel):
    note: str = Field(default="", max_length=200)


class FollowUpBookIn(StrictModel):
    appointment_id: uuid.UUID
    note: str = Field(default="", max_length=200)


class FollowUpOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    patient_uhid: str
    branch_id: uuid.UUID | None
    due_date: date
    reason: str
    status: str
    bucket: str
    assigned_user_id: uuid.UUID | None
    assigned_name: str | None
    created_by_name: str | None
    appointment_id: uuid.UUID | None
    appointment_starts_at: datetime | None
    status_note: str
    reminded_at: datetime | None
    closed_at: datetime | None
    created_at: datetime


class MissedAppointmentOut(BaseModel):
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    patient_uhid: str
    starts_at: datetime
    status: str
    provider_name: str | None
    notified: bool
    open_follow_up_id: uuid.UUID | None


class NotifyIn(StrictModel):
    channels: list[Channel] | None = None


TEMPLATE_RULE = (
    "Messages carry logistics only (first name, clinic, date/time, doctor). Never include "
    "diagnoses, conditions, medicines, test results, allergies, appointment reasons or "
    "clinical notes — those placeholders are rejected and must not be typed as free text.")


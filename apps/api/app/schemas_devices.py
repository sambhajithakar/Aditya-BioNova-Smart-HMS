"""M8.2 medical device API schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .schemas import StrictModel

DeviceKind = Literal["bp_monitor", "pulse_oximeter"]
Surface = Literal["web", "android"]

# A Bluetooth device address, or the simulator's own "SIM-XXXXXXXX" ids
_ADDRESS_RE = r"^(([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}|SIM-[0-9A-Fa-f]{8})$"


class DeviceIn(StrictModel):
    kind: DeviceKind
    label: str = Field(min_length=2, max_length=80)
    ble_address: str = Field(pattern=_ADDRESS_RE)
    manufacturer: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=80)
    serial: str = Field(default="", max_length=80)
    firmware: str = Field(default="", max_length=40)
    branch_id: uuid.UUID | None = None
    is_simulator: bool = False


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    label: str
    manufacturer: str
    model: str
    serial: str
    firmware: str
    branch_id: uuid.UUID | None
    is_simulator: bool
    status: str
    created_at: datetime
    retired_at: datetime | None
    # no model is validated on hardware yet (docs/DEVICE_SUPPORT.md)
    hardware_validated: bool = False


class ReadingIn(StrictModel):
    capture_id: uuid.UUID
    device_id: uuid.UUID
    ble_address: str = Field(pattern=_ADDRESS_RE)
    encounter_id: uuid.UUID
    characteristic: Literal["2a35", "2a5e", "2a5f"]
    raw_hex: str = Field(min_length=2, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    source: Literal["ble", "simulator"]
    captured_at: datetime
    app_version: str = Field(default="", max_length=40)
    # what the phone showed the clinician; must match the server's parse
    client_parsed: dict | None = None

    @field_validator("captured_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("captured_at must carry a time zone")
        return v


class DecisionOut(BaseModel):
    decision: str
    reason: str
    surface: str
    vitals_id: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime


class ReadingOut(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    device_label: str
    device_is_simulator: bool
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    capture_id: uuid.UUID
    kind: str
    characteristic: str
    values: dict
    exact: dict
    unit: str
    flags: list[str]
    raw_hex: str
    raw_sha256: str
    source: str
    device_time: datetime | None
    captured_at: datetime
    received_at: datetime
    clock_skew: bool
    captured_by: uuid.UUID | None
    app_version: str
    status: Literal["pending_review", "accepted", "rejected"]
    decision: DecisionOut | None


class AcceptIn(StrictModel):
    surface: Surface
    note: str = Field(default="", max_length=200)
    # the reviewer confirms the reading belongs to this patient, now
    confirm_patient: bool


class RejectIn(StrictModel):
    surface: Surface
    reason: str = Field(min_length=3, max_length=300)

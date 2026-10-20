"""Read-only slot suggestions from branch working hours + the clinic's
appointment schedule settings (slot length, max per slot).

This does NOT change booking semantics: ``POST /appointments`` still accepts
any window and still rejects provider overlaps. With a provider, a slot is
available only when that provider has no active appointment overlapping it
(the same rule booking enforces); without one, ``max_per_slot`` caps the
branch-wide count of active appointments in the slot.

Included in main.py BEFORE the appointments router so ``/appointments/slots``
is not captured by ``/appointments/{appointment_id}``.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, require_permission
from ..models import Appointment
from ..schemas_setup import SlotOut, SlotsOut
from ..services.setup_rules import generate_slots
from ..services.tenancy import load_branch, require_member
from ..timeutil import clinic_day_bounds, clinic_tz
from .setup import branch_sessions, load_settings_row, settings_doc

router = APIRouter(prefix="/appointments", tags=["appointments"])

_ACTIVE = ("scheduled", "checked_in")


@router.get("/slots", response_model=SlotsOut)
def suggest_slots(
    branch_id: uuid.UUID,
    date: date,  # noqa: A002 - public query parameter name
    provider_user_id: uuid.UUID | None = None,
    principal: Principal = Depends(require_permission("appointment.read")),
    db: Session = Depends(get_db, scope="function"),
) -> SlotsOut:
    load_branch(db, principal, branch_id)
    if provider_user_id is not None:
        require_member(db, principal, provider_user_id, field="provider_user_id")
    schedule = settings_doc(load_settings_row(db, principal.organization_id)).schedule
    sessions = branch_sessions(db, principal.organization_id, branch_id)
    windows = generate_slots(date, sessions, schedule.slot_minutes, clinic_tz())

    day_start, day_end = clinic_day_bounds(date)
    cond = [Appointment.organization_id == principal.organization_id,
            Appointment.status.in_(_ACTIVE),
            Appointment.starts_at < day_end, Appointment.ends_at > day_start]
    if provider_user_id is not None:
        cond.append(Appointment.provider_user_id == provider_user_id)
    else:
        cond.append(Appointment.branch_id == branch_id)
    booked = db.execute(select(Appointment.starts_at, Appointment.ends_at).where(*cond)).all()

    capacity = 1 if provider_user_id is not None else schedule.max_per_slot
    slots = []
    for start, end in windows:
        n = sum(1 for b_start, b_end in booked if b_start < end and b_end > start)
        slots.append(SlotOut(starts_at=start, ends_at=end, booked=n, available=n < capacity))
    return SlotsOut(branch_id=branch_id, date=date, provider_user_id=provider_user_id,
                    configured=bool(sessions), slot_minutes=schedule.slot_minutes,
                    max_per_slot=schedule.max_per_slot, slots=slots)

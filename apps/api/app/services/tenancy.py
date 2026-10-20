"""Tenant checks for client-supplied foreign ids (M7.0).

PostgreSQL foreign-key checks BYPASS row-level security: an INSERT that
references another tenant's branch/encounter/appointment UUID would succeed
even though RLS hides that row from every SELECT. Every id a client sends
must therefore be loaded through the request's RLS-scoped session (plus an
explicit ``organization_id`` filter) before it is written anywhere. An id
that is not visible is reported exactly like a non-existent one (404), so
the response never confirms that another tenant's record exists.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import Principal
from ..models import Appointment, Branch, Encounter, Membership


def load_branch(
    db: Session, principal: Principal, branch_id: uuid.UUID, *, active: bool = True
) -> Branch:
    row = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.organization_id == principal.organization_id,
        )
    )
    if row is None or (active and row.status != "active"):
        raise HTTPException(status_code=404, detail="Branch not found or inactive")
    return row


def load_encounter(
    db: Session,
    principal: Principal,
    encounter_id: uuid.UUID,
    *,
    patient_id: uuid.UUID | None = None,
) -> Encounter:
    row = db.scalar(
        select(Encounter).where(
            Encounter.id == encounter_id,
            Encounter.organization_id == principal.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Encounter not found")
    if patient_id is not None and row.patient_id != patient_id:
        raise HTTPException(
            status_code=422, detail="Encounter belongs to another patient"
        )
    return row


def load_appointment(
    db: Session,
    principal: Principal,
    appointment_id: uuid.UUID,
    *,
    patient_id: uuid.UUID | None = None,
) -> Appointment:
    row = db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.organization_id == principal.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if patient_id is not None and row.patient_id != patient_id:
        raise HTTPException(
            status_code=422, detail="Appointment belongs to another patient"
        )
    return row


def require_member(
    db: Session, principal: Principal, user_id: uuid.UUID, *, field: str
) -> None:
    """``user_id`` must be an ACTIVE member of the caller's organization."""
    found = db.scalar(
        select(Membership.id).where(
            Membership.user_id == user_id,
            Membership.organization_id == principal.organization_id,
            Membership.status == "active",
        )
    )
    if found is None:
        raise HTTPException(
            status_code=422,
            detail=f"{field} is not an active member of this organization",
        )

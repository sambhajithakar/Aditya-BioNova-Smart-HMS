"""Smart Patient QR Check-In (privacy-preserving).

* The QR shown / printed / shared for an appointment contains ONLY an opaque
  random 128-bit token (base32). No name, phone, UHID, clinic or appointment
  identifier is encoded — a lost or photographed QR reveals nothing.
* Only ``sha256`` of the token is stored, bound to one organization and one
  appointment, expiring at the end of the appointment's clinic day, single
  use. Re-issuing revokes the previous live token.
* Every route needs an authenticated staff session with ``checkin.manage``.
  The tenant comes from that session; a token belonging to another clinic is
  simply not visible under RLS and answers the same generic 404 as a code
  that never existed.
* Confirmation is idempotent and race-safe: the token row is locked
  ``FOR UPDATE``; a second scan returns the queue token already issued with
  ``already_checked_in``. The queue entry itself is allocated by the shared
  OPD-queue logic (same per-day advisory lock, same uniqueness backstops).
* Verification attempts are rate limited per staff member.
* Kiosk mode (``POST /checkin/kiosk``) is for a reception-owned device in a
  staff session: it confirms and returns ONLY the queue token number, so
  nothing about the patient is shown on a patient-facing screen.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ratelimit
from ..auditing import record_event, record_security_event
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..models import Appointment, Branch, OpdQueueEntry, Patient
from ..models_setup import CheckinToken
from ..schemas_setup import (
    CheckinCodeIn,
    CheckinConfirmOut,
    CheckinIssueOut,
    CheckinQueueOut,
    CheckinVerifyOut,
    KioskCheckinOut,
)
from ..services.setup_rules import hash_checkin_token, new_checkin_token, normalize_checkin_code
from ..services.tenancy import load_appointment
from ..timeutil import clinic_day_bounds, clinic_today, clinic_tz
from .opd_queue import issue_queue_entry, lock_service_day

router = APIRouter(prefix="/checkin", tags=["checkin"])

_ACTIVE_QUEUE = ("waiting", "called", "in_consultation")
_NOT_FOUND = "Check-in code not found"


def _verify_limit() -> int:
    """Attempts per staff member per minute (env ``RL_CHECKIN_PER_USER``)."""
    try:
        return max(1, int(os.environ.get("RL_CHECKIN_PER_USER", "60")))
    except ValueError:
        return 60


def _throttle(principal: Principal) -> None:
    ratelimit.hit("checkin", f"{principal.organization_id}:{principal.user_id}",
                  limit=_verify_limit(), window_seconds=60)


def _audit(db: Session, principal: Principal, request: Request, action: str,
           resource_id: str, metadata: dict | None = None) -> None:
    record_event(
        db, action=action, organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id), resource_type="appointment",
        resource_id=resource_id, metadata=metadata,
        correlation_id=get_correlation_id(request), ip_address=get_client_ip(request),
    )


@contextmanager
def _failures_audited(principal: Principal, request: Request, step: str):
    """Rejected codes end in a rollback, so they are audited in their own
    transaction (the code itself is never logged)."""
    try:
        yield
    except HTTPException as exc:
        if exc.status_code in (404, 409, 410):
            record_security_event(
                action="checkin.rejected", organization_id=str(principal.organization_id),
                actor_user_id=str(principal.user_id), resource_type="checkin",
                metadata={"step": step, "status": exc.status_code,
                          "reason": str(exc.detail)[:120]},
                correlation_id=get_correlation_id(request), ip_address=get_client_ip(request))
        raise


def _appointment_day(appt: Appointment):
    return appt.starts_at.astimezone(clinic_tz()).date()


# --- issue ---------------------------------------------------------------------------
@router.post("/appointments/{appointment_id}/token", response_model=CheckinIssueOut,
             status_code=status.HTTP_201_CREATED)
def issue_token(
    appointment_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission("checkin.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> CheckinIssueOut:
    """Create (or replace) the appointment's check-in QR token. The raw token
    is returned once; only its hash is kept."""
    appt = load_appointment(db, principal, appointment_id)
    appt = db.scalars(select(Appointment).where(Appointment.id == appt.id)
                      .with_for_update().execution_options(populate_existing=True)).one()
    if appt.status not in ("scheduled", "checked_in"):
        raise HTTPException(status_code=409,
                            detail=f"Cannot issue a check-in code for a {appt.status} "
                                   "appointment")
    used = db.scalar(select(CheckinToken.id).where(
        CheckinToken.appointment_id == appt.id, CheckinToken.used_at.is_not(None)))
    if used is not None:
        raise HTTPException(status_code=409, detail="Patient is already checked in")
    _, day_end = clinic_day_bounds(_appointment_day(appt))
    now = datetime.now(timezone.utc)
    if day_end <= now:
        raise HTTPException(status_code=409, detail="The appointment day has passed")

    revoked = 0
    for live in db.scalars(select(CheckinToken).where(
            CheckinToken.appointment_id == appt.id, CheckinToken.used_at.is_(None),
            CheckinToken.revoked_at.is_(None))).all():
        live.revoked_at = now
        revoked += 1
    db.flush()

    raw, digest = new_checkin_token()
    row = CheckinToken(organization_id=principal.organization_id, appointment_id=appt.id,
                       token_hash=digest, expires_at=day_end, created_by=principal.user_id)
    db.add(row)
    db.flush()
    _audit(db, principal, request, "checkin.token_issued", str(appt.id),
           {"token_id": str(row.id), "expires_at": day_end.isoformat(),
            "replaced": revoked})
    return CheckinIssueOut(appointment_id=appt.id, token=raw, expires_at=day_end)


# --- verify / confirm -------------------------------------------------------------
def _load_token(db: Session, principal: Principal, code: str, *,
                lock: bool) -> CheckinToken:
    raw = normalize_checkin_code(code)
    if raw is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    stmt = select(CheckinToken).where(
        CheckinToken.token_hash == hash_checkin_token(raw),
        # RLS already hides other clinics' tokens; the explicit filter keeps
        # the behaviour identical even under a privileged connection
        CheckinToken.organization_id == principal.organization_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalars(stmt.execution_options(populate_existing=True)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return row


def _usable(db: Session, token: CheckinToken) -> Appointment:
    """The token's appointment, or a clear error why it cannot check in."""
    if token.revoked_at is not None:
        raise HTTPException(status_code=410,
                            detail="This check-in code was replaced by a newer one")
    now = datetime.now(timezone.utc)
    if token.expires_at <= now:
        raise HTTPException(status_code=410, detail="This check-in code has expired")
    appt = db.get(Appointment, token.appointment_id)
    if appt is None:  # pragma: no cover - FK cascade
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if appt.status == "cancelled":
        raise HTTPException(status_code=409, detail="This appointment was cancelled")
    if appt.status in ("completed", "no_show"):
        raise HTTPException(status_code=409,
                            detail=f"This appointment is already {appt.status.replace('_', '-')}")
    if _appointment_day(appt) != clinic_today():
        raise HTTPException(status_code=409,
                            detail="Check-in opens on the day of the appointment")
    return appt


def _queue_out(entry: OpdQueueEntry) -> CheckinQueueOut:
    return CheckinQueueOut(id=entry.id, token_number=entry.token_number, status=entry.status,
                           service_date=entry.service_date)


@router.post("/verify", response_model=CheckinVerifyOut)
def verify(
    payload: CheckinCodeIn,
    request: Request,
    principal: Principal = Depends(require_permission("checkin.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> CheckinVerifyOut:
    """Look a scanned code up WITHOUT checking in: minimal context so staff
    can confirm the patient's identity verbally before confirming."""
    _throttle(principal)
    with _failures_audited(principal, request, "verify"):
        token = _load_token(db, principal, payload.code, lock=False)
        queue_number = None
        if token.used_at is not None:
            appt = db.get(Appointment, token.appointment_id)
            entry = (db.get(OpdQueueEntry, token.queue_entry_id)
                     if token.queue_entry_id else None)
            queue_number = entry.token_number if entry else None
            result = "already_checked_in"
        else:
            appt = _usable(db, token)
            result = "ready"
    patient = db.get(Patient, appt.patient_id)
    branch = db.get(Branch, appt.branch_id)
    _audit(db, principal, request, "checkin.verified", str(appt.id),
           {"token_id": str(token.id), "result": result})
    return CheckinVerifyOut(
        status=result, appointment_id=appt.id,
        patient_display_name=patient.full_name if patient else "",
        appointment_starts_at=appt.starts_at, branch_name=branch.name if branch else "",
        queue_token_number=queue_number)


def _confirm(db: Session, principal: Principal, request: Request,
             code: str) -> tuple[str, uuid.UUID, OpdQueueEntry]:
    # Lock order, as in issue_token: the appointment first, then its token.
    # Locking the token first could deadlock against a concurrent re-issue.
    token = _load_token(db, principal, code, lock=False)
    db.execute(select(Appointment.id).where(Appointment.id == token.appointment_id)
               .with_for_update())
    token = _load_token(db, principal, code, lock=True)
    if token.used_at is not None:
        entry = db.get(OpdQueueEntry, token.queue_entry_id) if token.queue_entry_id else None
        if entry is None:  # queue row removed afterwards: still a used code
            raise HTTPException(status_code=409, detail="Patient is already checked in")
        _audit(db, principal, request, "checkin.duplicate", str(token.appointment_id),
               {"token_id": str(token.id), "queue_token": entry.token_number})
        return "already_checked_in", token.appointment_id, entry

    appt = _usable(db, token)
    appt = db.scalars(select(Appointment).where(Appointment.id == appt.id)
                      .with_for_update().execution_options(populate_existing=True)).one()
    today = clinic_today()
    lock_service_day(db, principal.organization_id, today)
    # already queued today (e.g. added at the desk before the QR was scanned):
    # attach to that entry instead of issuing a second token. A patient has at
    # most one active queue entry per day; if it is at ANOTHER branch, say so
    # rather than silently checking them in where they are not (M8.1).
    entry = db.scalar(select(OpdQueueEntry).where(
        OpdQueueEntry.organization_id == principal.organization_id,
        OpdQueueEntry.patient_id == appt.patient_id,
        OpdQueueEntry.service_date == today,
        OpdQueueEntry.status.in_(_ACTIVE_QUEUE),
    ).order_by(OpdQueueEntry.token_number))
    if entry is not None and entry.branch_id != appt.branch_id:
        raise HTTPException(
            status_code=409,
            detail="Patient is already in today's queue at another branch; complete or "
                   "cancel that visit before checking in here")
    reused = entry is not None
    if entry is None:
        entry = issue_queue_entry(db, principal, request, patient_id=appt.patient_id,
                                  branch_id=appt.branch_id, appointment_id=appt.id)
    now = datetime.now(timezone.utc)
    token.used_at = now
    token.used_by = principal.user_id
    token.queue_entry_id = entry.id
    if appt.status == "scheduled":
        appt.status = "checked_in"
    db.flush()
    _audit(db, principal, request, "checkin.confirmed", str(appt.id),
           {"token_id": str(token.id), "queue_entry_id": str(entry.id),
            "queue_token": entry.token_number, "reused_queue_entry": reused})
    return "checked_in", appt.id, entry


@router.post("/confirm", response_model=CheckinConfirmOut)
def confirm(
    payload: CheckinCodeIn,
    request: Request,
    principal: Principal = Depends(require_permission("checkin.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> CheckinConfirmOut:
    _throttle(principal)
    with _failures_audited(principal, request, "confirm"):
        result, appointment_id, entry = _confirm(db, principal, request, payload.code)
    return CheckinConfirmOut(status=result, appointment_id=appointment_id,
                             queue_entry=_queue_out(entry))


@router.post("/kiosk", response_model=KioskCheckinOut)
def kiosk(
    payload: CheckinCodeIn,
    request: Request,
    principal: Principal = Depends(require_permission("checkin.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> KioskCheckinOut:
    """Self check-in on a reception-owned kiosk: confirm and show ONLY the
    queue number. Errors are generic so nothing is learned from a code."""
    _throttle(principal)
    try:
        with _failures_audited(principal, request, "kiosk"):
            result, _, entry = _confirm(db, principal, request, payload.code)
    except HTTPException as exc:
        if exc.status_code in (404, 409, 410):
            raise HTTPException(status_code=exc.status_code,
                                detail="Please see the reception desk") from None
        raise
    return KioskCheckinOut(status=result, token_number=entry.token_number)

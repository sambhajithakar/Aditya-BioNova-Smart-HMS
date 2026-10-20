"""Follow-up CRM (clinician-directed recalls) and missed-appointment tracking.

* A clinician (``followup.create``) plans a follow-up: patient, due date and a
  short NON-clinical label ("Review visit", "Dressing change"). The label is
  for the worklist only and never appears in a patient message.
* Reception / doctors (``followup.write``) move it along:
  planned → reminded → booked → completed, or missed / cancelled.
  Booking links an appointment of the same patient.
* Missed appointments: past start (+30 min grace) and never checked in
  (status still ``scheduled`` or ``no_show``). An optional "we missed you"
  message is consent-, quota- and quiet-hours-aware like every other send.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..comms import engine
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..models import Appointment, Patient, User
from ..models_comms import CommsDelivery, FollowUp
from ..schemas_comms import (
    FollowUpActionIn,
    FollowUpBookIn,
    FollowUpIn,
    FollowUpOut,
    MissedAppointmentOut,
    NotifyIn,
    SendResultOut,
)
from ..services.tenancy import load_branch, require_member
from .comms import mock_notice

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"])

OPEN = ("planned", "reminded", "booked", "missed")
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "planned": ("reminded", "booked", "completed", "missed", "cancelled"),
    "reminded": ("booked", "completed", "missed", "cancelled"),
    "booked": ("completed", "missed", "cancelled"),
    "missed": ("reminded", "booked", "cancelled"),
    "completed": (),
    "cancelled": (),
}


def _today(db: Session, org_id: uuid.UUID) -> date:
    from ..models import Organization

    return engine.utcnow().astimezone(engine.org_tz(db.get(Organization, org_id))).date()


def bucket(fu: FollowUp, today: date) -> str:
    if fu.status in ("completed", "cancelled"):
        return "closed"
    if fu.due_date < today:
        return "overdue"
    if fu.due_date == today:
        return "due_today"
    return "upcoming"


def _audit(db, principal, request, action, fu: FollowUp, meta: dict | None = None) -> None:
    record_event(db, action=action, organization_id=str(principal.organization_id),
                 actor_user_id=str(principal.user_id), resource_type="follow_up",
                 resource_id=str(fu.id),
                 metadata={"patient_id": str(fu.patient_id), "status": fu.status,
                           **(meta or {})},
                 correlation_id=get_correlation_id(request), ip_address=get_client_ip(request))


def _out(db: Session, rows: list[FollowUp], today: date) -> list[FollowUpOut]:
    pids = {r.patient_id for r in rows}
    patients = {p.id: p for p in db.scalars(select(Patient).where(Patient.id.in_(pids))).all()} \
        if pids else {}
    uids = {u for r in rows for u in (r.assigned_user_id, r.created_by) if u}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(uids))).all()) \
        if uids else {}
    aids = {r.appointment_id for r in rows if r.appointment_id}
    appts = dict(db.execute(select(Appointment.id, Appointment.starts_at)
                            .where(Appointment.id.in_(aids))).all()) if aids else {}
    out = []
    for r in rows:
        p = patients.get(r.patient_id)
        out.append(FollowUpOut(
            id=r.id, patient_id=r.patient_id, patient_name=p.full_name if p else "—",
            patient_uhid=p.uhid if p else "—", branch_id=r.branch_id, due_date=r.due_date,
            reason=r.reason, status=r.status, bucket=bucket(r, today),
            assigned_user_id=r.assigned_user_id, assigned_name=names.get(r.assigned_user_id),
            created_by_name=names.get(r.created_by), appointment_id=r.appointment_id,
            appointment_starts_at=appts.get(r.appointment_id), status_note=r.status_note,
            reminded_at=r.reminded_at, closed_at=r.closed_at, created_at=r.created_at))
    return out


def _load(db: Session, principal: Principal, fu_id: uuid.UUID) -> FollowUp:
    fu = db.get(FollowUp, fu_id)
    if fu is None or fu.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return fu


def _patient(db: Session, principal: Principal, patient_id: uuid.UUID) -> Patient:
    p = db.scalar(select(Patient).where(Patient.id == patient_id,
                                        Patient.organization_id == principal.organization_id))
    if p is None or p.status == "merged":
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


def _move(fu: FollowUp, to: str, note: str = "") -> None:
    if to not in TRANSITIONS[fu.status]:
        raise HTTPException(status_code=409,
                            detail=f"Cannot change a {fu.status} follow-up to {to}")
    now = engine.utcnow()
    fu.status, fu.updated_at = to, now
    if note:
        fu.status_note = note
    if to in ("completed", "cancelled"):
        fu.closed_at = now
    if to == "reminded":
        fu.reminded_at = now


# --------------------------------------------------------------------- worklist
@router.get("", response_model=list[FollowUpOut])
def list_follow_ups(
    bucket_filter: str | None = Query(default=None, alias="bucket"),
    status_filter: str | None = Query(default=None, alias="status"),
    patient_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    principal: Principal = Depends(require_permission("followup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> list[FollowUpOut]:
    org_id = principal.organization_id
    today = _today(db, org_id)
    conds = [FollowUp.organization_id == org_id]
    if patient_id:
        conds.append(FollowUp.patient_id == patient_id)
    if status_filter:
        if status_filter not in TRANSITIONS:
            raise HTTPException(status_code=422, detail="Unknown status filter")
        conds.append(FollowUp.status == status_filter)
    if bucket_filter:
        if bucket_filter not in ("due_today", "overdue", "upcoming", "open", "closed"):
            raise HTTPException(status_code=422, detail="Unknown bucket")
        if bucket_filter == "closed":
            conds.append(FollowUp.status.in_(("completed", "cancelled")))
        else:
            conds.append(FollowUp.status.in_(OPEN))
            if bucket_filter == "due_today":
                conds.append(FollowUp.due_date == today)
            elif bucket_filter == "overdue":
                conds.append(FollowUp.due_date < today)
            elif bucket_filter == "upcoming":
                conds.append(FollowUp.due_date > today)
    rows = db.scalars(select(FollowUp).where(*conds)
                      .order_by(FollowUp.due_date, FollowUp.created_at).limit(limit)).all()
    return _out(db, list(rows), today)


@router.get("/summary")
def summary(
    principal: Principal = Depends(require_permission("followup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, int]:
    org_id = principal.organization_id
    today = _today(db, org_id)
    base = select(func.count()).select_from(FollowUp).where(
        FollowUp.organization_id == org_id, FollowUp.status.in_(OPEN))
    return {
        "due_today": db.scalar(base.where(FollowUp.due_date == today)) or 0,
        "overdue": db.scalar(base.where(FollowUp.due_date < today)) or 0,
        "upcoming": db.scalar(base.where(FollowUp.due_date > today)) or 0,
        "missed_appointments": len(engine.missed_appointments(db, org_id)),
    }


@router.post("", response_model=FollowUpOut, status_code=status.HTTP_201_CREATED)
def create_follow_up(
    payload: FollowUpIn,
    request: Request,
    principal: Principal = Depends(require_permission("followup.create")),
    db: Session = Depends(get_db, scope="function"),
) -> FollowUpOut:
    patient = _patient(db, principal, payload.patient_id)
    today = _today(db, principal.organization_id)
    if payload.due_date < today:
        raise HTTPException(status_code=422, detail="due_date must not be in the past")
    if payload.branch_id:
        load_branch(db, principal, payload.branch_id)
    assigned = payload.assigned_user_id or principal.user_id
    if payload.assigned_user_id:
        require_member(db, principal, payload.assigned_user_id, field="assigned_user_id")
    fu = FollowUp(organization_id=principal.organization_id, patient_id=patient.id,
                  branch_id=payload.branch_id, due_date=payload.due_date,
                  reason=payload.reason, assigned_user_id=assigned,
                  created_by=principal.user_id)
    db.add(fu)
    db.flush()
    db.refresh(fu)
    _audit(db, principal, request, "followup.created", fu, {"due_date": str(fu.due_date)})
    return _out(db, [fu], today)[0]


# --------------------------------------------------------------------- missed appointments
# (declared before /{follow_up_id} so the literal path wins)
@router.get("/missed-appointments", response_model=list[MissedAppointmentOut])
def missed(
    days: int = Query(default=7, ge=1, le=90),
    principal: Principal = Depends(require_permission("followup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> list[MissedAppointmentOut]:
    org_id = principal.organization_id
    appts = engine.missed_appointments(db, org_id, days=days)
    pids = {a.patient_id for a in appts}
    patients = {p.id: p for p in db.scalars(select(Patient).where(Patient.id.in_(pids))).all()} \
        if pids else {}
    uids = {a.provider_user_id for a in appts if a.provider_user_id}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(uids))).all()) \
        if uids else {}
    aids = [a.id for a in appts]
    notified = set(db.scalars(select(CommsDelivery.appointment_id).where(
        CommsDelivery.organization_id == org_id, CommsDelivery.appointment_id.in_(aids),
        CommsDelivery.purpose == "missed_appointment",
        CommsDelivery.status.in_(engine.DELIVERED_STATUSES))).all()) if aids else set()
    open_fu = dict(db.execute(select(FollowUp.patient_id, FollowUp.id).where(
        FollowUp.organization_id == org_id, FollowUp.patient_id.in_(pids),
        FollowUp.status.in_(OPEN))).all()) if pids else {}
    return [MissedAppointmentOut(
        appointment_id=a.id, patient_id=a.patient_id,
        patient_name=patients[a.patient_id].full_name if a.patient_id in patients else "—",
        patient_uhid=patients[a.patient_id].uhid if a.patient_id in patients else "—",
        starts_at=a.starts_at, status=a.status, provider_name=names.get(a.provider_user_id),
        notified=a.id in notified, open_follow_up_id=open_fu.get(a.patient_id))
        for a in appts]


@router.post("/missed-appointments/{appointment_id}/notify", response_model=SendResultOut)
def notify_missed(
    appointment_id: uuid.UUID,
    payload: NotifyIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.send")),
    db: Session = Depends(get_db, scope="function"),
) -> SendResultOut:
    org_id = principal.organization_id
    appt = next((a for a in engine.missed_appointments(db, org_id, days=90)
                 if a.id == appointment_id), None)
    if appt is None:
        raise HTTPException(status_code=404, detail="Missed appointment not found")
    patient = db.get(Patient, appt.patient_id)
    ctx = engine.load_ctx(db, org_id, principal.user_id)
    channels = engine.channels_for(ctx, payload.channels)
    if not channels:
        raise HTTPException(status_code=409, detail="No communication channel is enabled")
    results = []
    for c in channels:
        o = engine.deliver(db, ctx, patient=patient, channel=c, purpose="missed_appointment",
                           appointment=appt, actor_user_id=principal.user_id,
                           correlation_id=get_correlation_id(request),
                           dedupe_scope=f"missed:{appt.id}")
        results.append({"channel": c, "status": o.status, "log_id": o.log_id})
    record_event(db, action="comms.missed_notified", organization_id=str(org_id),
                 actor_user_id=str(principal.user_id), resource_type="appointment",
                 resource_id=str(appt.id), metadata={"results": [r["status"] for r in results]},
                 correlation_id=get_correlation_id(request), ip_address=get_client_ip(request))
    return SendResultOut(results=results, mock_notice=mock_notice())


# --------------------------------------------------------------------- one follow-up
@router.get("/{follow_up_id}", response_model=FollowUpOut)
def get_follow_up(
    follow_up_id: uuid.UUID,
    principal: Principal = Depends(require_permission("followup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> FollowUpOut:
    fu = _load(db, principal, follow_up_id)
    return _out(db, [fu], _today(db, principal.organization_id))[0]


@router.post("/{follow_up_id}/book", response_model=FollowUpOut)
def book(
    follow_up_id: uuid.UUID,
    payload: FollowUpBookIn,
    request: Request,
    principal: Principal = Depends(require_permission("followup.write")),
    db: Session = Depends(get_db, scope="function"),
) -> FollowUpOut:
    fu = _load(db, principal, follow_up_id)
    appt = db.scalar(select(Appointment).where(
        Appointment.id == payload.appointment_id,
        Appointment.organization_id == principal.organization_id))
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.patient_id != fu.patient_id:
        raise HTTPException(status_code=422, detail="Appointment belongs to another patient")
    if appt.status in ("cancelled", "completed", "no_show"):
        raise HTTPException(status_code=409, detail=f"Appointment is {appt.status}")
    _move(fu, "booked", payload.note)
    fu.appointment_id = appt.id
    db.flush()
    _audit(db, principal, request, "followup.booked", fu, {"appointment_id": str(appt.id)})
    return _out(db, [fu], _today(db, principal.organization_id))[0]


def _simple(to: str):
    def endpoint(
        follow_up_id: uuid.UUID,
        payload: FollowUpActionIn,
        request: Request,
        principal: Principal = Depends(require_permission("followup.write")),
        db: Session = Depends(get_db, scope="function"),
    ) -> FollowUpOut:
        fu = _load(db, principal, follow_up_id)
        _move(fu, to, payload.note)
        db.flush()
        _audit(db, principal, request, f"followup.{to}", fu)
        return _out(db, [fu], _today(db, principal.organization_id))[0]

    endpoint.__name__ = f"follow_up_{to}"
    return endpoint


for _action, _to in (("complete", "completed"), ("cancel", "cancelled"), ("missed", "missed")):
    router.add_api_route(f"/{{follow_up_id}}/{_action}", _simple(_to), methods=["POST"],
                         response_model=FollowUpOut, name=f"follow_up_{_action}")


@router.post("/{follow_up_id}/remind", response_model=SendResultOut)
def remind(
    follow_up_id: uuid.UUID,
    payload: NotifyIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.send")),
    db: Session = Depends(get_db, scope="function"),
) -> SendResultOut:
    fu = _load(db, principal, follow_up_id)
    if fu.status not in ("planned", "reminded", "missed"):
        raise HTTPException(status_code=409, detail=f"Cannot remind a {fu.status} follow-up")
    ctx = engine.load_ctx(db, principal.organization_id, principal.user_id)
    channels = engine.channels_for(ctx, payload.channels)
    if not channels:
        raise HTTPException(status_code=409, detail="No communication channel is enabled")
    patient = db.get(Patient, fu.patient_id)
    results, delivered = [], False
    for c in channels:
        o = engine.deliver(db, ctx, patient=patient, channel=c, purpose="follow_up",
                           follow_up=fu, actor_user_id=principal.user_id,
                           correlation_id=get_correlation_id(request),
                           dedupe_scope=f"fu:{fu.id}:{fu.due_date.isoformat()}")
        results.append({"channel": c, "status": o.status, "log_id": o.log_id})
        delivered = delivered or o.status in engine.DELIVERED_STATUSES
    if delivered and fu.status != "reminded":
        _move(fu, "reminded")
        db.flush()
    _audit(db, principal, request, "followup.remind", fu,
           {"results": [r["status"] for r in results]})
    return SendResultOut(results=results, mock_notice=mock_notice())


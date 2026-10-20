"""BioNova Smart Setup Wizard: resumable, skippable first-run setup for clinic
owners / admins, and the clinic configuration it writes.

Step progress lives server-side (``org_settings.wizard``) so the wizard can
be resumed from any device. Steps that are backed by existing APIs (clinic
identity -> ``/organization``, branches -> ``/branches``, staff ->
``/members``, language -> ``/organization``, edition -> ``/subscription``)
are NOT duplicated here; this router only stores what is new: working hours,
the consultation fee master and the versioned settings document
(prescription template, clinic billing defaults, appointment schedule).

Clinic (patient) billing settings are deliberately separate from the SaaS
subscription — nothing here touches ``subscriptions``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..models import Branch, MemberInvitation, Membership, Organization
from ..models_setup import BranchWorkingHours, FeeSchedule, OrgSettings, PrinterProfile
from ..schemas_setup import (
    SETTINGS_SCHEMA_VERSION,
    WIZARD_STEPS,
    EffectiveFeeOut,
    FeeIn,
    FeeOut,
    FeesOut,
    OrgSettingsOut,
    OrgSettingsPatch,
    StepKey,
    WizardOut,
    WizardPatchIn,
    WizardStepIn,
    WizardStepOut,
    WorkingHoursIn,
    WorkingHoursOut,
    WorkingSessionOut,
)
from ..schemas_setup import OrgSettings as OrgSettingsDoc
from ..services.tenancy import load_branch, require_member

router = APIRouter(prefix="/setup", tags=["setup"])


def _audit(db: Session, principal: Principal, request: Request, action: str, *,
           resource_type: str = "org_settings", resource_id: str | None = None,
           metadata: dict | None = None) -> None:
    record_event(
        db, action=action, organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id), resource_type=resource_type,
        resource_id=resource_id or str(principal.organization_id), metadata=metadata,
        correlation_id=get_correlation_id(request), ip_address=get_client_ip(request),
    )


def load_settings_row(db: Session, org_id: uuid.UUID, *, lock: bool = False) -> OrgSettings:
    """The clinic's settings row, created on first use (race-safe)."""
    db.execute(
        text("INSERT INTO org_settings (organization_id) VALUES (:o) "
             "ON CONFLICT (organization_id) DO NOTHING"), {"o": str(org_id)})
    stmt = select(OrgSettings).where(OrgSettings.organization_id == org_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalars(stmt.execution_options(populate_existing=True)).one()


def settings_doc(row: OrgSettings) -> OrgSettingsDoc:
    """Stored document merged over defaults (older/partial rows stay valid)."""
    stored = dict(row.settings or {})
    stored["version"] = SETTINGS_SCHEMA_VERSION
    return OrgSettingsDoc.model_validate(stored)


# --- settings document -------------------------------------------------------------
@router.get("/settings", response_model=OrgSettingsOut)
def get_settings_doc(
    principal: Principal = Depends(require_permission("setup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> OrgSettingsOut:
    row = load_settings_row(db, principal.organization_id)
    return OrgSettingsOut(schema_version=row.schema_version, settings=settings_doc(row),
                          updated_at=row.updated_at)


@router.patch("/settings", response_model=OrgSettingsOut)
def patch_settings_doc(
    payload: OrgSettingsPatch,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> OrgSettingsOut:
    row = load_settings_row(db, principal.organization_id, lock=True)
    doc = settings_doc(row)
    changed, given = [], []
    for section in ("prescription", "billing", "schedule"):
        value = getattr(payload, section)
        if value is None:
            continue
        given.append(section)
        if value != getattr(doc, section):
            setattr(doc, section, value)
            changed.append(section)
    wizard = dict(row.wizard or {})
    saved = sorted(set(wizard.get("saved_sections", [])) | set(given))
    if changed or saved != wizard.get("saved_sections", []):
        # re-validate the whole document before it is stored
        doc = OrgSettingsDoc.model_validate(doc.model_dump())
        row.settings = doc.model_dump(mode="json")
        # accepting the pre-filled defaults counts as a conscious save
        wizard["saved_sections"] = saved
        row.wizard = wizard
        row.schema_version = SETTINGS_SCHEMA_VERSION
        row.updated_by = principal.user_id
        row.updated_at = datetime.now(timezone.utc)
        db.flush()
        _audit(db, principal, request, "setup.settings_updated",
               metadata={"sections": changed})
    return OrgSettingsOut(schema_version=row.schema_version, settings=doc,
                          updated_at=row.updated_at)


# --- wizard ------------------------------------------------------------------------
def _data_ready(db: Session, principal: Principal) -> dict[str, bool]:
    """Which steps the clinic's own data already satisfies."""
    org_id = principal.organization_id
    org = db.get(Organization, org_id)
    branches = db.scalar(select(func.count()).select_from(Branch).where(
        Branch.organization_id == org_id, Branch.status == "active")) or 0
    staff = db.scalar(select(func.count()).select_from(Membership).where(
        Membership.organization_id == org_id)) or 0
    invited = db.scalar(select(func.count()).select_from(MemberInvitation).where(
        MemberInvitation.organization_id == org_id)) or 0
    hours = db.scalar(select(func.count()).select_from(BranchWorkingHours).where(
        BranchWorkingHours.organization_id == org_id)) or 0
    fees = db.scalar(select(func.count()).select_from(FeeSchedule).where(
        FeeSchedule.organization_id == org_id)) or 0
    printers = db.scalar(select(func.count()).select_from(PrinterProfile).where(
        PrinterProfile.organization_id == org_id)) or 0
    row = load_settings_row(db, org_id)
    saved = set((row.wizard or {}).get("saved_sections", []))
    return {
        "identity": bool(org and org.address_line1 and org.city and org.phone),
        "branch": branches > 0,
        "staff": staff > 1 or invited > 0,
        "language": False,           # always a conscious choice (default "en")
        "working_hours": hours > 0,
        "fees": fees > 0,
        "prescription": "prescription" in saved,
        "billing": "billing" in saved,
        "printer": printers > 0,
        "schedule": "schedule" in saved,
        "edition": False,            # read-only review step
    }


def _wizard_out(db: Session, principal: Principal, row: OrgSettings) -> WizardOut:
    state = dict(row.wizard or {})
    marks: dict[str, str] = state.get("steps", {})
    ready = _data_ready(db, principal)
    steps = [WizardStepOut(key=k, status=marks.get(k, "todo"), data_ready=ready[k])
             for k in WIZARD_STEPS]
    handled = sum(1 for s in steps if s.status != "todo")
    current = state.get("current_step")
    if current not in WIZARD_STEPS:
        current = next((s.key for s in steps if s.status == "todo"), WIZARD_STEPS[0])
    finished_at = state.get("finished_at")
    finished = finished_at is not None
    return WizardOut(
        steps=steps, current_step=current, finished=finished,
        finished_at=datetime.fromisoformat(finished_at) if finished_at else None,
        should_show=("setup.manage" in principal.permissions) and not finished,
        progress_percent=round(100 * handled / len(WIZARD_STEPS)),
    )


@router.get("/wizard", response_model=WizardOut)
def get_wizard(
    principal: Principal = Depends(require_permission("setup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> WizardOut:
    return _wizard_out(db, principal, load_settings_row(db, principal.organization_id))


@router.post("/wizard/steps/{step_key}", response_model=WizardOut)
def mark_step(
    step_key: StepKey,
    payload: WizardStepIn,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> WizardOut:
    row = load_settings_row(db, principal.organization_id, lock=True)
    state = dict(row.wizard or {})
    steps = dict(state.get("steps", {}))
    if steps.get(step_key, "todo") != payload.status:
        steps[step_key] = payload.status
        state["steps"] = steps
        # move on to the next step still to do
        idx = WIZARD_STEPS.index(step_key)
        if payload.status != "todo":
            nxt = next((k for k in WIZARD_STEPS[idx + 1:] + WIZARD_STEPS[:idx]
                        if steps.get(k, "todo") == "todo"), step_key)
            state["current_step"] = nxt
        else:
            state["current_step"] = step_key
        row.wizard = state
        row.updated_by = principal.user_id
        row.updated_at = datetime.now(timezone.utc)
        db.flush()
        _audit(db, principal, request, "setup.wizard_step",
               metadata={"step": step_key, "status": payload.status})
    return _wizard_out(db, principal, row)


@router.patch("/wizard", response_model=WizardOut)
def patch_wizard(
    payload: WizardPatchIn,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> WizardOut:
    row = load_settings_row(db, principal.organization_id, lock=True)
    state = dict(row.wizard or {})
    meta: dict = {}
    if payload.current_step is not None:
        state["current_step"] = payload.current_step
    if payload.finished is True and not state.get("finished_at"):
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        meta["finished"] = True
    elif payload.finished is False and state.get("finished_at"):
        state["finished_at"] = None
        meta["reopened"] = True
    if state != (row.wizard or {}):
        row.wizard = state
        row.updated_by = principal.user_id
        row.updated_at = datetime.now(timezone.utc)
        db.flush()
        if meta:
            _audit(db, principal, request, "setup.wizard_" +
                   ("finished" if meta.get("finished") else "reopened"))
    return _wizard_out(db, principal, row)


# --- working hours -------------------------------------------------------------------
def _hours(db: Session, principal: Principal, branch_id: uuid.UUID) -> WorkingHoursOut:
    rows = db.scalars(select(BranchWorkingHours).where(
        BranchWorkingHours.organization_id == principal.organization_id,
        BranchWorkingHours.branch_id == branch_id,
    ).order_by(BranchWorkingHours.weekday, BranchWorkingHours.opens_at)).all()
    return WorkingHoursOut(branch_id=branch_id,
                           sessions=[WorkingSessionOut.model_validate(r) for r in rows])


@router.get("/branches/{branch_id}/working-hours", response_model=WorkingHoursOut)
def get_working_hours(
    branch_id: uuid.UUID,
    principal: Principal = Depends(require_permission("setup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> WorkingHoursOut:
    load_branch(db, principal, branch_id, active=False)
    return _hours(db, principal, branch_id)


@router.put("/branches/{branch_id}/working-hours", response_model=WorkingHoursOut)
def put_working_hours(
    branch_id: uuid.UUID,
    payload: WorkingHoursIn,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> WorkingHoursOut:
    """Replace the branch's whole week (validated: ranges, breaks, overlaps)."""
    load_branch(db, principal, branch_id)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
               {"k": f"hours:{principal.organization_id}:{branch_id}"})
    db.execute(delete(BranchWorkingHours).where(
        BranchWorkingHours.organization_id == principal.organization_id,
        BranchWorkingHours.branch_id == branch_id))
    for s in payload.sessions:
        db.add(BranchWorkingHours(organization_id=principal.organization_id,
                                  branch_id=branch_id, **s.model_dump()))
    db.flush()
    _audit(db, principal, request, "setup.working_hours_updated", resource_type="branch",
           resource_id=str(branch_id),
           metadata={"sessions": len(payload.sessions),
                     "days": sorted({s.weekday for s in payload.sessions})})
    return _hours(db, principal, branch_id)


def branch_sessions(db: Session, org_id: uuid.UUID, branch_id: uuid.UUID):
    from ..services.setup_rules import Session as Sess

    rows = db.scalars(select(BranchWorkingHours).where(
        BranchWorkingHours.organization_id == org_id,
        BranchWorkingHours.branch_id == branch_id)).all()
    return [Sess(r.weekday, r.opens_at, r.closes_at, r.break_starts_at, r.break_ends_at)
            for r in rows]


# --- consultation fees -------------------------------------------------------------
def _fee_row(db: Session, org_id: uuid.UUID, provider: uuid.UUID | None) -> FeeSchedule | None:
    cond = (FeeSchedule.provider_user_id.is_(None) if provider is None
            else FeeSchedule.provider_user_id == provider)
    return db.scalar(select(FeeSchedule).where(FeeSchedule.organization_id == org_id, cond))


def _upsert_fee(db: Session, principal: Principal, request: Request,
                provider: uuid.UUID | None, payload: FeeIn) -> FeeOut:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
               {"k": f"fee:{principal.organization_id}:{provider}"})
    row = _fee_row(db, principal.organization_id, provider)
    if row is None:
        row = FeeSchedule(organization_id=principal.organization_id, provider_user_id=provider)
        db.add(row)
    row.consultation_fee = payload.consultation_fee
    row.follow_up_fee = payload.follow_up_fee
    row.follow_up_valid_days = payload.follow_up_valid_days
    row.updated_by = principal.user_id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(row)
    _audit(db, principal, request, "setup.fee_updated", resource_type="fee_schedule",
           resource_id=str(row.id),
           metadata={"provider_user_id": str(provider) if provider else None,
                     "consultation_fee": str(payload.consultation_fee)})
    return FeeOut.model_validate(row)


@router.get("/fees", response_model=FeesOut)
def list_fees(
    principal: Principal = Depends(require_permission("setup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> FeesOut:
    rows = db.scalars(select(FeeSchedule).where(
        FeeSchedule.organization_id == principal.organization_id)
        .order_by(FeeSchedule.created_at)).all()
    default = next((r for r in rows if r.provider_user_id is None), None)
    return FeesOut(default=FeeOut.model_validate(default) if default else None,
                   providers=[FeeOut.model_validate(r) for r in rows
                              if r.provider_user_id is not None])


@router.put("/fees/default", response_model=FeeOut)
def put_default_fee(
    payload: FeeIn,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> FeeOut:
    return _upsert_fee(db, principal, request, None, payload)


@router.put("/fees/providers/{user_id}", response_model=FeeOut)
def put_provider_fee(
    user_id: uuid.UUID,
    payload: FeeIn,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> FeeOut:
    require_member(db, principal, user_id, field="user_id")
    return _upsert_fee(db, principal, request, user_id, payload)


@router.delete("/fees/providers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_fee(
    user_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> None:
    row = _fee_row(db, principal.organization_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No fee set for this doctor")
    db.delete(row)
    db.flush()
    _audit(db, principal, request, "setup.fee_removed", resource_type="fee_schedule",
           resource_id=str(row.id), metadata={"provider_user_id": str(user_id)})


@router.get("/fees/effective", response_model=EffectiveFeeOut)
def effective_fee(
    provider_user_id: uuid.UUID | None = None,
    principal: Principal = Depends(require_permission("setup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> EffectiveFeeOut:
    """The fee to pre-fill on a consultation invoice: the doctor's own fee,
    else the clinic default (billing staff can still edit the line)."""
    row, source = None, "none"
    if provider_user_id is not None:
        row = _fee_row(db, principal.organization_id, provider_user_id)
        source = "provider" if row else "none"
    if row is None:
        row = _fee_row(db, principal.organization_id, None)
        source = "default" if row else "none"
    return EffectiveFeeOut(
        provider_user_id=provider_user_id, source=source,
        consultation_fee=row.consultation_fee if row else None,
        follow_up_fee=row.follow_up_fee if row else None,
        follow_up_valid_days=row.follow_up_valid_days if row else None)


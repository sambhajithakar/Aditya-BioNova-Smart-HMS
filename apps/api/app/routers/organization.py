"""Tenant administration: clinic profile, MFA policy, onboarding checklist,
full data export and the offboarding (account closure) request."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..models import Branch, MemberInvitation, Membership, Organization, Role, User
from ..schemas import OffboardingIn, OnboardingOut, OnboardingStepOut, OrganizationProfileIn, \
    OrganizationProfileOut
from ..security import verify_password

router = APIRouter(prefix="/organization", tags=["organization"])

# Tenant tables included in the export. Session/token and idempotency tables
# are operational secrets, not clinic data, and are deliberately excluded.
EXPORT_TABLES = [
    "branches", "memberships", "member_invitations", "patients", "appointments",
    "opd_queue", "encounters", "encounter_vitals", "encounter_diagnoses", "prescriptions",
    "prescription_items", "invoices", "invoice_items", "payments", "refunds",
    "ledger_entries", "stock_batches", "stock_movements", "dispenses", "dispense_items",
    "lab_orders", "lab_order_items", "lab_specimens", "lab_results", "wards", "beds",
    "admissions", "admission_transfers", "nursing_records", "inventory_items",
    "inventory_movements", "expenses", "subscriptions", "subscription_events",
    "support_tickets", "support_ticket_messages", "audit_events",
]
_EXCLUDED_COLUMNS = {"token_hash"}


def _org(db: Session, principal: Principal) -> Organization:
    org = db.get(Organization, principal.organization_id)
    if org is None:  # pragma: no cover - RLS/context guarantees it
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _audit(db: Session, principal: Principal, request: Request, action: str,
           metadata: dict | None = None) -> None:
    record_event(
        db, action=action, organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id), resource_type="organization",
        resource_id=str(principal.organization_id), metadata=metadata,
        correlation_id=get_correlation_id(request), ip_address=get_client_ip(request),
    )


@router.get("", response_model=OrganizationProfileOut)
def get_organization(
    principal: Principal = Depends(require_permission("org.read")),
    db: Session = Depends(get_db, scope="function"),
) -> OrganizationProfileOut:
    return OrganizationProfileOut.model_validate(_org(db, principal))


@router.patch("", response_model=OrganizationProfileOut)
def update_organization(
    payload: OrganizationProfileIn,
    request: Request,
    principal: Principal = Depends(require_permission("org.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> OrganizationProfileOut:
    org = _org(db, principal)
    changes = {}
    for field_name in payload.model_fields_set:
        value = getattr(payload, field_name)
        if field_name == "name" and value is None:
            continue  # the display name can be changed but never cleared
        if getattr(org, field_name) != value:
            setattr(org, field_name, value)
            changes[field_name] = value
    if changes:
        org.updated_at = datetime.now(timezone.utc)
        db.flush()
        _audit(db, principal, request, "organization.updated",
               {"fields": sorted(changes), "mfa_required_roles":
                changes.get("mfa_required_roles")})
    return OrganizationProfileOut.model_validate(org)


@router.get("/onboarding", response_model=OnboardingOut)
def onboarding(
    principal: Principal = Depends(require_permission("org.read")),
    db: Session = Depends(get_db, scope="function"),
) -> OnboardingOut:
    org = _org(db, principal)
    org_id = principal.organization_id
    branches = db.scalar(select(func.count()).select_from(Branch).where(
        Branch.organization_id == org_id, Branch.status == "active")) or 0
    staff = db.scalar(select(func.count()).select_from(Membership).where(
        Membership.organization_id == org_id)) or 0
    invited = db.scalar(select(func.count()).select_from(MemberInvitation).where(
        MemberInvitation.organization_id == org_id)) or 0
    owner_mfa = db.scalar(
        select(func.count()).select_from(Membership)
        .join(Role, Role.id == Membership.role_id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == org_id, Role.key == "owner",
               User.mfa_totp_enabled_at.is_not(None))) or 0
    edition_chosen = db.scalar(text(
        "SELECT count(*) FROM subscription_events WHERE organization_id = :o"),
        {"o": str(org_id)}) or 0
    steps = [
        OnboardingStepOut(key="profile", done=bool(org.address_line1 and org.city
                                                   and org.phone)),
        OnboardingStepOut(key="branch", done=branches > 0),
        OnboardingStepOut(key="staff", done=staff > 1 or invited > 0),
        OnboardingStepOut(key="mfa_owner", done=owner_mfa > 0),
        OnboardingStepOut(key="mfa_policy", done=bool(org.mfa_required_roles)),
        OnboardingStepOut(key="edition", done=edition_chosen > 0),
    ]
    return OnboardingOut(completed=all(s.done for s in steps), steps=steps)


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    return str(value) if not isinstance(value, (int, float, str, bool, list, dict,
                                                type(None))) else value


@router.post("/export")
def export_organization(
    request: Request,
    principal: Principal = Depends(require_permission("org.offboard")),
    db: Session = Depends(get_db, scope="function"),
) -> Response:
    """Every tenant table as JSON in one zip (data portability / offboarding).

    Reads run through the tenant's RLS context AND an explicit
    ``organization_id`` filter, so nothing from another clinic can appear.
    """
    org = _org(db, principal)
    buf = io.BytesIO()
    counts: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        profile = OrganizationProfileOut.model_validate(org).model_dump(mode="json")
        zf.writestr("organization.json", json.dumps(profile, ensure_ascii=False, indent=1))
        staff = db.execute(
            select(User.id, User.email, User.full_name, User.registration_number,
                   Membership.status, Role.key)
            .join(Membership, Membership.user_id == User.id)
            .join(Role, Role.id == Membership.role_id)
            .where(Membership.organization_id == org.id)
        ).all()
        zf.writestr("staff.json", json.dumps(
            [{"user_id": str(r[0]), "email": r[1], "full_name": r[2],
              "registration_number": r[3], "status": r[4], "role": r[5]} for r in staff],
            ensure_ascii=False, indent=1))
        for table in EXPORT_TABLES:
            result = db.execute(
                text(f'SELECT * FROM "{table}" WHERE organization_id = :o'),  # noqa: S608
                {"o": str(org.id)})
            cols = [c for c in result.keys() if c not in _EXCLUDED_COLUMNS]
            rows = [{c: _jsonable(getattr(r, c)) for c in cols} for r in result]
            counts[table] = len(rows)
            zf.writestr(f"tables/{table}.json", json.dumps(rows, ensure_ascii=False))
        zf.writestr("MANIFEST.json", json.dumps({
            "organization_id": str(org.id), "slug": org.slug,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "row_counts": counts, "format": "one JSON array per table",
        }, indent=1))
    _audit(db, principal, request, "organization.exported",
           {"tables": len(counts), "rows": sum(counts.values())})
    filename = f"{org.slug}-export-{date.today().isoformat()}.zip"
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/offboarding", response_model=OrganizationProfileOut)
def request_offboarding(
    payload: OffboardingIn,
    request: Request,
    principal: Principal = Depends(require_permission("org.offboard")),
    db: Session = Depends(get_db, scope="function"),
) -> OrganizationProfileOut:
    """Record the owner's closure request. Nothing is deleted here: the vendor
    executes closure after the retention/notice period (platform console)."""
    if not verify_password(payload.password, principal.user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    org = _org(db, principal)
    if org.offboarding_requested_at is None:
        org.offboarding_requested_at = datetime.now(timezone.utc)
        org.offboarding_requested_by = principal.user_id
        org.offboarding_reason = payload.reason
        db.flush()
        _audit(db, principal, request, "organization.offboarding_requested",
               {"reason": payload.reason})
    return OrganizationProfileOut.model_validate(org)


@router.delete("/offboarding", response_model=OrganizationProfileOut)
def cancel_offboarding(
    request: Request,
    principal: Principal = Depends(require_permission("org.offboard")),
    db: Session = Depends(get_db, scope="function"),
) -> OrganizationProfileOut:
    org = _org(db, principal)
    if org.offboarding_requested_at is not None:
        org.offboarding_requested_at = None
        org.offboarding_requested_by = None
        org.offboarding_reason = None
        db.flush()
        _audit(db, principal, request, "organization.offboarding_cancelled")
    return OrganizationProfileOut.model_validate(org)

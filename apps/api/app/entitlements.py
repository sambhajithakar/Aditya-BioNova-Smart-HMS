"""Commercial editions: feature entitlements, usage limits and subscription
state, resolved per request.

Plans (editions) are DATA — rows in ``plans`` / ``plan_features`` /
``plan_limits`` (seeded by migration 0011, prices left unset) that the
platform super-admin maintains. A tenant's ``subscription`` points at one
plan and may carry per-tenant ``feature_overrides`` / ``limit_overrides``
(enterprise deals).

Enforcement points:
* ``require_feature(key)`` — router-level dependency (wired in main.py) so a
  module that is not in the plan answers 403 regardless of RBAC.
* ``enforce_writable`` — a read-only / suspended subscription blocks writes
  (402) but keeps reads working, so a lapsed clinic never loses access to
  its records.
* ``check_limit(...)`` — called before creating members, branches, beds.

Clinical patient billing is unrelated to this module (SaaS vs clinic money
are kept separate by design).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .db import get_db
from .deps import Principal, get_current_principal

FEATURES: dict[str, str] = {
    "patients": "Patient registration & EMR",
    "appointments": "Appointments",
    "opd_queue": "OPD queue & tokens",
    "consultation": "Consultation & e-prescriptions",
    "billing": "OPD billing & receipts",
    "pharmacy": "Pharmacy & stock",
    "laboratory": "Laboratory",
    "ipd": "Inpatient (IPD) & beds",
    "nursing": "Nursing workflows",
    "inventory": "General inventory",
    "expenses": "Expenses",
    "reports_basic": "Basic reports",
    "reports_advanced": "Advanced analytics",
    "multi_branch": "Multiple branches",
    "departments": "Multi-specialty departments",
    "emergency": "Emergency workflows",
    "ot": "Operation theatre scheduling",
    "insurance_tpa": "Insurance & TPA",
    "mobile_offline": "Offline Android app",
    "comms_email": "E-mail notifications",
    "comms_sms": "SMS notifications",
    "comms_whatsapp": "WhatsApp notifications",
    "ai_scribe": "AI clinical voice scribe",
    "ai_copilot": "AI business copilot",
    "ai_agents": "AI operations agents",
    "ai_rag": "AI knowledge assistant",
    "ai_document": "AI document extraction",
    "ai_forecast": "AI demand forecasting",
    "abdm": "ABDM / ABHA integration",
    "fhir_api": "HL7 FHIR API",
    "api_access": "Public API access",
    "custom_roles": "Custom roles",
    "audit_export": "Audit log export",
    "priority_support": "Priority support",
}

LIMITS: dict[str, str] = {
    "max_users": "Active staff accounts",
    "max_branches": "Active branches",
    "max_beds": "Inpatient beds",
    "ai_credits_monthly": "AI credits per month",
    "sms_monthly": "SMS per month",
    "whatsapp_monthly": "WhatsApp messages per month",
}

SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "read_only", "suspended",
                         "cancelled")


@dataclass
class Entitlements:
    organization_id: uuid.UUID
    plan_id: uuid.UUID | None
    plan_code: str | None
    plan_name: str | None
    status: str                      # stored subscription status
    effective_status: str            # what is enforced right now
    read_only_reason: str | None
    features: set[str] = field(default_factory=set)
    limits: dict[str, int | None] = field(default_factory=dict)

    @property
    def writable(self) -> bool:
        return self.effective_status in ("trialing", "active", "past_due")


def _effective(sub_status: str, trial_ends_at: datetime | None,
               current_period_end: datetime | None,
               grace_until: datetime | None) -> tuple[str, str | None]:
    now = datetime.now(timezone.utc)
    if sub_status == "trialing" and trial_ends_at is not None and trial_ends_at <= now:
        return "read_only", "trial ended"
    if sub_status == "past_due" and grace_until is not None and grace_until <= now:
        return "read_only", "payment overdue"
    if sub_status == "read_only":
        return "read_only", "subscription inactive"
    if sub_status in ("suspended", "cancelled"):
        return sub_status, f"subscription {sub_status}"
    return sub_status, None


def load_entitlements(db: Session, organization_id: uuid.UUID) -> Entitlements:
    """Resolve plan features/limits + overrides for one tenant (RLS-scoped)."""
    row = db.execute(
        text(
            """
            SELECT s.status, s.trial_ends_at, s.current_period_end, s.grace_until,
                   s.feature_overrides, s.limit_overrides,
                   p.id, p.code, p.name
            FROM subscriptions s JOIN plans p ON p.id = s.plan_id
            WHERE s.organization_id = :org
            """
        ),
        {"org": str(organization_id)},
    ).first()
    if row is None:
        # Pre-M7.1 tenants without a subscription row: nothing is withheld
        # until the platform assigns an edition (migration 0011 backfills).
        return Entitlements(organization_id, None, None, None, "active", "active", None,
                            set(FEATURES), {k: None for k in LIMITS})
    (sub_status, trial_ends, period_end, grace, f_over, l_over,
     plan_id, plan_code, plan_name) = row
    features = set(db.scalars(
        text("SELECT feature_key FROM plan_features WHERE plan_id = :p"), {"p": plan_id}
    ).all())
    for key, enabled in (f_over or {}).items():
        (features.add if enabled else features.discard)(key)
    limits: dict[str, int | None] = {k: None for k in LIMITS}
    for key, value in db.execute(
        text("SELECT limit_key, limit_value FROM plan_limits WHERE plan_id = :p"),
        {"p": plan_id},
    ).all():
        limits[key] = value
    limits.update(l_over or {})
    effective, reason = _effective(sub_status, trial_ends, period_end, grace)
    return Entitlements(organization_id, plan_id, plan_code, plan_name, sub_status,
                        effective, reason, features, limits)


def get_entitlements(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> Entitlements:
    cached = getattr(request.state, "entitlements", None)
    if cached is None:
        cached = load_entitlements(db, principal.organization_id)
        request.state.entitlements = cached
    return cached


_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def require_feature(feature_key: str, *, writes_need_writable: bool = True):
    """Router-level guard: the module must be in the tenant's plan and the
    subscription must allow the request (writes need a writable status unless
    the module's POSTs are reads, e.g. asking the Copilot a question)."""
    if feature_key not in FEATURES:
        raise ValueError(f"unknown feature {feature_key!r}")

    def checker(request: Request, ent: Entitlements = Depends(get_entitlements)) -> None:
        if ent.effective_status == "suspended":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Subscription is suspended")
        if feature_key not in ent.features:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature not included in your plan: {feature_key}",
            )
        if writes_need_writable and request.method in _WRITE_METHODS and not ent.writable:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Subscription is read-only: {ent.read_only_reason}",
            )

    return checker


def enforce_writable(request: Request, ent: Entitlements = Depends(get_entitlements)) -> None:
    """For always-available modules (patients, members, branches): reads stay
    open, writes need a writable subscription."""
    if ent.effective_status == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Subscription is suspended")
    if request.method in _WRITE_METHODS and not ent.writable:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Subscription is read-only: {ent.read_only_reason}",
        )


# --- usage limits --------------------------------------------------------------
def current_usage(db: Session, organization_id: uuid.UUID) -> dict[str, int]:
    """Counts used for limits (RLS-scoped to the tenant in context)."""
    from .models import Bed, Branch, MemberInvitation, Membership

    users = db.scalar(select(func.count()).select_from(Membership).where(
        Membership.organization_id == organization_id, Membership.status == "active")) or 0
    pending = db.scalar(select(func.count()).select_from(MemberInvitation).where(
        MemberInvitation.organization_id == organization_id,
        MemberInvitation.status == "pending",
        MemberInvitation.expires_at > datetime.now(timezone.utc))) or 0
    branches = db.scalar(select(func.count()).select_from(Branch).where(
        Branch.organization_id == organization_id, Branch.status == "active")) or 0
    beds = db.scalar(select(func.count()).select_from(Bed).where(
        Bed.organization_id == organization_id)) or 0
    from .ai.gateway import allowance_used
    from .comms import engine as comms_engine
    from .models import Organization

    org = db.get(Organization, organization_id)
    period = comms_engine.period_of(comms_engine.utcnow(), comms_engine.org_tz(org))
    sent = comms_engine.usage(db, organization_id, period)
    return {"max_users": users + pending, "max_branches": branches, "max_beds": beds,
            # the plan's own monthly allowance; purchased credits are on top
            "ai_credits_monthly": allowance_used(db, organization_id),
            "sms_monthly": sent["sms"]["used"], "whatsapp_monthly": sent["whatsapp"]["used"]}


def check_limit(db: Session, organization_id: uuid.UUID, limit_key: str,
                adding: int = 1) -> None:
    """403 when adding ``adding`` more units would exceed the plan limit."""
    ent = load_entitlements(db, organization_id)
    limit = ent.limits.get(limit_key)
    if limit is None:
        return
    used = current_usage(db, organization_id)[limit_key]
    if used + adding > limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan limit reached: {limit_key} ({limit}). Upgrade your plan.",
        )

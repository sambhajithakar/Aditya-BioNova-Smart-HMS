"""Platform (vendor) console: tenants, editions/prices, subscriptions, support.

Every route depends on ``require_platform_admin``, which sets the
``app.platform_admin`` GUC. RLS then opens only the commercial tables
(organizations, plans, subscriptions, support); patient/clinical tables stay
tenant-only, so nothing here can read PHI. Per-tenant usage comes from the
SECURITY DEFINER ``platform_tenant_overview()`` (counts only).

Platform actions are audited in the operator's own organization (the audit
writer only accepts events for the tenant in context), and every subscription
change is also written to the target tenant's ``subscription_events`` history,
which the tenant can see.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_platform_admin
from ..entitlements import FEATURES, LIMITS, _effective
from ..models import (
    Organization,
    Plan,
    PlanFeature,
    PlanLimit,
    Subscription,
    SubscriptionEvent,
    SupportTicket,
    SupportTicketMessage,
    User,
)
from ..schemas import (
    CatalogEntryOut,
    CatalogOut,
    PlanFeaturesIn,
    PlanLimitsIn,
    PlanOut,
    PlanUpdateIn,
    PlatformOverviewOut,
    PlatformSubscriptionIn,
    PlatformSupportMessageIn,
    PlatformTenantDetailOut,
    PlatformTenantOut,
    PlatformTenantUpdateIn,
    PlatformTicketUpdateIn,
    SubscriptionEventOut,
    SubscriptionOut,
    SupportTicketDetailOut,
    SupportTicketOut,
    UsageOut,
)
from ..services.subscriptions import get_plan, plan_out, record_subscription_event
from .support import ticket_detail, ticket_out

router = APIRouter(prefix="/platform", tags=["platform"])

_USAGE_KEYS = {"max_users": "users", "max_branches": "branches", "max_beds": "beds"}


def _audit(db: Session, principal: Principal, request: Request, action: str,
           target: uuid.UUID | str | None, metadata: dict | None = None) -> None:
    record_event(
        db, action=action, organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id), resource_type="platform",
        resource_id=str(target) if target else None, metadata=metadata,
        correlation_id=get_correlation_id(request), ip_address=get_client_ip(request),
    )


def _overview_counts(db: Session) -> dict[uuid.UUID, dict[str, int]]:
    rows = db.execute(text("SELECT * FROM platform_tenant_overview()")).all()
    return {r.organization_id: {"users": r.users, "branches": r.branches, "beds": r.beds,
                                "patients": r.patients} for r in rows}


def _tenant_out(db: Session, org: Organization, sub: Subscription | None,
                counts: dict[str, int]) -> PlatformTenantOut:
    plan = db.get(Plan, sub.plan_id) if sub else None
    effective = None
    if sub is not None:
        effective, _ = _effective(sub.status, sub.trial_ends_at, sub.current_period_end,
                                  sub.grace_until)
    return PlatformTenantOut(
        id=org.id, name=org.name, slug=org.slug, status=org.status,
        created_at=org.created_at, plan_code=plan.code if plan else None,
        subscription_status=sub.status if sub else None, effective_status=effective,
        trial_ends_at=sub.trial_ends_at if sub else None,
        users=counts.get("users", 0), branches=counts.get("branches", 0),
        beds=counts.get("beds", 0), patients=counts.get("patients", 0),
        offboarding_requested_at=org.offboarding_requested_at,
    )


def _platform_subscription_out(db: Session, sub: Subscription,
                               counts: dict[str, int]) -> SubscriptionOut:
    plan = db.get(Plan, sub.plan_id)
    p_out = plan_out(db, plan)
    features = set(p_out.features)
    for key, enabled in (sub.feature_overrides or {}).items():
        (features.add if enabled else features.discard)(key)
    limits = dict(p_out.limits)
    limits.update(sub.limit_overrides or {})
    effective, reason = _effective(sub.status, sub.trial_ends_at, sub.current_period_end,
                                   sub.grace_until)
    return SubscriptionOut(
        plan=p_out, status=sub.status, effective_status=effective,
        billing_cycle=sub.billing_cycle, trial_ends_at=sub.trial_ends_at,
        current_period_end=sub.current_period_end, read_only_reason=reason,
        features=sorted(features),
        usage={k: UsageOut(limit=limits.get(k), used=counts.get(_USAGE_KEYS.get(k, ""), 0))
               for k in LIMITS},
    )


def _detail(db: Session, org: Organization) -> PlatformTenantDetailOut:
    counts = _overview_counts(db).get(org.id, {})
    sub = db.scalar(select(Subscription).where(Subscription.organization_id == org.id))
    events = db.scalars(select(SubscriptionEvent).where(
        SubscriptionEvent.organization_id == org.id)
        .order_by(SubscriptionEvent.id.desc()).limit(50)).all()
    return PlatformTenantDetailOut(
        **_tenant_out(db, org, sub, counts).model_dump(),
        subscription=_platform_subscription_out(db, sub, counts) if sub else None,
        events=[SubscriptionEventOut(
            id=e.id, from_plan=e.from_plan, to_plan=e.to_plan, from_status=e.from_status,
            to_status=e.to_status, reason=e.reason, created_at=e.created_at,
            actor_name=(db.get(User, e.actor_user_id).full_name
                        if e.actor_user_id and db.get(User, e.actor_user_id) else None))
            for e in events],
    )


def _load_org(db: Session, org_id: uuid.UUID) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return org


# --- overview & tenants ------------------------------------------------------------
@router.get("/overview", response_model=PlatformOverviewOut)
def overview(
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> PlatformOverviewOut:
    by_status: dict[str, int] = {}
    for (st,) in db.execute(select(Organization.status)).all():
        by_status[st] = by_status.get(st, 0) + 1
    by_plan: dict[str, int] = {}
    mrr = unpriced = expiring = 0
    soon = datetime.now(timezone.utc) + timedelta(days=7)
    for sub, plan in db.execute(select(Subscription, Plan).join(
            Plan, Plan.id == Subscription.plan_id)).all():
        by_plan[plan.code] = by_plan.get(plan.code, 0) + 1
        if sub.status == "trialing" and sub.trial_ends_at and sub.trial_ends_at <= soon:
            expiring += 1
        if sub.status in ("active", "past_due"):
            if sub.billing_cycle == "annual" and plan.price_annual_paise is not None:
                mrr += plan.price_annual_paise // 12
            elif sub.billing_cycle == "monthly" and plan.price_monthly_paise is not None:
                mrr += plan.price_monthly_paise
            else:
                unpriced += 1
    open_tickets = len(db.scalars(select(SupportTicket.id).where(
        SupportTicket.status.in_(("open", "in_progress")))).all())
    return PlatformOverviewOut(tenants_by_status=by_status, tenants_by_plan=by_plan,
                               trials_expiring_7d=expiring, open_tickets=open_tickets,
                               mrr_paise=mrr, unpriced_active_subscriptions=unpriced)


@router.get("/tenants", response_model=list[PlatformTenantOut])
def list_tenants(
    q: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=20),
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> list[PlatformTenantOut]:
    stmt = select(Organization).order_by(Organization.created_at.desc())
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where((Organization.name.ilike(like)) | (Organization.slug.ilike(like)))
    if status:
        stmt = stmt.where(Organization.status == status)
    counts = _overview_counts(db)
    subs = {s.organization_id: s for s in db.scalars(select(Subscription)).all()}
    return [_tenant_out(db, o, subs.get(o.id), counts.get(o.id, {}))
            for o in db.scalars(stmt.limit(500)).all()]


@router.get("/tenants/{org_id}", response_model=PlatformTenantDetailOut)
def tenant_detail(
    org_id: uuid.UUID,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> PlatformTenantDetailOut:
    return _detail(db, _load_org(db, org_id))


@router.patch("/tenants/{org_id}", response_model=PlatformTenantOut)
def update_tenant(
    org_id: uuid.UUID,
    payload: PlatformTenantUpdateIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> PlatformTenantOut:
    org = _load_org(db, org_id)
    if org.id == principal.organization_id:
        raise HTTPException(status_code=409, detail="The platform organization cannot be "
                                                    "suspended from the console")
    if org.status != payload.status:
        old = org.status
        org.status = payload.status
        org.updated_at = datetime.now(timezone.utc)
        db.flush()
        _audit(db, principal, request, f"platform.tenant_{payload.status}", org.id,
               {"from": old, "reason": payload.reason, "slug": org.slug})
    sub = db.scalar(select(Subscription).where(Subscription.organization_id == org.id))
    return _tenant_out(db, org, sub, _overview_counts(db).get(org.id, {}))


@router.put("/tenants/{org_id}/subscription", response_model=PlatformTenantDetailOut)
def set_subscription(
    org_id: uuid.UUID,
    payload: PlatformSubscriptionIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> PlatformTenantDetailOut:
    org = _load_org(db, org_id)
    plan = get_plan(db, payload.plan_code)
    bad = sorted((set(payload.feature_overrides) - set(FEATURES))
                 | (set(payload.limit_overrides) - set(LIMITS)))
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown keys: {', '.join(bad)}")
    sub = db.scalar(select(Subscription).where(Subscription.organization_id == org.id))
    old_plan = db.get(Plan, sub.plan_id).code if sub else None
    old_status = sub.status if sub else None
    if sub is None:
        sub = Subscription(organization_id=org.id, plan_id=plan.id, status=payload.status)
        db.add(sub)
    sub.plan_id = plan.id
    sub.status = payload.status
    sub.billing_cycle = payload.billing_cycle
    sub.trial_ends_at = payload.trial_ends_at
    sub.current_period_end = payload.current_period_end
    sub.feature_overrides = payload.feature_overrides
    sub.limit_overrides = payload.limit_overrides
    sub.updated_at = datetime.now(timezone.utc)
    record_subscription_event(db, org.id, from_plan=old_plan, to_plan=plan.code,
                              from_status=old_status, to_status=payload.status,
                              reason=payload.reason, actor_user_id=principal.user_id)
    db.flush()
    _audit(db, principal, request, "platform.subscription_set", org.id,
           {"plan": plan.code, "status": payload.status, "reason": payload.reason})
    return _detail(db, org)


# --- catalogue & editions ----------------------------------------------------------------
@router.get("/catalog", response_model=CatalogOut)
def catalog(principal: Principal = Depends(require_platform_admin)) -> CatalogOut:
    return CatalogOut(
        features=[CatalogEntryOut(key=k, label=v) for k, v in FEATURES.items()],
        limits=[CatalogEntryOut(key=k, label=v) for k, v in LIMITS.items()],
    )


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> list[PlanOut]:
    return [plan_out(db, p, admin=True)
            for p in db.scalars(select(Plan).order_by(Plan.tier)).all()]


@router.patch("/plans/{code}", response_model=PlanOut)
def update_plan(
    code: str,
    payload: PlanUpdateIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> PlanOut:
    plan = get_plan(db, code)
    changes = {}
    for name in payload.model_fields_set:
        value = getattr(payload, name)
        if name in ("name", "trial_days", "is_active", "is_public", "description") \
                and value is None:
            continue
        if getattr(plan, name) != value:
            changes[name] = value
            setattr(plan, name, value)
    if changes:
        plan.updated_at = datetime.now(timezone.utc)
        db.flush()
        _audit(db, principal, request, "platform.plan_updated", plan.code, changes)
    return plan_out(db, plan, admin=True)


@router.put("/plans/{code}/features", response_model=PlanOut)
def set_plan_features(
    code: str,
    payload: PlanFeaturesIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> PlanOut:
    plan = get_plan(db, code)
    unknown = sorted(set(payload.features) - set(FEATURES))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown features: {', '.join(unknown)}")
    db.execute(delete(PlanFeature).where(PlanFeature.plan_id == plan.id))
    for key in sorted(set(payload.features)):
        db.add(PlanFeature(plan_id=plan.id, feature_key=key))
    db.flush()
    _audit(db, principal, request, "platform.plan_features_set", plan.code,
           {"features": sorted(set(payload.features))})
    return plan_out(db, plan, admin=True)


@router.put("/plans/{code}/limits", response_model=PlanOut)
def set_plan_limits(
    code: str,
    payload: PlanLimitsIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> PlanOut:
    plan = get_plan(db, code)
    unknown = sorted(set(payload.limits) - set(LIMITS))
    if unknown or any(v is not None and v < 0 for v in payload.limits.values()):
        raise HTTPException(status_code=422, detail="Unknown limit keys or negative values")
    for key, value in payload.limits.items():
        row = db.get(PlanLimit, (plan.id, key))
        if row is None:
            db.add(PlanLimit(plan_id=plan.id, limit_key=key, limit_value=value))
        else:
            row.limit_value = value
    db.flush()
    _audit(db, principal, request, "platform.plan_limits_set", plan.code, payload.limits)
    return plan_out(db, plan, admin=True)


# --- support queue ---------------------------------------------------------------------
@router.get("/support/tickets", response_model=list[SupportTicketOut])
def support_queue(
    status: str | None = Query(default=None, max_length=25),
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> list[SupportTicketOut]:
    stmt = select(SupportTicket).order_by(SupportTicket.updated_at.desc()).limit(500)
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    return [ticket_out(db, t, with_org=True) for t in db.scalars(stmt).all()]


def _ticket(db: Session, ticket_id: uuid.UUID) -> SupportTicket:
    t = db.get(SupportTicket, ticket_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return t


@router.get("/support/tickets/{ticket_id}", response_model=SupportTicketDetailOut)
def support_ticket(
    ticket_id: uuid.UUID,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> SupportTicketDetailOut:
    return ticket_detail(db, _ticket(db, ticket_id), with_org=True)


@router.post("/support/tickets/{ticket_id}/messages", response_model=SupportTicketDetailOut)
def support_reply(
    ticket_id: uuid.UUID,
    payload: PlatformSupportMessageIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> SupportTicketDetailOut:
    t = _ticket(db, ticket_id)
    db.add(SupportTicketMessage(ticket_id=t.id, organization_id=t.organization_id,
                                author_user_id=principal.user_id, author_side="vendor",
                                body=payload.body, internal=payload.internal))
    if not payload.internal and t.status in ("open", "in_progress"):
        t.status = "waiting_on_customer"
    t.updated_at = datetime.now(timezone.utc)
    db.flush()
    _audit(db, principal, request, "platform.support_replied", t.id,
           {"number": t.number, "internal": payload.internal})
    return ticket_detail(db, t, with_org=True)


@router.patch("/support/tickets/{ticket_id}", response_model=SupportTicketOut)
def support_update(
    ticket_id: uuid.UUID,
    payload: PlatformTicketUpdateIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    db: Session = Depends(get_db, scope="function"),
) -> SupportTicketOut:
    t = _ticket(db, ticket_id)
    changes = {k: getattr(payload, k) for k in payload.model_fields_set
               if getattr(payload, k) is not None}
    for k, v in changes.items():
        setattr(t, k, v)
    if changes:
        t.updated_at = datetime.now(timezone.utc)
        db.flush()
        _audit(db, principal, request, "platform.support_updated", t.id,
               {"number": t.number, **changes})
    return ticket_out(db, t, with_org=True)

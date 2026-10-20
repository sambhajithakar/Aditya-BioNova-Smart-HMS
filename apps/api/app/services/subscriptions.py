"""Edition catalogue and subscription helpers shared by registration, the
tenant subscription view and the platform console."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..entitlements import LIMITS, current_usage, load_entitlements
from ..models import Plan, PlanFeature, PlanLimit, Subscription, SubscriptionEvent
from ..schemas import PlanOut, SubscriptionOut, UsageOut


def plan_out(db: Session, plan: Plan, *, admin: bool = False) -> PlanOut:
    features = sorted(db.scalars(
        select(PlanFeature.feature_key).where(PlanFeature.plan_id == plan.id)).all())
    limits = {k: None for k in LIMITS}
    for row in db.scalars(select(PlanLimit).where(PlanLimit.plan_id == plan.id)).all():
        limits[row.limit_key] = row.limit_value
    return PlanOut(
        code=plan.code, name=plan.name, description=plan.description, tier=plan.tier,
        price_monthly_paise=plan.price_monthly_paise,
        price_annual_paise=plan.price_annual_paise, currency=plan.currency,
        trial_days=plan.trial_days, features=features, limits=limits,
        is_active=plan.is_active if admin else None,
        is_public=plan.is_public if admin else None,
    )


def get_plan(db: Session, code: str, *, public_only: bool = False) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.code == code))
    if plan is None or (public_only and not (plan.is_active and plan.is_public)):
        raise HTTPException(status_code=422, detail=f"Unknown or unavailable plan: {code}")
    return plan


def subscription_out(db: Session, organization_id: uuid.UUID) -> SubscriptionOut | None:
    sub = db.scalar(select(Subscription).where(
        Subscription.organization_id == organization_id))
    if sub is None:
        return None
    plan = db.get(Plan, sub.plan_id)
    ent = load_entitlements(db, organization_id)
    used = current_usage(db, organization_id)
    return SubscriptionOut(
        plan=plan_out(db, plan), status=sub.status, effective_status=ent.effective_status,
        billing_cycle=sub.billing_cycle, trial_ends_at=sub.trial_ends_at,
        current_period_end=sub.current_period_end, read_only_reason=ent.read_only_reason,
        features=sorted(ent.features),
        usage={k: UsageOut(limit=ent.limits.get(k), used=used.get(k, 0)) for k in LIMITS},
    )


def record_subscription_event(
    db: Session, organization_id: uuid.UUID, *, from_plan: str | None, to_plan: str | None,
    from_status: str | None, to_status: str | None, reason: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    db.add(SubscriptionEvent(
        organization_id=organization_id, from_plan=from_plan, to_plan=to_plan,
        from_status=from_status, to_status=to_status, reason=reason[:500],
        actor_user_id=actor_user_id,
    ))


def start_trial(db: Session, organization_id: uuid.UUID, plan: Plan,
                actor_user_id: uuid.UUID | None) -> Subscription:
    now = datetime.now(timezone.utc)
    trialing = plan.trial_days > 0
    sub = Subscription(
        organization_id=organization_id, plan_id=plan.id,
        status="trialing" if trialing else "active",
        trial_ends_at=now + timedelta(days=plan.trial_days) if trialing else None,
        current_period_start=now,
    )
    db.add(sub)
    record_subscription_event(
        db, organization_id, from_plan=None, to_plan=plan.code, from_status=None,
        to_status=sub.status, reason="self-service registration",
        actor_user_id=actor_user_id,
    )
    return sub

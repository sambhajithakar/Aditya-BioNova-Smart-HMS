"""Tenant view of its commercial edition, the public plan catalogue, and
plan-change requests (fulfilled by the vendor; online payment is M7.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, require_permission
from ..models import Plan
from ..schemas import ChangeRequestIn, PlanOut, SubscriptionOut, SupportTicketIn, \
    SupportTicketOut
from ..services.subscriptions import get_plan, plan_out, subscription_out
from .support import open_ticket

router = APIRouter(tags=["subscription"])


@router.get("/plans", response_model=list[PlanOut])
def list_public_plans(db: Session = Depends(get_db, scope="function")) -> list[PlanOut]:
    """Public catalogue (no auth). A null price means "not configured yet"."""
    plans = db.scalars(select(Plan).where(Plan.is_active, Plan.is_public)
                       .order_by(Plan.tier)).all()
    return [plan_out(db, p) for p in plans]


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(
    principal: Principal = Depends(require_permission("subscription.read")),
    db: Session = Depends(get_db, scope="function"),
) -> SubscriptionOut:
    out = subscription_out(db, principal.organization_id)
    if out is None:
        raise HTTPException(status_code=404, detail="No subscription")
    return out


@router.post("/subscription/change-request", response_model=SupportTicketOut,
             status_code=status.HTTP_201_CREATED)
def request_plan_change(
    payload: ChangeRequestIn,
    request: Request,
    principal: Principal = Depends(require_permission("subscription.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> SupportTicketOut:
    plan = get_plan(db, payload.plan_code, public_only=True)
    body = (f"Requested edition: {plan.name} ({plan.code}), billing cycle: "
            f"{payload.billing_cycle}.\n\n{payload.note}").strip()
    return open_ticket(
        db, principal, request,
        SupportTicketIn(subject=f"Plan change request: {plan.name}", category="billing",
                        priority="normal", body=body),
    )

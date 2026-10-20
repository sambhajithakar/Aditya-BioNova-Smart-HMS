"""Statistical forecasts (phase AI-1). Mounted behind ``require_feature
("ai_forecast")``; the tenant must also have switched ``ai_forecast`` on.

These are deterministic statistical models computed inside the API — no AI
provider is called, no credits are consumed and ``AI_ENABLED=false`` does not
stop them (the kill switch governs model inference; see AI_ARCHITECTURE.md
§6.5). Each response says "statistical model" and reports its backtest
against a naive baseline.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import forecast_service as svc
from ..ai.common import require_opt_in, require_perm
from ..ai.models_ai1 import AiModelRun
from ..db import get_db
from ..deps import Principal, require_permission
from ..schemas_ai1 import ForecastOut, ModelRunOut
from ..services.tenancy import load_branch

router = APIRouter(prefix="/ai/forecast", tags=["ai-forecast"])
FEATURE = "ai_forecast"


def _branch(db: Session, principal: Principal, branch_id: uuid.UUID | None):
    if branch_id is not None:
        load_branch(db, principal, branch_id, active=False)
    return branch_id


@router.get("/opd", response_model=list[ForecastOut])
def opd(branch_id: uuid.UUID | None = None, horizon: int = Query(default=14, ge=7, le=28),
        principal: Principal = Depends(require_permission("ai.forecast.read")),
        db: Session = Depends(get_db, scope="function")) -> list[dict]:
    require_opt_in(db, principal, FEATURE)
    return svc.opd_demand(db, principal, _branch(db, principal, branch_id), horizon)


@router.get("/no-show", response_model=ForecastOut)
def no_show(branch_id: uuid.UUID | None = None,
            days_ahead: int = Query(default=7, ge=1, le=30),
            principal: Principal = Depends(require_permission("ai.forecast.read")),
            db: Session = Depends(get_db, scope="function")) -> dict:
    require_perm(principal, "appointment.read")
    require_opt_in(db, principal, FEATURE)
    return svc.no_show(db, principal, _branch(db, principal, branch_id), days_ahead)


@router.get("/pharmacy", response_model=list[ForecastOut])
def pharmacy(branch_id: uuid.UUID | None = None,
             lead_time_days: int = Query(default=7, ge=1, le=60),
             review_days: int = Query(default=14, ge=1, le=90),
             principal: Principal = Depends(require_permission("ai.forecast.read")),
             db: Session = Depends(get_db, scope="function")) -> list[dict]:
    require_perm(principal, "pharmacy.read")
    require_opt_in(db, principal, FEATURE)
    return svc.pharmacy_demand(db, principal, _branch(db, principal, branch_id),
                               lead_time_days, review_days)


@router.get("/inventory", response_model=list[ForecastOut])
def inventory(branch_id: uuid.UUID | None = None,
              lead_time_days: int = Query(default=7, ge=1, le=60),
              review_days: int = Query(default=14, ge=1, le=90),
              principal: Principal = Depends(require_permission("ai.forecast.read")),
              db: Session = Depends(get_db, scope="function")) -> list[dict]:
    require_perm(principal, "inventory.read")
    require_opt_in(db, principal, FEATURE)
    return svc.inventory_demand(db, principal, _branch(db, principal, branch_id),
                                lead_time_days, review_days)


@router.get("/beds", response_model=ForecastOut)
def beds(branch_id: uuid.UUID | None = None, horizon: int = Query(default=14, ge=7, le=28),
         principal: Principal = Depends(require_permission("ai.forecast.read")),
         db: Session = Depends(get_db, scope="function")) -> dict:
    require_perm(principal, "bed.read")
    require_opt_in(db, principal, FEATURE)
    return svc.bed_occupancy(db, principal, _branch(db, principal, branch_id), horizon)


@router.get("/model-runs", response_model=list[ModelRunOut])
def model_runs(kind: str | None = None, limit: int = Query(default=50, ge=1, le=200),
               principal: Principal = Depends(require_permission("ai.forecast.read")),
               db: Session = Depends(get_db, scope="function")) -> list[ModelRunOut]:
    q = select(AiModelRun).where(AiModelRun.organization_id == principal.organization_id)
    if kind:
        q = q.where(AiModelRun.kind == kind)
    rows = db.scalars(q.order_by(AiModelRun.trained_at.desc()).limit(limit)).all()
    return [ModelRunOut.model_validate(r) for r in rows]

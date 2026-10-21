"""AI governance views (AI-1): credits and requests per feature/task for the
clinic-month, and the honest implementation status of every AI feature.
Mounted with the Copilot router's gate (any AI edition)."""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..ai.gateway import credits_used, current_period, purchased_balance, \
    tenant_enabled_features
from ..config import get_settings
from ..db import get_db
from ..deps import Principal, require_permission
from ..entitlements import load_entitlements
from ..models import AiRequest
from ..schemas_ai1 import UsageBreakdownOut, UsageBreakdownRow
from ..timeutil import clinic_day_bounds

_PERIOD_RE = re.compile(r"\d{4}-(0[1-9]|1[0-2])")

router = APIRouter(prefix="/ai/governance", tags=["ai-governance"])

FEATURE_STATUS = {
    "ai_copilot": {"implemented": True, "engine": "mock rule-based intent parser; figures "
                   "from verified report queries", "needs_provider": False},
    "ai_forecast": {"implemented": True, "engine": "statistical models (seasonal naive, "
                    "Holt-Winters, Croston/SBA, logistic regression) — no AI provider",
                    "needs_provider": False},
    "ai_rag": {"implemented": True, "engine": "BM25 retrieval + extractive quotes (mock "
               "inference); groundedness check for any live model", "needs_provider": False},
    "ai_agents": {"implemented": True, "engine": "deterministic planners; proposals need "
                  "human approval", "needs_provider": False},
    "ai_scribe": {"implemented": True, "engine": "typed/pasted transcript (mock "
                  "transcription, no ASR) + rule-based SOAP sectioniser (mock inference)",
                  "needs_provider": False},
    "ai_document": {"implemented": False, "engine": "not implemented (no OCR available)",
                    "needs_provider": True},
}


@router.get("/usage", response_model=UsageBreakdownOut)
def usage_breakdown(period: str | None = None,
                    principal: Principal = Depends(require_permission("ai.audit.read")),
                    db: Session = Depends(get_db, scope="function")) -> UsageBreakdownOut:
    if period is not None and not _PERIOD_RE.fullmatch(period):
        raise HTTPException(422, detail="period must be YYYY-MM")
    period = period or current_period()
    y, m = int(period[:4]), int(period[5:7])
    start = clinic_day_bounds(date(y, m, 1))[0]
    end = clinic_day_bounds(date(y + (m == 12), m % 12 + 1, 1))[0]
    rows = db.execute(
        select(AiRequest.feature, AiRequest.task, AiRequest.inference, func.count(),
               func.sum(case((AiRequest.status == "ok", 1), else_=0)),
               func.coalesce(func.sum(AiRequest.credits), 0))
        .where(AiRequest.organization_id == principal.organization_id,
               AiRequest.created_at >= start, AiRequest.created_at < end)
        .group_by(AiRequest.feature, AiRequest.task, AiRequest.inference)
        .order_by(AiRequest.feature, AiRequest.task)).all()
    ent = load_entitlements(db, principal.organization_id)
    enabled = set(tenant_enabled_features(db, principal.organization_id))
    settings = get_settings()
    features = {
        k: {**v, "entitled": k in ent.features, "enabled": k in enabled,
            "available_now": bool(v["implemented"] and k in ent.features and k in enabled
                                  and (settings.ai_enabled or not v["needs_provider"]))}
        for k, v in FEATURE_STATUS.items()}
    features["_kill_switches"] = {"AI_ENABLED": settings.ai_enabled,
                                  "AI_LIVE_ENABLED": settings.ai_live_enabled}
    return UsageBreakdownOut(
        period=period, used_credits=credits_used(db, principal.organization_id, period),
        limit_credits=ent.limits.get("ai_credits_monthly"),
        purchased_balance=purchased_balance(db, principal.organization_id),
        rows=[UsageBreakdownRow(feature=r[0], task=r[1], inference=r[2], requests=r[3],
                                ok=int(r[4] or 0), credits=int(r[5] or 0)) for r in rows],
        features=features)

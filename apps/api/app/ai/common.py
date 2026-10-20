"""Helpers shared by the AI-1 routers."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..deps import Principal, get_client_ip, get_correlation_id
from ..timeutil import clinic_day_bounds, clinic_today
from .gateway import tenant_enabled_features
from .models_ai1 import AiModelRun


def require_opt_in(db: Session, principal: Principal, feature: str) -> None:
    """The plan gate is on the router; the TENANT must also have switched the
    feature on (AI settings). Applies even to features that never call a model."""
    if feature not in tenant_enabled_features(db, principal.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="ai_not_enabled")


def require_perm(principal: Principal, *perms: str) -> None:
    missing = [p for p in perms if p not in principal.permissions]
    if missing:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail=f"Missing permission: {', '.join(missing)}")


def args_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def audit(db: Session, request: Request | None, principal: Principal, action: str,
          resource_type: str, resource_id: str | None, metadata: dict | None = None) -> None:
    record_event(db, action=action, organization_id=str(principal.organization_id),
                 actor_user_id=str(principal.user_id), resource_type=resource_type,
                 resource_id=resource_id, metadata=metadata or {},
                 correlation_id=get_correlation_id(request) if request else None,
                 ip_address=get_client_ip(request) if request else None)


def record_model_run(db: Session, principal: Principal, *, kind: str, scope: str,
                     engine_version: str, method: str, status_: str, params: dict,
                     metrics: dict, baseline_metrics: dict, data_start: date | None,
                     data_end: date | None, n_obs: int) -> AiModelRun:
    """Append a model-run row, reusing today's identical run (same kind, scope,
    method and data window) so page reloads do not flood the registry."""
    t0, t1 = clinic_day_bounds(clinic_today())
    existing = db.scalar(select(AiModelRun).where(
        AiModelRun.organization_id == principal.organization_id, AiModelRun.kind == kind,
        AiModelRun.scope == scope, AiModelRun.method == method,
        AiModelRun.status == status_, AiModelRun.data_end == data_end,
        AiModelRun.n_obs == n_obs, AiModelRun.engine_version == engine_version,
        AiModelRun.trained_at >= t0, AiModelRun.trained_at < t1)
        .order_by(AiModelRun.trained_at.desc()).limit(1))
    if existing is not None:
        return existing
    run = AiModelRun(organization_id=principal.organization_id, kind=kind, scope=scope[:80],
                     engine_version=engine_version, method=method, status=status_,
                     params=params, metrics=metrics, baseline_metrics=baseline_metrics,
                     data_start=data_start, data_end=data_end, n_obs=n_obs,
                     trained_by=principal.user_id, trained_at=datetime.now(timezone.utc))
    db.add(run)
    db.flush()
    return run

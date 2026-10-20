"""Gateway dispatch: kill switches → entitlement → opt-in → policy → credits →
provider call → output validation → audit + ledger."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..deps import Principal
from ..entitlements import load_entitlements
from ..models import AiCreditEntry, AiRequest, AiTenantSettings
from ..security import encrypt_field
from ..timeutil import clinic_today

DataClass = Literal["C0", "C1", "C2", "C3"]
_CLASS_RANK = {"C0": 0, "C1": 1, "C2": 2, "C3": 3}

# Credit cost per task and inference kind. Product units (not tokens); the
# owner can tune these later as data (AI_ARCHITECTURE.md §2.3, decision D5).
CREDIT_COSTS: dict[str, dict[str, int]] = {
    "copilot.intent": {"mock": 0, "live": 1},
}


@dataclass
class AIRequest:
    feature: str                       # entitlement key, e.g. "ai_copilot"
    task: str                          # e.g. "copilot.intent"
    data_class: DataClass              # set by the calling feature's policy
    messages: list[dict[str, str]]     # system/user/context blocks
    max_output_tokens: int = 256
    timeout_s: float = 15.0
    tools: list[str] = field(default_factory=list)


@dataclass
class AIResult:
    provider: str
    model: str
    inference: Literal["mock", "live"]
    status: str                        # ok | suppressed | failed | timeout | ...
    output: Any = None
    input_units: int = 0
    output_units: int = 0
    latency_ms: int = 0
    error: str | None = None


class Provider(Protocol):
    name: str
    inference: Literal["mock", "live"]

    def max_data_class(self, settings: Settings) -> DataClass: ...

    def configured(self, settings: Settings) -> bool: ...

    def run(self, req: AIRequest, settings: Settings) -> AIResult: ...


def current_period() -> str:
    today = clinic_today()
    return f"{today.year:04d}-{today.month:02d}"


def credits_used(db: Session, organization_id: uuid.UUID, period: str | None = None) -> int:
    return int(db.scalar(
        select(func.coalesce(func.sum(AiCreditEntry.credits), 0)).where(
            AiCreditEntry.organization_id == organization_id,
            AiCreditEntry.period == (period or current_period()),
            AiCreditEntry.entry_type == "consume",
        )) or 0)


def credits_granted(db: Session, organization_id: uuid.UUID, period: str | None = None) -> int:
    """Credits added on top of the plan allowance (purchased AI credit packs)."""
    return int(db.scalar(
        select(func.coalesce(func.sum(AiCreditEntry.credits), 0)).where(
            AiCreditEntry.organization_id == organization_id,
            AiCreditEntry.period == (period or current_period()),
            AiCreditEntry.entry_type == "grant",
        )) or 0)


def tenant_enabled_features(db: Session, organization_id: uuid.UUID) -> list[str]:
    row = db.get(AiTenantSettings, organization_id)
    return list(row.enabled_features) if row else []


def _seal(value: Any, organization_id: uuid.UUID) -> str | None:
    if value is None:
        return None
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return encrypt_field(raw[:8000], context=f"ai:{organization_id}")


def dispatch(
    db: Session,
    principal: Principal,
    req: AIRequest,
    provider: Provider,
    *,
    validate: Callable[[Any], bool],
    correlation_id: str | None = None,
    tools_called: list | None = None,
) -> tuple[AIResult, uuid.UUID]:
    """Run one AI task under every governance control; returns (result, request id).

    Raises 403 for missing entitlement / opt-in / exhausted credits so the
    caller never pays for, or silently degrades, a refused call."""
    settings = get_settings()
    org_id = principal.organization_id
    ent = load_entitlements(db, org_id)
    if req.feature not in ent.features:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail=f"Feature not included in your plan: {req.feature}")
    if req.feature not in tenant_enabled_features(db, org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="ai_not_enabled")

    started = time.monotonic()
    payload = json.dumps(req.messages, ensure_ascii=False, sort_keys=True)
    result: AIResult
    if not settings.ai_enabled:
        result = AIResult(provider=provider.name, model="-", inference=provider.inference,
                          status="suppressed", error="AI_ENABLED=false")
    elif provider.inference == "live" and not (settings.ai_live_enabled
                                               and provider.configured(settings)):
        result = AIResult(provider=provider.name, model="-", inference="live",
                          status="suppressed", error="live inference disabled")
    elif _CLASS_RANK[req.data_class] > _CLASS_RANK[provider.max_data_class(settings)]:
        result = AIResult(provider=provider.name, model="-", inference=provider.inference,
                          status="rejected_by_policy",
                          error=f"{req.data_class} above provider ceiling")
    else:
        cost = CREDIT_COSTS.get(req.task, {}).get(provider.inference, 0)
        if cost:
            # serialise credit checks per tenant for the rest of the transaction
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                       {"k": f"ai-credits:{org_id}"})
            limit = ent.limits.get("ai_credits_monthly")
            if limit is not None:
                limit += credits_granted(db, org_id)  # purchased packs (M7.2)
            if limit is not None and credits_used(db, org_id) + cost > limit:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail=f"Plan limit reached: ai_credits_monthly ({limit}). "
                           "Upgrade your plan.")
        try:
            result = provider.run(req, settings)
        except TimeoutError:
            result = AIResult(provider=provider.name, model="-", inference=provider.inference,
                              status="timeout")
        except Exception as exc:  # provider failure never crashes the request
            result = AIResult(provider=provider.name, model="-", inference=provider.inference,
                              status="failed", error=type(exc).__name__)
        if result.status == "ok" and not validate(result.output):
            result.status = "rejected_output"
    result.latency_ms = result.latency_ms or int((time.monotonic() - started) * 1000)

    charged = (CREDIT_COSTS.get(req.task, {}).get(result.inference, 0)
               if result.status in ("ok", "rejected_output") else 0)
    row = AiRequest(
        organization_id=org_id, actor_user_id=principal.user_id, feature=req.feature,
        task=req.task, provider=result.provider, model=result.model[:120],
        inference=result.inference, data_class=req.data_class, deidentified=False,
        prompt_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        prompt_redacted=_seal(payload, org_id), output_redacted=_seal(result.output, org_id),
        output_valid=(result.status == "ok") if result.status in ("ok", "rejected_output")
        else None,
        tools_called=tools_called or [], credits=charged, input_units=result.input_units,
        output_units=result.output_units, latency_ms=result.latency_ms,
        status=result.status, correlation_id=(correlation_id or "")[:64] or None,
    )
    db.add(row)
    db.flush()
    if charged:
        db.add(AiCreditEntry(organization_id=org_id, period=current_period(),
                             entry_type="consume", credits=charged, ai_request_id=row.id,
                             actor_user_id=principal.user_id, reason=req.task))
        db.flush()
    return result, row.id

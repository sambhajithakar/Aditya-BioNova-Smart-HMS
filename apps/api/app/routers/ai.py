"""AI endpoints (phase AI-0): tenant opt-in, Business Copilot, usage, audit.

Mounted behind ``require_feature("ai_copilot")`` in main.py. Asking a
question is a read: it keeps working on a read-only subscription.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import copilot
from ..ai.gateway import AIRequest, credits_used, current_period, dispatch, \
    tenant_enabled_features
from ..ai.providers import MockProvider, OpenAICompatibleProvider
from ..auditing import record_event
from ..config import get_settings
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..entitlements import FEATURES, load_entitlements
from ..models import AiRequest, AiTenantSettings
from ..schemas import AiRequestOut, AiSettingsIn, AiSettingsOut, AiUsageOut, \
    CopilotAnswerOut, CopilotAskIn, CopilotCatalogEntry, CopilotComputedWith

router = APIRouter(prefix="/ai", tags=["ai"])

AI_FEATURES = [k for k in FEATURES if k.startswith("ai_")]
# features with a working implementation; the others are entitlement switches
# for roadmap phases (docs/AI_ARCHITECTURE.md §11)
IMPLEMENTED_AI_FEATURES = {"ai_copilot"}


def _mock() -> MockProvider:
    def intent(req: AIRequest):
        question = next(m["content"] for m in req.messages if m["role"] == "user")
        return copilot.parse_intent(question) or {"function": None}

    return MockProvider({"copilot.intent": intent})


def copilot_provider():
    name = get_settings().ai_copilot_provider
    if name == "openai_compatible":
        return OpenAICompatibleProvider()
    return _mock()


@router.get("/settings", response_model=AiSettingsOut)
def get_ai_settings(
    principal: Principal = Depends(require_permission("ai.settings.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> AiSettingsOut:
    settings = get_settings()
    ent = load_entitlements(db, principal.organization_id)
    provider = copilot_provider()
    region = "in-process" if provider.name == "mock" else settings.ai_openai_region
    return AiSettingsOut(
        enabled_features=tenant_enabled_features(db, principal.organization_id),
        entitled_features=sorted(f for f in ent.features if f in AI_FEATURES),
        live_inference=settings.ai_live_enabled and provider.inference == "live",
        copilot_provider=provider.name, copilot_provider_region=region,
    )


@router.patch("/settings", response_model=AiSettingsOut)
def update_ai_settings(
    payload: AiSettingsIn,
    request: Request,
    principal: Principal = Depends(require_permission("ai.settings.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> AiSettingsOut:
    ent = load_entitlements(db, principal.organization_id)
    wanted = sorted(set(payload.enabled_features))
    bad = [f for f in wanted if f not in AI_FEATURES or f not in ent.features]
    if bad:
        raise HTTPException(status_code=422,
                            detail=f"Not entitled or unknown AI features: {', '.join(bad)}")
    row = db.get(AiTenantSettings, principal.organization_id)
    if row is None:
        row = AiTenantSettings(organization_id=principal.organization_id)
        db.add(row)
    before = list(row.enabled_features or [])
    row.enabled_features = wanted
    row.updated_by = principal.user_id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_event(db, action="ai.settings_updated",
                 organization_id=str(principal.organization_id),
                 actor_user_id=str(principal.user_id), resource_type="ai_settings",
                 resource_id=str(principal.organization_id),
                 metadata={"before": before, "after": wanted},
                 correlation_id=get_correlation_id(request), ip_address=get_client_ip(request))
    return get_ai_settings(principal=principal, db=db)


@router.get("/copilot/catalog", response_model=list[CopilotCatalogEntry])
def catalog(
    principal: Principal = Depends(require_permission("ai.copilot.use")),
) -> list[CopilotCatalogEntry]:
    return [CopilotCatalogEntry(function=k, label=v["label"], args=v["args"])
            for k, v in copilot.CATALOG.items()]


@router.post("/copilot/ask", response_model=CopilotAnswerOut)
def ask(
    payload: CopilotAskIn,
    request: Request,
    principal: Principal = Depends(require_permission("ai.copilot.use")),
    db: Session = Depends(get_db, scope="function"),
) -> CopilotAnswerOut:
    lang = payload.language or copilot.detect_language(payload.question)
    provider = copilot_provider()
    question = (payload.question if provider.name == "mock"
                else copilot.redact_question(payload.question))
    catalog_text = json.dumps({k: v["args"] for k, v in copilot.CATALOG.items()})
    req = AIRequest(
        feature="ai_copilot", task="copilot.intent", data_class="C1",
        messages=[{"role": "system", "content": copilot.SYSTEM_PROMPT + catalog_text
                   + " Periods: " + ", ".join(copilot.PERIODS)},
                  {"role": "user", "content": question}],
        max_output_tokens=256, timeout_s=15.0,
    )

    def validate(out):
        return out == {"function": None} or copilot.valid_selection(out)

    result, request_id = dispatch(db, principal, req, provider, validate=validate,
                                  correlation_id=get_correlation_id(request))
    note = None
    if result.status != "ok" and provider.name != "mock":
        # live path unavailable: fall back to the deterministic parser (audited too)
        note = f"Live AI unavailable ({result.status}); answered by the rule-based parser."
        result, request_id = dispatch(db, principal, req, _mock(), validate=validate,
                                      correlation_id=get_correlation_id(request))
    selection = result.output if result.status == "ok" else None
    if not selection or selection.get("function") is None:
        return CopilotAnswerOut(
            request_id=request_id, answered=False, language=lang,
            answer=copilot.REFUSAL[lang], figures={}, rows=[], computed_with=None,
            inference=result.inference, provider=result.provider, model=result.model,
            credits_charged=0, note=note)
    fn, args = selection["function"], selection.get("args", {})
    if "period" in copilot.CATALOG[fn]["args"]:
        args.setdefault("period", "last_30_days")
    computed = copilot.compute(db, principal, fn, args)
    row = db.get(AiRequest, request_id)
    return CopilotAnswerOut(
        request_id=request_id, answered=True, language=lang,
        answer=copilot.answer_text(fn, args, computed, lang),
        figures=computed.figures, rows=computed.rows,
        computed_with=CopilotComputedWith(function=fn, args=args, method=computed.method),
        inference=result.inference, provider=result.provider, model=result.model,
        credits_charged=row.credits if row else 0, note=note,
    )


@router.get("/usage", response_model=AiUsageOut)
def usage(
    principal: Principal = Depends(require_permission("ai.audit.read")),
    db: Session = Depends(get_db, scope="function"),
) -> AiUsageOut:
    ent = load_entitlements(db, principal.organization_id)
    return AiUsageOut(period=current_period(),
                      used_credits=credits_used(db, principal.organization_id),
                      limit_credits=ent.limits.get("ai_credits_monthly"))


@router.get("/requests", response_model=list[AiRequestOut])
def list_requests(
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_permission("ai.audit.read")),
    db: Session = Depends(get_db, scope="function"),
) -> list[AiRequestOut]:
    rows = db.scalars(select(AiRequest).where(
        AiRequest.organization_id == principal.organization_id)
        .order_by(AiRequest.created_at.desc()).limit(limit)).all()
    return [AiRequestOut.model_validate(r) for r in rows]

"""SaaS subscription billing API (M7.2): the clinic pays the VENDOR for the
software. Patient billing lives in ``routers/billing.py`` and never touches
these tables.

Not gated by ``enforce_writable``: a clinic whose subscription lapsed into
read-only mode must still be able to pay to recover.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .. import ratelimit
from ..ai.gateway import allowance_used, credits_used
from ..auditing import record_event
from ..config import get_settings
from ..db import get_db, set_request_context
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission, \
    require_platform_admin
from ..entitlements import load_entitlements
from ..models import Plan
from ..models_billing import AiCreditPack, SaasInvoice, SaasOrder, SaasPayment, SaasRefund
from ..saas_billing import service
from ..saas_billing.providers import ProviderError, SimulatorProvider, get_provider
from ..schemas_billing import (
    BillingCatalog,
    CatalogPack,
    CatalogPlan,
    CheckoutParams,
    CreditPackIn,
    CreditsOut,
    InvoiceOut,
    LifecycleOut,
    OrderCreated,
    OrderIn,
    OrderOut,
    PaymentOut,
    PaymentResult,
    ReconciliationOut,
    RefundDecisionIn,
    RefundIn,
    RefundOut,
    SimulateIn,
    VerifyIn,
)

router = APIRouter(prefix="/saas", tags=["saas-billing"])
webhooks = APIRouter(prefix="/saas/webhooks", tags=["saas-billing"])
platform = APIRouter(prefix="/platform/billing", tags=["platform"])

MAX_WEBHOOK_BYTES = 64 * 1024


def _order(db: Session, principal: Principal, order_id: uuid.UUID) -> SaasOrder:
    order = db.scalar(select(SaasOrder).where(
        SaasOrder.id == order_id, SaasOrder.organization_id == principal.organization_id))
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


# --- tenant ---------------------------------------------------------------------------
@router.get("/catalog", response_model=BillingCatalog)
def catalog(principal: Principal = Depends(require_permission("billing.saas.read")),
            db: Session = Depends(get_db, scope="function")) -> BillingCatalog:
    settings = get_settings()
    try:
        provider = get_provider(settings)
        name, mode = provider.name, provider.mode
    except ProviderError:
        name, mode = settings.payments_provider, "unavailable"
    plans = db.scalars(select(Plan).where(Plan.is_active, Plan.is_public)
                       .order_by(Plan.tier)).all()
    packs = db.scalars(select(AiCreditPack).where(AiCreditPack.is_active)
                       .order_by(AiCreditPack.credits)).all()
    notice = {"simulator": "Payment simulator — development demo, no money moves.",
              "sandbox": "Razorpay TEST mode — test cards only, no real money moves."
              }.get(mode, "Online payment is not available right now.")
    return BillingCatalog(
        provider=name, mode=mode, gst_rate_bp=settings.saas_gst_rate_bp, notice=notice,
        plans=[CatalogPlan(code=p.code, name=p.name, tier=p.tier,
                           price_monthly_paise=p.price_monthly_paise,
                           price_annual_paise=p.price_annual_paise,
                           purchasable=bool(p.price_monthly_paise or p.price_annual_paise))
               for p in plans],
        credit_packs=[CatalogPack(code=k.code, name=k.name, credits=k.credits,
                                  price_paise=k.price_paise, purchasable=bool(k.price_paise))
                      for k in packs])


@router.post("/orders", response_model=OrderCreated, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderIn,
                 idempotency_key: str = Header(..., alias="Idempotency-Key"),
                 principal: Principal = Depends(require_permission("billing.saas.pay")),
                 db: Session = Depends(get_db, scope="function")) -> OrderCreated:
    order, checkout = service.create_order(
        db, organization_id=principal.organization_id, actor_user_id=principal.user_id,
        kind=payload.kind, plan_code=payload.plan_code, billing_cycle=payload.billing_cycle,
        pack_code=payload.pack_code, idempotency_key=idempotency_key.strip())
    return OrderCreated(order=OrderOut.model_validate(order),
                        checkout=CheckoutParams(**checkout))


@router.post("/orders/{order_id}/retry", response_model=OrderCreated,
             status_code=status.HTTP_201_CREATED)
def retry_order(order_id: uuid.UUID,
                idempotency_key: str = Header(..., alias="Idempotency-Key"),
                principal: Principal = Depends(require_permission("billing.saas.pay")),
                db: Session = Depends(get_db, scope="function")) -> OrderCreated:
    """Failed-payment recovery: a fresh order for the same item at today's price."""
    old = _order(db, principal, order_id)
    if old.status not in ("failed", "expired", "cancelled"):
        raise HTTPException(409, detail=f"Order is {old.status}; only failed or expired "
                                        "orders can be retried")
    plan_code = db.get(Plan, old.plan_id).code if old.plan_id else None
    pack_code = db.get(AiCreditPack, old.pack_id).code if old.pack_id else None
    order, checkout = service.create_order(
        db, organization_id=principal.organization_id, actor_user_id=principal.user_id,
        kind=old.kind, plan_code=plan_code, billing_cycle=old.billing_cycle,
        pack_code=pack_code, idempotency_key=idempotency_key.strip())
    return OrderCreated(order=OrderOut.model_validate(order),
                        checkout=CheckoutParams(**checkout))


@router.get("/orders", response_model=list[OrderOut])
def list_orders(principal: Principal = Depends(require_permission("billing.saas.read")),
                db: Session = Depends(get_db, scope="function"),
                limit: int = Query(50, ge=1, le=200)) -> list[SaasOrder]:
    return db.scalars(select(SaasOrder).where(
        SaasOrder.organization_id == principal.organization_id)
        .order_by(SaasOrder.created_at.desc()).limit(limit)).all()


@router.post("/orders/{order_id}/verify", response_model=PaymentResult)
def verify_payment(order_id: uuid.UUID, payload: VerifyIn, request: Request,
                   principal: Principal = Depends(require_permission("billing.saas.pay")),
                   db: Session = Depends(get_db, scope="function")) -> PaymentResult:
    """Browser callback after the hosted checkout. The signature is checked
    server-side; the webhook remains the safety net if the browser never
    comes back."""
    ratelimit.hit("saas-verify", str(principal.user_id), limit=20, window_seconds=60)
    order = _order(db, principal, order_id)
    outcome = service.verify_checkout(db, order, payload.provider_payment_id,
                                      payload.signature)
    db.refresh(order)
    return PaymentResult(outcome=outcome, order=OrderOut.model_validate(order))


@router.post("/orders/{order_id}/simulate", response_model=PaymentResult)
def simulate_payment(order_id: uuid.UUID, payload: SimulateIn,
                     principal: Principal = Depends(require_permission("billing.saas.pay")),
                     db: Session = Depends(get_db, scope="function")) -> PaymentResult:
    """Development demo only: plays the hosted checkout AND the provider's
    webhook for a simulator order, through the real verification code."""
    order = _order(db, principal, order_id)
    settings = get_settings()
    if order.provider != "simulator" or not settings.is_dev:
        raise HTTPException(404, detail="Not available")
    sim = get_provider(settings, "simulator")
    assert isinstance(sim, SimulatorProvider)
    payment_id = "pay_SIM" + uuid.uuid4().hex[:16]
    if payload.outcome == "success":
        outcome = service.verify_checkout(db, order, payment_id,
                                          sim.sign_checkout(order.provider_order_id,
                                                            payment_id))
        event = "payment.captured"
    else:
        outcome, event = "failed", "payment.failed"
    body = _simulated_event(event, order, payment_id)
    _, webhook_outcome = service.handle_webhook(db, "simulator", body, sim.sign_webhook(body),
                                                f"evt_SIM{uuid.uuid4().hex[:12]}")
    if payload.outcome == "failure":
        outcome = webhook_outcome
    db.refresh(order)
    return PaymentResult(outcome=outcome, order=OrderOut.model_validate(order))


def _simulated_event(event: str, order: SaasOrder, payment_id: str) -> bytes:
    import json

    entity = {"id": payment_id, "order_id": order.provider_order_id,
              "amount": order.total_paise, "currency": order.currency, "method": "upi",
              "status": "captured" if event == "payment.captured" else "failed"}
    if event == "payment.failed":
        entity["error_description"] = "Simulated decline (demo)"
    return json.dumps({"event": event, "payload": {"payment": {"entity": entity}}},
                      separators=(",", ":")).encode()


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(principal: Principal = Depends(require_permission("billing.saas.read")),
                  db: Session = Depends(get_db, scope="function")) -> list[SaasPayment]:
    return db.scalars(select(SaasPayment).where(
        SaasPayment.organization_id == principal.organization_id)
        .order_by(SaasPayment.created_at.desc()).limit(200)).all()


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(principal: Principal = Depends(require_permission("billing.saas.read")),
                  db: Session = Depends(get_db, scope="function")) -> list[SaasInvoice]:
    return db.scalars(select(SaasInvoice).where(
        SaasInvoice.organization_id == principal.organization_id)
        .order_by(SaasInvoice.issued_at.desc()).limit(200)).all()


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: uuid.UUID,
                principal: Principal = Depends(require_permission("billing.saas.read")),
                db: Session = Depends(get_db, scope="function")) -> SaasInvoice:
    inv = db.scalar(select(SaasInvoice).where(
        SaasInvoice.id == invoice_id, SaasInvoice.organization_id == principal.organization_id))
    if inv is None:
        raise HTTPException(404, detail="Invoice not found")
    return inv


@router.post("/refunds", response_model=RefundOut, status_code=status.HTTP_201_CREATED)
def request_refund(payload: RefundIn,
                   principal: Principal = Depends(
                       require_permission("billing.saas.refund_request")),
                   db: Session = Depends(get_db, scope="function")) -> SaasRefund:
    return service.request_refund(db, organization_id=principal.organization_id,
                                  actor_user_id=principal.user_id,
                                  payment_id=payload.payment_id,
                                  amount_paise=payload.amount_paise, reason=payload.reason)


@router.get("/refunds", response_model=list[RefundOut])
def list_refunds(principal: Principal = Depends(require_permission("billing.saas.read")),
                 db: Session = Depends(get_db, scope="function")) -> list[SaasRefund]:
    return db.scalars(select(SaasRefund).where(
        SaasRefund.organization_id == principal.organization_id)
        .order_by(SaasRefund.created_at.desc())).all()


@router.get("/credits", response_model=CreditsOut)
def ai_credits(principal: Principal = Depends(require_permission("billing.saas.read")),
               db: Session = Depends(get_db, scope="function")) -> CreditsOut:
    org = principal.organization_id
    ent = load_entitlements(db, org)
    allowance = ent.limits.get("ai_credits_monthly")
    from_allowance = allowance_used(db, org)
    balance = service.purchased_balance(db, org)
    remaining = (None if allowance is None
                 else max(0, allowance - from_allowance) + balance)
    return CreditsOut(period=service.credit_period(), plan_allowance=allowance,
                      allowance_used=from_allowance, purchased=balance,
                      purchased_total=service.credits_purchased(db, org),
                      used=credits_used(db, org), remaining=remaining)


# --- provider webhooks (no session; the HMAC signature is the authentication) ------
async def _webhook(provider_name: str, request: Request, db: Session) -> JSONResponse:
    await run_in_threadpool(ratelimit.hit, "saas-webhook-ip", get_client_ip(request),
                            limit=120, window_seconds=60)
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        return JSONResponse({"detail": "payload too large"}, status_code=413)
    # the DB work blocks (row locks): run it off the event loop, or one webhook
    # waiting on a lock would stall every request, including the lock holder
    code, detail = await run_in_threadpool(
        service.handle_webhook, db, provider_name, raw,
        request.headers.get("X-Razorpay-Signature"), request.headers.get("X-Razorpay-Event-Id"))
    return JSONResponse({"detail": detail}, status_code=code)


@webhooks.post("/razorpay", include_in_schema=True)
async def razorpay_webhook(request: Request,
                           db: Session = Depends(get_db, scope="function")) -> JSONResponse:
    return await _webhook("razorpay", request, db)


@webhooks.post("/simulator", include_in_schema=False)
async def simulator_webhook(request: Request,
                            db: Session = Depends(get_db, scope="function")) -> JSONResponse:
    if not get_settings().is_dev:
        raise HTTPException(404, detail="Not found")
    return await _webhook("simulator", request, db)


# --- platform (vendor) console --------------------------------------------------------
def _paudit(db: Session, principal: Principal, request: Request, action: str,
            target: uuid.UUID | str | None, metadata: dict | None = None) -> None:
    record_event(db, action=action, organization_id=str(principal.organization_id),
                 actor_user_id=str(principal.user_id), resource_type="platform_billing",
                 resource_id=str(target) if target else None, metadata=metadata,
                 correlation_id=get_correlation_id(request), ip_address=get_client_ip(request))


@platform.get("/orders", response_model=list[OrderOut])
def platform_orders(principal: Principal = Depends(require_platform_admin),
                    db: Session = Depends(get_db, scope="function"),
                    status_: str | None = Query(None, alias="status"),
                    organization_id: uuid.UUID | None = None,
                    limit: int = Query(100, ge=1, le=500)) -> list[SaasOrder]:
    q = select(SaasOrder).order_by(SaasOrder.created_at.desc()).limit(limit)
    if status_:
        q = q.where(SaasOrder.status == status_)
    if organization_id:
        q = q.where(SaasOrder.organization_id == organization_id)
    return db.scalars(q).all()


@platform.get("/refunds", response_model=list[RefundOut])
def platform_refunds(principal: Principal = Depends(require_platform_admin),
                     db: Session = Depends(get_db, scope="function"),
                     status_: str | None = Query("requested", alias="status")
                     ) -> list[SaasRefund]:
    q = select(SaasRefund).order_by(SaasRefund.created_at)
    if status_:
        q = q.where(SaasRefund.status == status_)
    return db.scalars(q).all()


@platform.post("/refunds/{refund_id}/decide", response_model=RefundOut)
def platform_decide_refund(refund_id: uuid.UUID, payload: RefundDecisionIn, request: Request,
                           principal: Principal = Depends(require_platform_admin),
                           db: Session = Depends(get_db, scope="function")) -> SaasRefund:
    refund = service.decide_refund(db, refund_id, approve=payload.approve,
                                   decider_user_id=principal.user_id, note=payload.note)
    _paudit(db, principal, request, f"platform.saas_refund.{refund.status}", refund.id,
            {"organization_id": str(refund.organization_id),
             "amount_paise": refund.amount_paise})
    if refund.status != "processing":
        return refund
    # the approval is durable BEFORE any money moves (see service.decide_refund)
    _commit_keeping_scope(db, principal)
    return _execute_refund(db, principal, request, refund.id)


@platform.post("/refunds/{refund_id}/resume", response_model=RefundOut)
def platform_resume_refund(refund_id: uuid.UUID, request: Request,
                           principal: Principal = Depends(require_platform_admin),
                           db: Session = Depends(get_db, scope="function")) -> SaasRefund:
    """Re-check an approved refund whose provider outcome is not yet known
    (listed by reconciliation as ``refund_processing``). Never refunds twice:
    the provider is asked for this refund's reference first."""
    refund = db.get(SaasRefund, refund_id)
    if refund is None:
        raise HTTPException(404, detail="Refund not found")
    if refund.status != "processing":
        raise HTTPException(409, detail=f"Refund is {refund.status}, not processing")
    return _execute_refund(db, principal, request, refund.id)


def _commit_keeping_scope(db: Session, principal: Principal) -> None:
    """Commit, then reinstall the request's transaction-local RLS context."""
    db.commit()
    set_request_context(db, user_id=str(principal.user_id),
                        org_id=str(principal.organization_id))
    db.execute(text("SELECT set_config('app.platform_admin', 'true', true)"))


def _execute_refund(db: Session, principal: Principal, request: Request,
                    refund_id: uuid.UUID) -> SaasRefund:
    refund = service.execute_refund(db, refund_id)
    _paudit(db, principal, request, f"platform.saas_refund.{refund.status}", refund.id,
            {"organization_id": str(refund.organization_id),
             "amount_paise": refund.amount_paise, "error": refund.error})
    return refund


@platform.post("/lifecycle", response_model=LifecycleOut)
def platform_lifecycle(request: Request, principal: Principal = Depends(require_platform_admin),
                       db: Session = Depends(get_db, scope="function")) -> LifecycleOut:
    counts = service.run_lifecycle(db)
    _paudit(db, principal, request, "platform.saas_lifecycle.run", None, counts)
    return LifecycleOut(**counts)


@platform.get("/reconciliation", response_model=ReconciliationOut)
def platform_reconciliation(principal: Principal = Depends(require_platform_admin),
                            db: Session = Depends(get_db, scope="function"),
                            check_provider: bool = False) -> ReconciliationOut:
    return ReconciliationOut(checked_at=datetime.now(timezone.utc),
                             issues=service.reconciliation(db, check_provider))


@platform.get("/credit-packs", response_model=list[CatalogPack])
def platform_packs(principal: Principal = Depends(require_platform_admin),
                   db: Session = Depends(get_db, scope="function")) -> list[CatalogPack]:
    return [CatalogPack(code=k.code, name=k.name, credits=k.credits, price_paise=k.price_paise,
                        purchasable=bool(k.price_paise and k.is_active))
            for k in db.scalars(select(AiCreditPack).order_by(AiCreditPack.credits)).all()]


@platform.put("/credit-packs/{code}", response_model=CatalogPack)
def platform_put_pack(code: str, payload: CreditPackIn, request: Request,
                      principal: Principal = Depends(require_platform_admin),
                      db: Session = Depends(get_db, scope="function")) -> CatalogPack:
    if not code.replace("_", "").isalnum() or len(code) > 40:
        raise HTTPException(422, detail="Invalid pack code")
    pack = db.scalar(select(AiCreditPack).where(AiCreditPack.code == code))
    if pack is None:
        pack = AiCreditPack(code=code, name=payload.name, credits=payload.credits)
        db.add(pack)
    pack.name, pack.credits = payload.name, payload.credits
    pack.price_paise, pack.is_active = payload.price_paise, payload.is_active
    db.flush()
    _paudit(db, principal, request, "platform.ai_credit_pack.put", code,
            payload.model_dump())
    return CatalogPack(code=pack.code, name=pack.name, credits=pack.credits,
                       price_paise=pack.price_paise,
                       purchasable=bool(pack.price_paise and pack.is_active))

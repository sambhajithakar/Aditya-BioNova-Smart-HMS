"""SaaS subscription billing: orders → verified payments → fulfilment →
GST invoices; refunds with four-eyes approval; lifecycle; reconciliation.

Money rules:
* amounts are integer paise, computed ONLY on the server from the plan /
  credit-pack catalogue; a client never sends an amount;
* a payment is accepted only with a valid provider signature (checkout
  ``order_id|payment_id`` HMAC, or the webhook body HMAC) AND an amount +
  currency equal to the order;
* fulfilment is idempotent: the order row is locked ``FOR UPDATE``; the
  provider payment id is unique; webhook events are de-duplicated by id —
  a replayed or concurrent capture never extends a subscription twice;
* payments, invoices and webhook events are append-only; refunds produce
  credit notes.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.gateway import credits_granted  # noqa: F401  (re-exported)
from ..auditing import record_event
from ..config import Settings, get_settings
from ..models import AiCreditEntry, Organization, Plan, Subscription
from ..models_billing import AiCreditPack, SaasInvoice, SaasOrder, SaasPayment, SaasRefund, \
    SaasWebhookEvent
from ..services.subscriptions import record_subscription_event
from ..timeutil import clinic_today
from .providers import PaymentProvider, ProviderError, get_provider


# --- scopes -----------------------------------------------------------------------
@contextmanager
def system_scope(db: Session, organization_id: uuid.UUID | None = None) -> Iterator[None]:
    """Open the commercial tables for billing state changes (same GUC as the
    platform console) and, optionally, the tenant context of the order so the
    audit trail lands in that tenant. Restored on exit."""
    prev_org = db.execute(text("SELECT current_setting('app.current_org_id', true)")).scalar()
    db.execute(text("SELECT set_config('app.platform_admin', 'true', true)"))
    if organization_id is not None:
        db.execute(text("SELECT set_config('app.current_org_id', :v, true)"),
                   {"v": str(organization_id)})
    try:
        yield
    finally:
        db.execute(text("SELECT set_config('app.platform_admin', '', true)"))
        if organization_id is not None:
            db.execute(text("SELECT set_config('app.current_org_id', :v, true)"),
                       {"v": prev_org or ""})


# --- money helpers ------------------------------------------------------------------
def gst_on(amount_paise: int, rate_bp: int) -> int:
    """GST rounded half-up to the paisa."""
    return (amount_paise * rate_bp + 5000) // 10000


def split_inclusive(total_paise: int, rate_bp: int) -> tuple[int, int]:
    """(taxable, tax) parts of a tax-inclusive amount (used for credit notes)."""
    taxable = (total_paise * 10000 + (10000 + rate_bp) // 2) // (10000 + rate_bp)
    return taxable, total_paise - taxable


def add_months(dt: datetime, months: int) -> datetime:
    m = dt.month - 1 + months
    year, month = dt.year + m // 12, m % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def financial_year(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def credit_period(d: date | None = None) -> str:
    d = d or clinic_today()
    return f"{d.year:04d}-{d.month:02d}"


# --- orders ---------------------------------------------------------------------------
def _price(plan: Plan, cycle: str) -> int | None:
    return plan.price_monthly_paise if cycle == "monthly" else plan.price_annual_paise


def create_order(db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID,
                 kind: str, plan_code: str | None, billing_cycle: str | None,
                 pack_code: str | None, idempotency_key: str,
                 settings: Settings | None = None) -> tuple[SaasOrder, dict]:
    settings = settings or get_settings()
    if not idempotency_key or len(idempotency_key) > 100:
        raise HTTPException(422, detail="Idempotency-Key header (1–100 chars) is required")
    existing = db.scalar(select(SaasOrder).where(
        SaasOrder.organization_id == organization_id,
        SaasOrder.idempotency_key == idempotency_key))

    plan = pack = None
    if kind == "subscription":
        plan = db.scalar(select(Plan).where(Plan.code == (plan_code or "")))
        if plan is None or not (plan.is_active and plan.is_public):
            raise HTTPException(422, detail="Unknown or unavailable plan")
        if billing_cycle not in ("monthly", "annual"):
            raise HTTPException(422, detail="billing_cycle must be monthly or annual")
        amount = _price(plan, billing_cycle)
        description = f"{plan.name} — {billing_cycle} subscription"
    elif kind == "ai_credits":
        pack = db.scalar(select(AiCreditPack).where(AiCreditPack.code == (pack_code or "")))
        if pack is None or not pack.is_active:
            raise HTTPException(422, detail="Unknown or unavailable AI credit pack")
        amount = pack.price_paise
        description = pack.name
    else:
        raise HTTPException(422, detail="kind must be subscription or ai_credits")
    if not amount:  # unset (NULL) or zero: nothing to charge online
        raise HTTPException(409, detail="price_not_configured: the vendor has not set a price "
                                        "for this item yet")

    if existing is not None:
        same = (existing.kind == kind and existing.plan_id == (plan.id if plan else None)
                and existing.billing_cycle == (billing_cycle if plan else None)
                and existing.pack_id == (pack.id if pack else None))
        if not same:
            raise HTTPException(409, detail="Idempotency-Key reused for a different order")
        return existing, checkout_params(existing)

    if kind == "subscription":
        sub = db.scalar(select(Subscription).where(
            Subscription.organization_id == organization_id))
        if sub is not None and sub.status in ("suspended", "cancelled"):
            raise HTTPException(409, detail=f"Subscription is {sub.status}; contact support")

    tax = gst_on(amount, settings.saas_gst_rate_bp)
    order_uuid = uuid.uuid4()
    try:
        provider = get_provider(settings)
        created = provider.create_order(
            amount_paise=amount + tax, currency="INR", receipt=str(order_uuid),
            notes={"organization_id": str(organization_id), "order": str(order_uuid)})
    except ProviderError as exc:
        raise HTTPException(503, detail=f"Payment provider unavailable: {exc}") from exc
    order = SaasOrder(
        id=order_uuid, organization_id=organization_id, kind=kind,
        plan_id=plan.id if plan else None, billing_cycle=billing_cycle if plan else None,
        pack_id=pack.id if pack else None, credits=pack.credits if pack else None,
        description=description, amount_paise=amount, tax_paise=tax,
        total_paise=amount + tax, currency="INR", gst_rate_bp=settings.saas_gst_rate_bp,
        provider=provider.name, provider_order_id=created.provider_order_id,
        idempotency_key=idempotency_key, status="created", created_by=actor_user_id)
    db.add(order)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:  # a concurrent request with the same key won the race
        db.expunge(order)
        winner = db.scalar(select(SaasOrder).where(
            SaasOrder.organization_id == organization_id,
            SaasOrder.idempotency_key == idempotency_key))
        if winner is None:
            raise
        return winner, checkout_params(winner)
    record_event(db, action="saas.order.created", organization_id=str(organization_id),
                 actor_user_id=str(actor_user_id), resource_type="saas_order",
                 resource_id=str(order.id),
                 metadata={"kind": kind, "total_paise": order.total_paise,
                           "provider": provider.name})
    return order, checkout_params(order, provider)


def checkout_params(order: SaasOrder, provider: PaymentProvider | None = None) -> dict:
    provider = provider or get_provider(get_settings(), order.provider)
    key_id = getattr(provider, "key_id", "simulator")
    return {"provider": order.provider, "mode": provider.mode, "key_id": key_id,
            "provider_order_id": order.provider_order_id, "amount": order.total_paise,
            "currency": order.currency}


# --- payment recording + fulfilment ---------------------------------------------------
def record_payment(db: Session, order_id: uuid.UUID, organization_id: uuid.UUID, *,
                   provider_payment_id: str, amount_paise: int, currency: str, captured: bool,
                   method: str | None, source: str, error: str | None = None) -> str:
    """Record a VERIFIED provider payment and fulfil the order once. Returns an
    outcome: processed | duplicate | mismatch | failed_recorded | already_paid."""
    with system_scope(db, organization_id):
        order = db.scalar(select(SaasOrder).where(
            SaasOrder.id == order_id, SaasOrder.organization_id == organization_id
        ).with_for_update())
        if order is None:
            return "ignored"
        if db.scalar(select(SaasPayment.id).where(
                SaasPayment.provider_payment_id == provider_payment_id)) is not None:
            return "duplicate"
        if captured and (amount_paise != order.total_paise or currency != order.currency):
            record_event(db, action="saas.payment.mismatch",
                         organization_id=str(order.organization_id),
                         resource_type="saas_order", resource_id=str(order.id),
                         metadata={"expected": order.total_paise, "got": amount_paise,
                                   "currency": currency, "payment": provider_payment_id})
            return "mismatch"
        db.add(SaasPayment(
            organization_id=order.organization_id, order_id=order.id, provider=order.provider,
            provider_payment_id=provider_payment_id[:64], amount_paise=amount_paise or 1,
            currency=currency, status="captured" if captured else "failed",
            method=(method or None) and method[:30], source=source,
            signature_verified=True, error=(error or None) and error[:300]))
        db.flush()
        if not captured:
            if order.status == "created":
                order.status = "failed"
                order.failure_reason = (error or "payment failed")[:300]
            record_event(db, action="saas.payment.failed",
                         organization_id=str(order.organization_id),
                         resource_type="saas_order", resource_id=str(order.id),
                         metadata={"payment": provider_payment_id, "error": error})
            db.flush()
            return "failed_recorded"
        if order.status == "paid":
            # a second successful capture for one order: keep it, flag it for
            # reconciliation/refund — never extend the subscription twice
            record_event(db, action="saas.payment.duplicate_capture",
                         organization_id=str(order.organization_id),
                         resource_type="saas_order", resource_id=str(order.id),
                         metadata={"payment": provider_payment_id})
            return "already_paid"
        order.status = "paid"
        order.paid_at = datetime.now(timezone.utc)
        order.failure_reason = None
        db.flush()
        period = _fulfil(db, order)
        _issue_invoice(db, order, period)
        record_event(db, action="saas.order.paid", organization_id=str(order.organization_id),
                     resource_type="saas_order", resource_id=str(order.id),
                     metadata={"total_paise": order.total_paise, "source": source,
                               "payment": provider_payment_id})
    return "processed"


def _fulfil(db: Session, order: SaasOrder) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(timezone.utc)
    if order.kind == "ai_credits":
        db.add(AiCreditEntry(organization_id=order.organization_id, period=credit_period(),
                             entry_type="grant", credits=int(order.credits or 0),
                             actor_user_id=order.created_by,
                             reason=f"purchased {order.description}"[:300]))
        db.flush()
        return None, None
    sub = db.scalar(select(Subscription).where(
        Subscription.organization_id == order.organization_id).with_for_update())
    plan = db.get(Plan, order.plan_id)
    months = 12 if order.billing_cycle == "annual" else 1
    # renewal of the same plan extends from the current period end; a new or
    # changed plan starts now (no proration in M7.2 — documented)
    if (sub is not None and sub.plan_id == order.plan_id and sub.status == "active"
            and sub.current_period_end and sub.current_period_end > now):
        start = sub.current_period_end
    else:
        start = now
    end = add_months(start, months)
    if sub is None:
        sub = Subscription(organization_id=order.organization_id, plan_id=order.plan_id,
                           status="active")
        db.add(sub)
        from_plan = from_status = None
    else:
        old_plan = db.get(Plan, sub.plan_id)
        from_plan, from_status = (old_plan.code if old_plan else None), sub.status
    sub.plan_id = order.plan_id
    sub.status = "active"
    sub.billing_cycle = order.billing_cycle or "monthly"
    sub.trial_ends_at = None
    sub.grace_until = None
    if start == now:
        sub.current_period_start = now
    sub.current_period_end = end
    db.flush()
    record_subscription_event(
        db, order.organization_id, from_plan=from_plan, to_plan=plan.code,
        from_status=from_status, to_status="active",
        reason=f"payment received ({order.provider}) — {order.billing_cycle} until "
               f"{end.date().isoformat()}", actor_user_id=order.created_by)
    return start, end


def _seller(settings: Settings) -> dict:
    return {"name": settings.saas_seller_name, "gstin": settings.saas_seller_gstin,
            "state": settings.saas_seller_state, "address": settings.saas_seller_address}


def _buyer(db: Session, organization_id: uuid.UUID) -> dict:
    org = db.get(Organization, organization_id)
    address = ", ".join(x for x in (org.address_line1, org.address_line2, org.city,
                                    org.pincode) if x)
    return {"name": org.legal_name or org.name, "gstin": org.gstin, "state": org.state,
            "address": address}


def _tax_breakdown(tax: int, rate_bp: int, seller_state: str, buyer_state: str | None
                   ) -> dict:
    # place of supply = buyer's state; unknown → treated as intra-state
    intra = (not buyer_state) or buyer_state.strip().lower() == seller_state.strip().lower()
    if intra:
        cgst = tax // 2
        return {"type": "intra_state", "cgst_bp": rate_bp // 2, "sgst_bp": rate_bp - rate_bp // 2,
                "cgst_paise": cgst, "sgst_paise": tax - cgst}
    return {"type": "inter_state", "igst_bp": rate_bp, "igst_paise": tax}


def _next_number(db: Session, seq: str, prefix: str) -> str:
    n = db.execute(text(f"SELECT nextval('{seq}')")).scalar()
    return f"{prefix}/{financial_year(clinic_today())}/{int(n):06d}"


def _issue_invoice(db: Session, order: SaasOrder,
                   period: tuple[datetime | None, datetime | None]) -> SaasInvoice:
    settings = get_settings()
    seller, buyer = _seller(settings), _buyer(db, order.organization_id)
    inv = SaasInvoice(
        organization_id=order.organization_id,
        number=_next_number(db, "saas_invoice_number_seq", "BNS"), kind="invoice",
        order_id=order.id, period_start=period[0], period_end=period[1], seller=seller,
        buyer=buyer,
        lines=[{"description": order.description, "sac": "998314", "quantity": 1,
                "amount_paise": order.amount_paise}],
        subtotal_paise=order.amount_paise,
        tax_breakdown=_tax_breakdown(order.tax_paise, order.gst_rate_bp, seller["state"],
                                     buyer.get("state")),
        tax_paise=order.tax_paise, total_paise=order.total_paise, currency=order.currency)
    db.add(inv)
    db.flush()
    return inv


# --- checkout verification (browser callback) ----------------------------------------
def verify_checkout(db: Session, order: SaasOrder, provider_payment_id: str,
                    signature: str) -> str:
    provider = get_provider(get_settings(), order.provider)
    if not provider.checkout_signature_ok(order.provider_order_id, provider_payment_id,
                                          signature):
        record_event(db, action="saas.payment.signature_invalid",
                     organization_id=str(order.organization_id), resource_type="saas_order",
                     resource_id=str(order.id), metadata={"payment": provider_payment_id[:64]})
        raise HTTPException(400, detail="Payment signature verification failed")
    # the signature binds this payment id to this order; the amount is the order's
    return record_payment(db, order.id, order.organization_id,
                          provider_payment_id=provider_payment_id,
                          amount_paise=order.total_paise, currency=order.currency,
                          captured=True, method=None, source="checkout")


# --- webhooks -------------------------------------------------------------------------
def handle_webhook(db: Session, provider_name: str, raw_body: bytes, signature: str | None,
                   event_id: str | None) -> tuple[int, str]:
    settings = get_settings()
    try:
        provider = get_provider(settings, provider_name)
    except ProviderError:
        return 404, "provider not enabled"
    digest = hashlib.sha256(raw_body).hexdigest()
    event_id = (event_id or f"sha256:{digest}")[:100]
    valid = provider.webhook_signature_ok(raw_body, signature)
    try:
        payload = json.loads(raw_body) if valid else None
    except ValueError:
        payload, valid = None, False
    event_type = (payload or {}).get("event", "unknown")[:60] if valid else "unverified"

    def _log(outcome: str, detail: str = "", org: uuid.UUID | None = None) -> None:
        with system_scope(db):
            try:
                with db.begin_nested():
                    db.add(SaasWebhookEvent(
                        provider=provider.name, event_id=event_id, event_type=event_type,
                        signature_valid=valid, payload_sha256=digest,
                        payload=payload if valid else None, organization_id=org,
                        outcome=outcome, detail=detail[:300]))
                    db.flush()
            except IntegrityError:
                pass  # same event id logged concurrently

    if not valid:
        _log("rejected", "invalid signature")
        return 400, "invalid signature"
    with system_scope(db):
        seen = db.scalar(select(SaasWebhookEvent.id).where(
            SaasWebhookEvent.provider == provider.name, SaasWebhookEvent.event_id == event_id,
            SaasWebhookEvent.outcome != "rejected"))
    if seen is not None:
        return 200, "duplicate"

    entity = (((payload.get("payload") or {}).get("payment") or {}).get("entity") or {})
    if event_type not in ("payment.captured", "payment.failed", "order.paid") or not entity:
        _log("ignored", f"event {event_type} not used")
        return 200, "ignored"
    with system_scope(db):
        order = db.scalar(select(SaasOrder).where(
            SaasOrder.provider_order_id == str(entity.get("order_id", ""))[:64]))
    if order is None:
        _log("ignored", "unknown order")
        return 200, "ignored"
    outcome = record_payment(
        db, order.id, order.organization_id, provider_payment_id=str(entity.get("id", ""))[:64],
        amount_paise=int(entity.get("amount") or 0), currency=str(entity.get("currency", "")),
        captured=event_type != "payment.failed", method=entity.get("method"),
        source="webhook", error=entity.get("error_description"))
    _log({"processed": "processed", "failed_recorded": "processed", "duplicate": "duplicate",
          "already_paid": "processed", "mismatch": "mismatch"}.get(outcome, "ignored"),
         outcome, order.organization_id)
    return 200, outcome


# --- refunds --------------------------------------------------------------------------
def refundable_paise(db: Session, payment: SaasPayment) -> int:
    taken = db.scalar(select(func.coalesce(func.sum(SaasRefund.amount_paise), 0)).where(
        SaasRefund.payment_id == payment.id,
        SaasRefund.status.in_(("requested", "processed")))) or 0
    return payment.amount_paise - int(taken)


def request_refund(db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID,
                   payment_id: uuid.UUID, amount_paise: int, reason: str) -> SaasRefund:
    payment = db.scalar(select(SaasPayment).where(SaasPayment.id == payment_id,
                                                  SaasPayment.organization_id ==
                                                  organization_id))
    if payment is None or payment.status != "captured":
        raise HTTPException(404, detail="Payment not found")
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
               {"k": f"saas-refund:{payment.id}"})
    if amount_paise <= 0 or amount_paise > refundable_paise(db, payment):
        raise HTTPException(422, detail="Refund exceeds the refundable amount")
    refund = SaasRefund(organization_id=organization_id, payment_id=payment.id,
                        amount_paise=amount_paise, reason=reason[:500], status="requested",
                        requested_by=actor_user_id)
    db.add(refund)
    db.flush()
    record_event(db, action="saas.refund.requested", organization_id=str(organization_id),
                 actor_user_id=str(actor_user_id), resource_type="saas_refund",
                 resource_id=str(refund.id), metadata={"amount_paise": amount_paise})
    return refund


def decide_refund(db: Session, refund_id: uuid.UUID, *, approve: bool,
                  decider_user_id: uuid.UUID, note: str) -> SaasRefund:
    """Platform (vendor) decision. Caller must already hold the platform scope."""
    refund = db.scalar(select(SaasRefund).where(SaasRefund.id == refund_id).with_for_update())
    if refund is None:
        raise HTTPException(404, detail="Refund not found")
    if refund.status != "requested":
        raise HTTPException(409, detail=f"Refund is already {refund.status}")
    if refund.requested_by == decider_user_id:
        raise HTTPException(403, detail="Four-eyes rule: the requester cannot decide")
    refund.decided_by, refund.decided_at = decider_user_id, datetime.now(timezone.utc)
    refund.decision_note = note[:500] or None
    if not approve:
        refund.status = "rejected"
        db.flush()
        return refund
    payment = db.get(SaasPayment, refund.payment_id)
    order = db.get(SaasOrder, payment.order_id)
    try:
        refund.provider_refund_id = get_provider(get_settings(), order.provider).refund(
            payment.provider_payment_id, refund.amount_paise, {"refund": str(refund.id)})
        refund.status = "processed"
    except ProviderError as exc:
        refund.status, refund.error = "failed", str(exc)[:300]
        db.flush()
        return refund
    db.flush()
    original = db.scalar(select(SaasInvoice).where(SaasInvoice.order_id == order.id,
                                                   SaasInvoice.kind == "invoice"))
    taxable, tax = split_inclusive(refund.amount_paise, order.gst_rate_bp)
    settings = get_settings()
    db.add(SaasInvoice(
        organization_id=order.organization_id,
        number=_next_number(db, "saas_credit_note_number_seq", "BNS-CN"), kind="credit_note",
        order_id=order.id, refund_id=refund.id,
        related_invoice_id=original.id if original else None, seller=_seller(settings),
        buyer=_buyer(db, order.organization_id),
        lines=[{"description": f"Refund — {order.description}"
                               + (f" (invoice {original.number})" if original else ""),
                "sac": "998314", "quantity": 1, "amount_paise": taxable}],
        subtotal_paise=taxable,
        tax_breakdown=_tax_breakdown(tax, order.gst_rate_bp, settings.saas_seller_state,
                                     _buyer(db, order.organization_id).get("state")),
        tax_paise=tax, total_paise=refund.amount_paise, currency=order.currency))
    db.flush()
    return refund


# --- lifecycle ------------------------------------------------------------------------
def run_lifecycle(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Caller holds the platform scope. Period ended → past_due with grace;
    grace over → read_only (reads keep working); stale orders expire."""
    now = now or datetime.now(timezone.utc)
    grace = timedelta(days=get_settings().saas_grace_days)
    counts = {"past_due": 0, "read_only": 0, "orders_expired": 0}
    for sub in db.scalars(select(Subscription).where(
            Subscription.status == "active", Subscription.current_period_end.is_not(None),
            Subscription.current_period_end <= now).with_for_update()).all():
        sub.status, sub.grace_until = "past_due", sub.current_period_end + grace
        record_subscription_event(db, sub.organization_id, from_plan=None, to_plan=None,
                                  from_status="active", to_status="past_due",
                                  reason="billing period ended without renewal",
                                  actor_user_id=None)
        counts["past_due"] += 1
    for sub in db.scalars(select(Subscription).where(
            Subscription.status == "past_due", Subscription.grace_until.is_not(None),
            Subscription.grace_until <= now).with_for_update()).all():
        sub.status = "read_only"
        record_subscription_event(db, sub.organization_id, from_plan=None, to_plan=None,
                                  from_status="past_due", to_status="read_only",
                                  reason="grace period ended", actor_user_id=None)
        counts["read_only"] += 1
    for order in db.scalars(select(SaasOrder).where(
            SaasOrder.status == "created",
            SaasOrder.created_at <= now - timedelta(hours=24))).all():
        order.status = "expired"
        counts["orders_expired"] += 1
    db.flush()
    return counts


# --- reconciliation -------------------------------------------------------------------
def reconciliation(db: Session, check_provider: bool = False) -> list[dict]:
    """Caller holds the platform scope. Lists every inconsistency found."""
    issues: list[dict] = []

    def issue(kind: str, **kw) -> None:
        issues.append({"kind": kind, **{k: str(v) for k, v in kw.items()}})

    captured_sum = (select(SaasPayment.order_id,
                           func.sum(SaasPayment.amount_paise).label("paid"),
                           func.count().label("n"))
                    .where(SaasPayment.status == "captured").group_by(SaasPayment.order_id)
                    .subquery())
    for order, paid, n in db.execute(
            select(SaasOrder, captured_sum.c.paid, captured_sum.c.n)
            .outerjoin(captured_sum, captured_sum.c.order_id == SaasOrder.id)).all():
        if order.status == "paid" and not paid:
            issue("paid_order_without_payment", order=order.id, org=order.organization_id)
        if paid and order.status != "paid":
            issue("captured_payment_on_unpaid_order", order=order.id, status=order.status)
        if paid and n and n > 1:
            issue("duplicate_capture", order=order.id, payments=n, paid_paise=paid)
        if order.status == "paid" and db.scalar(select(SaasInvoice.id).where(
                SaasInvoice.order_id == order.id, SaasInvoice.kind == "invoice")) is None:
            issue("paid_order_without_invoice", order=order.id)
        if check_provider and order.provider == "razorpay" and order.status in ("created",
                                                                               "failed"):
            try:
                remote = get_provider(get_settings(), "razorpay").fetch_order_status(
                    order.provider_order_id)
            except ProviderError as exc:
                issue("provider_unreachable", order=order.id, error=exc)
                continue
            if remote == "paid":
                issue("provider_paid_but_local_not", order=order.id, local=order.status)
    for ev in db.scalars(select(SaasWebhookEvent).where(
            SaasWebhookEvent.outcome.in_(("mismatch", "failed", "rejected")),
            SaasWebhookEvent.received_at >= datetime.now(timezone.utc) - timedelta(days=30))
    ).all():
        issue(f"webhook_{ev.outcome}", event=ev.event_id, detail=ev.detail)
    for r in db.scalars(select(SaasRefund).where(SaasRefund.status == "failed")).all():
        issue("refund_failed", refund=r.id, error=r.error or "")
    return issues

"""M7.2: SaaS subscription billing — server-side pricing with GST, idempotent
orders, signature-verified payments (checkout + webhook), exactly-once
fulfilment under replay and concurrency, invoices and credit notes, refunds
with four-eyes approval, failed-payment recovery, lifecycle (past-due →
read-only), reconciliation, AI credit packs, tenant isolation, append-only
financial records — and the guarantees that live payments and the simulator
can never be switched on in production."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.saas_billing import providers as prov
from app.saas_billing.providers import RazorpayProvider, SimulatorProvider
from app.saas_billing.service import add_months, financial_year, gst_on, split_inclusive
from tests.conftest import APP_PASSWORD, PG_HOST, PG_PORT, TEST_DB, _auth
from tests.test_m71_tenancy_saas import _platform_admin, _register, _sql
from tests.test_m7_integrity import _concurrently

PLAN = "clinic_starter"
API = "/api/v1"


def _idem() -> dict:
    return {"Idempotency-Key": uuid.uuid4().hex}


@pytest.fixture(scope="module")
def platform(client):
    _, h = _platform_admin(client)
    yield h
    # leave the shared catalogue as other suites expect it: no prices
    _sql("UPDATE plans SET price_monthly_paise = NULL, price_annual_paise = NULL")
    _sql("UPDATE ai_credit_packs SET price_paise = NULL")


@pytest.fixture(scope="module")
def priced(client, platform):
    r = client.patch(f"{API}/platform/plans/{PLAN}", headers=platform,
                     json={"price_monthly_paise": 99900, "price_annual_paise": 999000})
    assert r.status_code == 200, r.text
    r = client.put(f"{API}/platform/billing/credit-packs/ai_credits_500", headers=platform,
                   json={"name": "AI credits — 500", "credits": 500, "price_paise": 49900})
    assert r.status_code == 200, r.text
    return platform


def _tenant(client, state="Maharashtra"):
    org = _register(client, prefix="m72")
    h = _auth(org)
    assert client.patch(f"{API}/organization", headers=h, json={
        "legal_name": "Synthetic Billing Clinic", "state": state, "city": "Pune",
        "gstin": "27AAAAA0000A1Z5"}).status_code == 200
    return org, h


def _order(client, h, **body):
    body = {"kind": "subscription", "plan_code": PLAN, "billing_cycle": "monthly", **body}
    return client.post(f"{API}/saas/orders", headers={**h, **_idem()}, json=body)


def _pay(client, h, order_id, outcome="success"):
    r = client.post(f"{API}/saas/orders/{order_id}/simulate", headers=h,
                    json={"outcome": outcome})
    assert r.status_code == 200, r.text
    return r.json()


def _sim() -> SimulatorProvider:
    return SimulatorProvider(get_settings())


def _webhook(client, body: dict, event_id: str | None = None, signature: str | None = None):
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json",
               "X-Razorpay-Signature": signature or _sim().sign_webhook(raw),
               "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex[:12]}"}
    return client.post(f"{API}/saas/webhooks/simulator", content=raw, headers=headers)


def _captured(order: dict, payment_id: str, amount: int | None = None) -> dict:
    return {"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": payment_id, "order_id": order["provider_order_id"],
        "amount": order["total_paise"] if amount is None else amount,
        "currency": "INR", "method": "upi", "status": "captured"}}}}


def _app_conn(org_id: str):
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user="hms_app", password=APP_PASSWORD,
                            dbname=TEST_DB)
    cur = conn.cursor()
    cur.execute("SELECT set_config('app.current_org_id', %s, false)", (org_id,))
    return conn, cur


# --- pure money helpers ---------------------------------------------------------------
def test_money_helpers():
    assert gst_on(99900, 1800) == 17982
    assert gst_on(1, 1800) == 0 and gst_on(3, 1800) == 1          # half-up to the paisa
    taxable, tax = split_inclusive(117882, 1800)
    assert (taxable, tax) == (99900, 17982)
    assert add_months(datetime(2026, 1, 31, tzinfo=timezone.utc), 1).day == 28
    assert financial_year(datetime(2026, 3, 31).date()) == "2025-26"
    assert financial_year(datetime(2026, 4, 1).date()) == "2026-27"


# --- configuration guarantees -----------------------------------------------------------
def test_live_keys_and_production_simulator_are_refused():
    base = {"jwt_secret": "x" * 40, "database_url": "postgresql+psycopg2://a:b@h/d"}
    with pytest.raises(ValidationError, match="TEST keys"):
        Settings(**base, razorpay_key_id="rzp_live_abc123")
    with pytest.raises(ValidationError, match="simulator"):
        Settings(**base, environment="production", field_encryption_key="k" * 44,
                 payments_provider="simulator")
    Settings(**base, razorpay_key_id="rzp_test_abc123")  # test keys are fine
    prod = Settings(**base, environment="production", field_encryption_key="k" * 44,
                    payments_provider="razorpay")
    with pytest.raises(prov.ProviderError):
        SimulatorProvider(prod)


# --- catalogue & orders -------------------------------------------------------------------
def test_unpriced_items_cannot_be_bought(client, platform):
    _sql("UPDATE plans SET price_monthly_paise = NULL WHERE code = %s", (PLAN,))
    _, h = _tenant(client)
    cat = client.get(f"{API}/saas/catalog", headers=h).json()
    assert cat["mode"] == "simulator" and "no money" in cat["notice"]
    assert all(not p["purchasable"] for p in cat["plans"] if p["code"] == PLAN)
    r = _order(client, h)
    assert r.status_code == 409 and "price_not_configured" in r.json()["detail"]


def test_order_amount_is_computed_on_the_server_and_idempotent(client, priced):
    _, h = _tenant(client)
    key = {"Idempotency-Key": "k-" + uuid.uuid4().hex}
    body = {"kind": "subscription", "plan_code": PLAN, "billing_cycle": "monthly"}
    first = client.post(f"{API}/saas/orders", headers={**h, **key}, json=body)
    assert first.status_code == 201, first.text
    o = first.json()["order"]
    assert (o["amount_paise"], o["tax_paise"], o["total_paise"]) == (99900, 17982, 117882)
    assert first.json()["checkout"]["amount"] == 117882
    # a client cannot smuggle an amount in
    assert client.post(f"{API}/saas/orders", headers={**h, **_idem()},
                       json={**body, "amount_paise": 1}).status_code == 422
    again = client.post(f"{API}/saas/orders", headers={**h, **key}, json=body)
    assert again.json()["order"]["id"] == o["id"]
    other = client.post(f"{API}/saas/orders", headers={**h, **key},
                        json={**body, "billing_cycle": "annual"})
    assert other.status_code == 409
    assert client.post(f"{API}/saas/orders", headers=h, json=body).status_code == 422


def test_successful_payment_activates_plan_and_issues_gst_invoice(client, priced):
    org, h = _tenant(client)
    order = _order(client, h).json()["order"]
    paid = _pay(client, h, order["id"])
    assert paid["outcome"] == "processed" and paid["order"]["status"] == "paid"
    me = client.get(f"{API}/auth/me", headers=h).json()
    assert me["edition"]["code"] == PLAN and me["subscription_status"] == "active"
    sub = client.get(f"{API}/subscription", headers=h).json()
    end = datetime.fromisoformat(sub["current_period_end"])
    assert timedelta(days=27) < end - datetime.now(timezone.utc) < timedelta(days=32)
    # the simulated webhook replayed the same payment: still exactly one payment
    payments = client.get(f"{API}/saas/payments", headers=h).json()
    assert [p["status"] for p in payments] == ["captured"]
    (inv,) = client.get(f"{API}/saas/invoices", headers=h).json()
    assert inv["number"].startswith("BNS/") and inv["kind"] == "invoice"
    assert inv["total_paise"] == 117882 and inv["subtotal_paise"] == 99900
    assert inv["tax_breakdown"] == {"type": "intra_state", "cgst_bp": 900, "sgst_bp": 900,
                                    "cgst_paise": 8991, "sgst_paise": 8991}
    assert inv["buyer"]["gstin"] == "27AAAAA0000A1Z5"
    assert inv["lines"][0]["sac"] == "998314"
    actions = {r[0] for r in _sql(
        "SELECT action FROM audit_events WHERE organization_id = %s",
        (org["organization"]["id"],))}
    assert {"saas.order.created", "saas.order.paid"} <= actions


def test_inter_state_buyer_gets_igst(client, priced):
    _, h = _tenant(client, state="Karnataka")
    order = _order(client, h).json()["order"]
    _pay(client, h, order["id"])
    (inv,) = client.get(f"{API}/saas/invoices", headers=h).json()
    assert inv["tax_breakdown"] == {"type": "inter_state", "igst_bp": 1800,
                                    "igst_paise": 17982}


def test_forged_checkout_signature_is_rejected(client, priced):
    _, h = _tenant(client)
    order = _order(client, h).json()["order"]
    r = client.post(f"{API}/saas/orders/{order['id']}/verify", headers=h,
                    json={"provider_payment_id": "pay_FAKE123", "signature": "0" * 64})
    assert r.status_code == 400
    assert client.get(f"{API}/saas/orders", headers=h).json()[0]["status"] == "created"
    # a correct signature for ANOTHER order does not work either
    sig = _sim().sign_checkout("order_SIMother", "pay_FAKE123")
    assert client.post(f"{API}/saas/orders/{order['id']}/verify", headers=h, json={
        "provider_payment_id": "pay_FAKE123", "signature": sig}).status_code == 400
    # M8.1: the attempt is audited although the request itself is rolled back
    (n,) = _sql("SELECT count(*) FROM audit_events WHERE action = "
                "'saas.payment.signature_invalid' AND resource_id = %s", (order["id"],))[0]
    assert n == 2


def test_webhook_signature_replay_and_amount_mismatch(client, priced):
    _, h = _tenant(client)
    order = _order(client, h).json()["order"]
    body = _captured(order, "pay_SIMwh" + uuid.uuid4().hex[:8])
    assert _webhook(client, body, signature="f" * 64).status_code == 400  # forged
    bad = _captured(order, "pay_SIMbad" + uuid.uuid4().hex[:8], amount=100)
    assert _webhook(client, bad).json()["detail"] == "mismatch"
    assert client.get(f"{API}/saas/orders", headers=h).json()[0]["status"] == "created"

    first = _webhook(client, body, event_id="evt_same_" + order["id"][:8])
    assert first.json()["detail"] == "processed"
    replay = _webhook(client, body, event_id="evt_same_" + order["id"][:8])
    assert replay.json()["detail"] == "duplicate"
    # Razorpay also sends order.paid for the same payment under another event id
    order_paid = {**body, "event": "order.paid"}
    assert _webhook(client, order_paid).json()["detail"] == "duplicate"
    assert len(client.get(f"{API}/saas/payments", headers=h).json()) == 1
    assert len(client.get(f"{API}/saas/invoices", headers=h).json()) == 1
    outcomes = {r[0] for r in _sql(
        "SELECT outcome FROM saas_webhook_events WHERE payload_sha256 IS NOT NULL")}
    assert {"rejected", "mismatch", "processed"} <= outcomes


def test_concurrent_captures_fulfil_exactly_once(client, priced):
    _, h = _tenant(client)
    order = _order(client, h).json()["order"]
    body = _captured(order, "pay_SIMrace" + uuid.uuid4().hex[:8])
    results = _concurrently(*[lambda: _webhook(client, body) for _ in range(4)])
    details = sorted(r.json()["detail"] for r in results)
    assert details.count("processed") == 1, details
    assert len(client.get(f"{API}/saas/payments", headers=h).json()) == 1
    sub = client.get(f"{API}/subscription", headers=h).json()
    end = datetime.fromisoformat(sub["current_period_end"])
    assert end - datetime.now(timezone.utc) < timedelta(days=32)  # extended once


def test_failed_payment_recovery_and_read_only_tenant_can_pay(client, priced):
    org, h = _tenant(client)
    _sql("UPDATE subscriptions SET trial_ends_at = now() - interval '1 day' "
         "WHERE organization_id = %s", (org["organization"]["id"],))
    assert client.post(f"{API}/patients", headers=h, json={
        "full_name": "Read Only Test", "phone": "9000000001", "gender": "female",
        "date_of_birth": "1990-01-01"}).status_code == 402
    order = _order(client, h).json()["order"]
    failed = _pay(client, h, order["id"], outcome="failure")
    assert failed["order"]["status"] == "failed" and failed["order"]["failure_reason"]
    assert client.post(f"{API}/saas/orders/{order['id']}/retry", headers=h).status_code == 422
    retry = client.post(f"{API}/saas/orders/{order['id']}/retry", headers={**h, **_idem()})
    assert retry.status_code == 201
    new_id = retry.json()["order"]["id"]
    assert new_id != order["id"]
    assert _pay(client, h, new_id)["order"]["status"] == "paid"
    assert client.post(f"{API}/patients", headers=h, json={
        "full_name": "Writable Again", "phone": "9000000002", "gender": "female",
        "date_of_birth": "1990-01-01"}).status_code == 201
    paid_order = client.post(f"{API}/saas/orders/{new_id}/retry", headers={**h, **_idem()})
    assert paid_order.status_code == 409


def test_ai_credit_pack_purchase_adds_credits(client, priced):
    _, h = _tenant(client)
    before = client.get(f"{API}/saas/credits", headers=h).json()
    r = client.post(f"{API}/saas/orders", headers={**h, **_idem()},
                    json={"kind": "ai_credits", "pack_code": "ai_credits_500"})
    assert r.status_code == 201, r.text
    assert r.json()["order"]["total_paise"] == 49900 + gst_on(49900, 1800)
    _pay(client, h, r.json()["order"]["id"])
    after = client.get(f"{API}/saas/credits", headers=h).json()
    assert after["purchased"] == before["purchased"] + 500
    if after["plan_allowance"] is not None:
        assert after["remaining"] == before["remaining"] + 500


def test_refund_needs_vendor_approval_and_issues_credit_note(client, priced):
    org, h = _tenant(client)
    order = _order(client, h).json()["order"]
    _pay(client, h, order["id"])
    (payment,) = client.get(f"{API}/saas/payments", headers=h).json()
    too_much = client.post(f"{API}/saas/refunds", headers=h, json={
        "payment_id": payment["id"], "amount_paise": payment["amount_paise"] + 1,
        "reason": "Testing over-refund"})
    assert too_much.status_code == 422
    req = client.post(f"{API}/saas/refunds", headers=h, json={
        "payment_id": payment["id"], "amount_paise": 58941, "reason": "Half-month goodwill"})
    assert req.status_code == 201, req.text
    refund = req.json()
    # a second request may not exceed what is left
    assert client.post(f"{API}/saas/refunds", headers=h, json={
        "payment_id": payment["id"], "amount_paise": 58942,
        "reason": "Would exceed"}).status_code == 422
    # the clinic cannot approve its own refund
    assert client.post(f"{API}/platform/billing/refunds/{refund['id']}/decide", headers=h,
                       json={"approve": True}).status_code == 403
    queue = client.get(f"{API}/platform/billing/refunds", headers=priced).json()
    assert refund["id"] in {r["id"] for r in queue}
    done = client.post(f"{API}/platform/billing/refunds/{refund['id']}/decide",
                       headers=priced, json={"approve": True, "note": "approved (test)"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "processed"
    assert done.json()["provider_refund_id"].startswith("rfnd_SIM")
    again = client.post(f"{API}/platform/billing/refunds/{refund['id']}/decide",
                        headers=priced, json={"approve": False})
    assert again.status_code == 409
    notes = [i for i in client.get(f"{API}/saas/invoices", headers=h).json()
             if i["kind"] == "credit_note"]
    assert len(notes) == 1 and notes[0]["number"].startswith("BNS-CN/")
    assert notes[0]["total_paise"] == 58941
    assert notes[0]["subtotal_paise"] + notes[0]["tax_paise"] == 58941
    # four-eyes is also a database rule
    with pytest.raises(psycopg2.Error, match="four_eyes|already|cannot move"):
        _sql("UPDATE saas_refunds SET decided_by = requested_by WHERE id = %s",
             (refund["id"],))


def test_financial_records_are_append_only(client, priced):
    org, h = _tenant(client)
    order = _order(client, h).json()["order"]
    _pay(client, h, order["id"])
    for stmt in ("UPDATE saas_payments SET amount_paise = 1 WHERE order_id = %s",
                 "DELETE FROM saas_payments WHERE order_id = %s",
                 "UPDATE saas_invoices SET total_paise = 0 WHERE order_id = %s",
                 "UPDATE saas_orders SET status = 'created' WHERE id = %s",
                 "UPDATE saas_orders SET total_paise = 1 WHERE id = %s",
                 "DELETE FROM saas_orders WHERE id = %s"):
        with pytest.raises(psycopg2.Error):
            _sql(stmt, (order["id"],))


def test_tenant_isolation_and_rls(client, priced):
    org_a, ha = _tenant(client)
    _, hb = _tenant(client)
    order = _order(client, ha).json()["order"]
    _pay(client, ha, order["id"])
    assert client.get(f"{API}/saas/orders", headers=hb).json() == []
    assert client.get(f"{API}/saas/invoices", headers=hb).json() == []
    inv = client.get(f"{API}/saas/invoices", headers=ha).json()[0]
    assert client.get(f"{API}/saas/invoices/{inv['id']}", headers=hb).status_code == 404
    assert client.post(f"{API}/saas/orders/{order['id']}/simulate", headers=hb,
                       json={"outcome": "success"}).status_code == 404
    # as the app role in tenant A's context: no self-made paid orders, no edits
    conn, cur = _app_conn(org_a["organization"]["id"])
    try:
        with pytest.raises(psycopg2.Error):
            cur.execute(
                "INSERT INTO saas_orders (organization_id, kind, plan_id, billing_cycle, "
                "description, amount_paise, tax_paise, total_paise, gst_rate_bp, provider, "
                "provider_order_id, idempotency_key, status) SELECT %s, 'subscription', id, "
                "'annual', 'free', 1, 0, 1, 0, 'simulator', 'order_forged', 'forged', 'paid' "
                "FROM plans WHERE code = 'enterprise'", (org_a["organization"]["id"],))
        conn.rollback()
        cur.execute("SELECT set_config('app.current_org_id', %s, false)",
                    (org_a["organization"]["id"],))
        cur.execute("UPDATE saas_orders SET status = 'cancelled' WHERE id = %s",
                    (order["id"],))
        assert cur.rowcount == 0
        cur.execute("SELECT count(*) FROM saas_webhook_events")
        assert cur.fetchone()[0] == 0
    finally:
        conn.rollback()
        conn.close()


def test_lifecycle_past_due_then_read_only(client, priced):
    org, h = _tenant(client)
    _pay(client, h, _order(client, h).json()["order"]["id"])
    oid = org["organization"]["id"]
    _sql("UPDATE subscriptions SET current_period_end = now() - interval '1 hour' "
         "WHERE organization_id = %s", (oid,))
    r = client.post(f"{API}/platform/billing/lifecycle", headers=priced)
    assert r.status_code == 200 and r.json()["past_due"] >= 1
    sub = client.get(f"{API}/subscription", headers=h).json()
    assert sub["status"] == "past_due" and sub["effective_status"] == "past_due"
    _sql("UPDATE subscriptions SET grace_until = now() - interval '1 minute' "
         "WHERE organization_id = %s", (oid,))
    assert client.get(f"{API}/subscription", headers=h).json()["effective_status"] == \
        "read_only"
    assert client.post(f"{API}/platform/billing/lifecycle", headers=priced).json()[
        "read_only"] >= 1
    # paying again restores the clinic
    _pay(client, h, _order(client, h).json()["order"]["id"])
    assert client.get(f"{API}/subscription", headers=h).json()["status"] == "active"
    assert client.post(f"{API}/platform/billing/lifecycle", headers=h).status_code == 403


def test_reconciliation_reports_inconsistencies(client, priced):
    org, h = _tenant(client)
    oid = org["organization"]["id"]
    _sql("INSERT INTO saas_orders (organization_id, kind, plan_id, billing_cycle, description, "
         "amount_paise, tax_paise, total_paise, gst_rate_bp, provider, provider_order_id, "
         "idempotency_key, status) SELECT %s, 'subscription', id, 'monthly', 'ghost', 100, 18, "
         "118, 1800, 'simulator', %s, 'ghost', 'paid' FROM plans WHERE code = %s",
         (oid, "order_SIMghost" + uuid.uuid4().hex[:6], PLAN))
    r = client.get(f"{API}/platform/billing/reconciliation", headers=priced)
    assert r.status_code == 200
    kinds = {i["kind"] for i in r.json()["issues"]}
    assert {"paid_order_without_payment", "paid_order_without_invoice"} <= kinds
    assert client.get(f"{API}/platform/billing/reconciliation", headers=h).status_code == 403


# --- Razorpay test-mode adapter against a fake HTTP server ------------------------------
class FakeRazorpay:
    def __init__(self):
        self.calls = []
        self.refunds = []            # refunds the fake "provider" has carried out
        self.refund_mode = "ok"      # ok | lost_response | refused

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, json.loads(body) if body else None))
        if url.endswith("/orders") and method == "POST":
            data = json.loads(body)
            return 200, json.dumps({"id": "order_TEST" + uuid.uuid4().hex[:10],
                                    "amount": data["amount"], "status": "created"}).encode()
        if method == "GET" and "/refunds" in url:
            return 200, json.dumps({"items": self.refunds}).encode()
        if "/refund" in url:
            if self.refund_mode == "refused":
                return 400, b'{"error":{"description":"refund amount too high"}}'
            data = json.loads(body)
            item = {"id": "rfnd_TEST" + uuid.uuid4().hex[:10], "status": "processed",
                    "notes": data["notes"], "receipt": data.get("receipt")}
            self.refunds.append(item)
            if self.refund_mode == "lost_response":
                raise TimeoutError("read timed out")  # the provider DID refund
            return 200, json.dumps(item).encode()
        if method == "GET" and "/orders/" in url:
            return 200, json.dumps({"status": "paid"}).encode()
        return 500, b"{}"


@pytest.fixture
def razorpay():
    s = get_settings().model_copy(update={
        "razorpay_key_id": "rzp_test_SYNTHETIC", "razorpay_key_secret": "test_secret_value",
        "razorpay_webhook_secret": "test_webhook_secret"})
    fake = FakeRazorpay()
    provider = RazorpayProvider(s, http=fake)
    prov.set_provider_override(provider)
    get_settings().payments_provider = "razorpay"
    yield provider, fake
    prov.set_provider_override(None)
    get_settings().payments_provider = "simulator"


def test_razorpay_sandbox_adapter_end_to_end(client, priced, razorpay):
    provider, fake = razorpay
    _, h = _tenant(client)
    created = _order(client, h)
    assert created.status_code == 201, created.text
    order, checkout = created.json()["order"], created.json()["checkout"]
    assert checkout["mode"] == "sandbox" and checkout["key_id"] == "rzp_test_SYNTHETIC"
    method, url, headers, payload = fake.calls[0]
    assert url == "https://api.razorpay.com/v1/orders"
    assert headers["Authorization"] == "Basic " + base64.b64encode(
        b"rzp_test_SYNTHETIC:test_secret_value").decode()
    assert payload["amount"] == order["total_paise"] and payload["currency"] == "INR"
    # the simulate endpoint never works for real-provider orders
    assert client.post(f"{API}/saas/orders/{order['id']}/simulate", headers=h,
                       json={}).status_code == 404
    pid = "pay_TEST" + uuid.uuid4().hex[:10]
    sig = hmac.new(b"test_secret_value", f"{order['provider_order_id']}|{pid}".encode(),
                   hashlib.sha256).hexdigest()
    ok = client.post(f"{API}/saas/orders/{order['id']}/verify", headers=h,
                     json={"provider_payment_id": pid, "signature": sig})
    assert ok.status_code == 200 and ok.json()["outcome"] == "processed"
    # Razorpay webhook with its own secret; replay is a no-op
    raw = json.dumps(_captured(order, pid), separators=(",", ":")).encode()
    wsig = hmac.new(b"test_webhook_secret", raw, hashlib.sha256).hexdigest()
    hook = client.post(f"{API}/saas/webhooks/razorpay", content=raw, headers={
        "X-Razorpay-Signature": wsig, "X-Razorpay-Event-Id": "evt_rzp_" + pid})
    assert hook.status_code == 200 and hook.json()["detail"] == "duplicate"
    assert client.post(f"{API}/saas/webhooks/razorpay", content=raw, headers={
        "X-Razorpay-Signature": "0" * 64}).status_code == 400
    # refund goes to the Razorpay refunds API
    (payment,) = client.get(f"{API}/saas/payments", headers=h).json()
    ref = client.post(f"{API}/saas/refunds", headers=h, json={
        "payment_id": payment["id"], "amount_paise": 1000, "reason": "sandbox refund"}).json()
    done = client.post(f"{API}/platform/billing/refunds/{ref['id']}/decide", headers=priced,
                       json={"approve": True}).json()
    assert done["provider_refund_id"] == fake.refunds[0]["id"]
    assert any(c[1].endswith(f"/payments/{pid}/refund") and c[3]["amount"] == 1000
               for c in fake.calls)


def test_provider_outage_is_reported_not_swallowed(client, priced, razorpay):
    provider, fake = razorpay
    _, h = _tenant(client)

    def down(*_a):
        raise OSError("network unreachable")

    provider._http = down
    r = _order(client, h)
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]
    assert client.get(f"{API}/saas/orders", headers=h).json() == []


# --- M8.1 corrections ---------------------------------------------------------------------
def _expire(order_id: str) -> None:
    _sql("UPDATE saas_orders SET created_at = now() - interval '25 hours' WHERE id = %s",
         (order_id,))


def test_late_payment_on_expired_order_is_fulfilled(client, priced):
    """H1: money captured after the order expired must not be stranded."""
    org, h = _tenant(client)
    order = _order(client, h).json()["order"]
    _expire(order["id"])
    assert client.post(f"{API}/platform/billing/lifecycle", headers=priced).json()[
        "orders_expired"] >= 1
    assert client.get(f"{API}/saas/orders", headers=h).json()[0]["status"] == "expired"
    pid = "pay_SIMlate" + uuid.uuid4().hex[:8]
    r = _webhook(client, _captured(order, pid))
    assert r.status_code == 200 and r.json()["detail"] == "processed", r.text
    (o,) = client.get(f"{API}/saas/orders", headers=h).json()
    assert o["status"] == "paid"
    assert client.get(f"{API}/subscription", headers=h).json()["status"] == "active"
    assert [i["kind"] for i in client.get(f"{API}/saas/invoices", headers=h).json()] == [
        "invoice"]
    (n,) = _sql("SELECT count(*) FROM audit_events WHERE action = 'saas.payment.late' "
                "AND resource_id = %s", (order["id"],))[0]
    assert n == 1
    # a replay of the same capture changes nothing
    assert _webhook(client, _captured(order, pid)).json()["detail"] == "duplicate"


def test_late_checkout_on_cancelled_order_is_fulfilled(client, priced):
    _, h = _tenant(client)
    order = _order(client, h).json()["order"]
    _sql("UPDATE saas_orders SET status = 'cancelled' WHERE id = %s", (order["id"],))
    pid = "pay_SIMlate" + uuid.uuid4().hex[:8]
    r = client.post(f"{API}/saas/orders/{order['id']}/verify", headers=h, json={
        "provider_payment_id": pid,
        "signature": _sim().sign_checkout(order["provider_order_id"], pid)})
    assert r.status_code == 200 and r.json()["outcome"] == "processed", r.text
    assert r.json()["order"]["status"] == "paid"
    # paid is still final: nothing moves an order out of it
    with pytest.raises(psycopg2.Error, match="cannot move"):
        _sql("UPDATE saas_orders SET status = 'expired' WHERE id = %s", (order["id"],))


def test_reconciliation_checks_expired_orders_with_the_provider(client, priced, razorpay):
    _, h = _tenant(client)
    order = _order(client, h).json()["order"]
    _sql("UPDATE saas_orders SET status = 'expired' WHERE id = %s", (order["id"],))
    issues = client.get(f"{API}/platform/billing/reconciliation?check_provider=true",
                        headers=priced).json()["issues"]
    assert {"kind": "provider_paid_but_local_not", "order": order["id"],
            "local": "expired"} in issues


def _rzp_paid_refund(client, priced, h, fake):
    order = _order(client, h).json()["order"]
    pid = "pay_TEST" + uuid.uuid4().hex[:10]
    sig = hmac.new(b"test_secret_value", f"{order['provider_order_id']}|{pid}".encode(),
                   hashlib.sha256).hexdigest()
    assert client.post(f"{API}/saas/orders/{order['id']}/verify", headers=h, json={
        "provider_payment_id": pid, "signature": sig}).json()["outcome"] == "processed"
    (payment,) = client.get(f"{API}/saas/payments", headers=h).json()
    return client.post(f"{API}/saas/refunds", headers=h, json={
        "payment_id": payment["id"], "amount_paise": 5000, "reason": "M8.1 test"}).json()


def test_refund_with_lost_provider_response_is_resumed_not_repeated(client, priced, razorpay):
    """M2: the approval is committed as 'processing' before the provider call;
    a lost response leaves it processing, and resuming finds the provider's
    refund by reference instead of refunding a second time."""
    _, fake = razorpay
    _, h = _tenant(client)
    ref = _rzp_paid_refund(client, priced, h, fake)
    fake.refund_mode = "lost_response"
    r = client.post(f"{API}/platform/billing/refunds/{ref['id']}/decide", headers=priced,
                    json={"approve": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "processing" and "outcome unknown" in out["error"]
    assert out["decided_by"] is not None
    # the approval survived the provider failure, and nothing was credited yet
    (status,) = _sql("SELECT status FROM saas_refunds WHERE id = %s", (ref["id"],))[0]
    assert status == "processing"
    assert not [i for i in client.get(f"{API}/saas/invoices", headers=h).json()
                if i["kind"] == "credit_note"]
    issues = client.get(f"{API}/platform/billing/reconciliation", headers=priced).json()
    assert ref["id"] in {i.get("refund") for i in issues["issues"]
                         if i["kind"] == "refund_processing"}
    # deciding again is refused; resuming is the only way forward
    assert client.post(f"{API}/platform/billing/refunds/{ref['id']}/decide", headers=priced,
                       json={"approve": True}).status_code == 409
    assert client.post(f"{API}/platform/billing/refunds/{ref['id']}/resume",
                       headers=h).status_code == 403
    fake.refund_mode = "ok"
    done = client.post(f"{API}/platform/billing/refunds/{ref['id']}/resume", headers=priced)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "processed"
    assert done.json()["provider_refund_id"] == fake.refunds[0]["id"]
    posts = [c for c in fake.calls if c[0] == "POST" and c[1].endswith("/refund")]
    assert len(posts) == 1 and posts[0][3]["notes"] == {"refund": ref["id"]}
    assert len(fake.refunds) == 1
    notes = [i for i in client.get(f"{API}/saas/invoices", headers=h).json()
             if i["kind"] == "credit_note"]
    assert len(notes) == 1 and notes[0]["total_paise"] == 5000
    assert client.post(f"{API}/platform/billing/refunds/{ref['id']}/resume",
                       headers=priced).status_code == 409


def test_refund_refused_by_provider_is_failed(client, priced, razorpay):
    _, fake = razorpay
    _, h = _tenant(client)
    ref = _rzp_paid_refund(client, priced, h, fake)
    fake.refund_mode = "refused"
    out = client.post(f"{API}/platform/billing/refunds/{ref['id']}/decide", headers=priced,
                      json={"approve": True}).json()
    assert out["status"] == "failed" and "HTTP 400" in out["error"]
    # failed is final in the database too
    with pytest.raises(psycopg2.Error, match="cannot move"):
        _sql("UPDATE saas_refunds SET status = 'processing' WHERE id = %s", (ref["id"],))


def test_refund_state_machine_in_the_database(client, priced):
    _, h = _tenant(client)
    order = _order(client, h).json()["order"]
    _pay(client, h, order["id"])
    (payment,) = client.get(f"{API}/saas/payments", headers=h).json()
    ref = client.post(f"{API}/saas/refunds", headers=h, json={
        "payment_id": payment["id"], "amount_paise": 100, "reason": "state machine"}).json()
    with pytest.raises(psycopg2.Error, match="cannot move"):
        _sql("UPDATE saas_refunds SET status = 'processed' WHERE id = %s", (ref["id"],))
    _sql("UPDATE saas_refunds SET status = 'processing' WHERE id = %s", (ref["id"],))
    with pytest.raises(psycopg2.Error, match="cannot move"):
        _sql("UPDATE saas_refunds SET status = 'requested' WHERE id = %s", (ref["id"],))
    # a processing refund still counts against what can be refunded
    assert client.post(f"{API}/saas/refunds", headers=h, json={
        "payment_id": payment["id"], "amount_paise": payment["amount_paise"],
        "reason": "would exceed"}).status_code == 422


def test_append_only_tables_have_no_update_or_delete_grant(client):
    rows = _sql("SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = 'hms_app' AND table_name IN ('saas_payments', "
                "'saas_invoices', 'saas_webhook_events', 'saas_orders', 'saas_refunds')")
    granted = {(t, p) for t, p in rows}
    for t in ("saas_payments", "saas_invoices", "saas_webhook_events"):
        assert (t, "UPDATE") not in granted and (t, "DELETE") not in granted
    assert ("saas_orders", "DELETE") not in granted and ("saas_orders", "UPDATE") in granted


def test_system_scope_restores_the_callers_scope_and_survives_aborts(client):
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    from app.db import SessionLocal
    from app.saas_billing.service import system_scope

    def admin(db):
        return db.execute(text("SELECT current_setting('app.platform_admin', true)")).scalar()

    db = SessionLocal()
    try:
        db.execute(text("SELECT set_config('app.platform_admin', 'true', true)"))
        with system_scope(db, uuid.uuid4()):
            assert admin(db) == "true"
        assert admin(db) == "true"            # the console's scope is kept
        db.execute(text("SELECT set_config('app.platform_admin', '', true)"))
        with system_scope(db):
            pass
        assert admin(db) == ""                # and nothing is left open
        # an error inside the block surfaces as itself, not as "transaction aborted"
        with pytest.raises(ProgrammingError, match="no_such_table"):
            with system_scope(db):
                db.execute(text("SELECT * FROM no_such_table"))
    finally:
        db.rollback()
        db.close()

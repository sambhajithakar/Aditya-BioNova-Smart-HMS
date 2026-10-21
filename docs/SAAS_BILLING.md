# SaaS subscription billing (M7.2)

How clinics pay **Aditya BioNova** for the software: editions, AI credit
packs, GST invoices, refunds and the subscription lifecycle. This is the
vendor's billing of its customers. **Patient billing** (invoices, receipts
and the ledger under *Billing*, migration 0006) is a different module and
never shares tables, endpoints or permissions with it.

> **Status: sandbox only.** No live payment gateway is connected and no real
> money can move. Production refuses live Razorpay keys (`rzp_live_…`) at
> startup, and the local payment simulator cannot be enabled outside
> development/test. Going live needs the owner's approval, a Razorpay
> account with KYC, the seller GSTIN, and an accountant's review of the
> invoice format.

## Editions and prices

- The 7 editions (Rural Clinic, Clinic Starter, Clinic Plus + AI,
  Multi-Specialty Clinic, Hospital Core, Hospital Advanced, Enterprise) are
  rows in `plans`. Their features and limits are set in the platform console.
- **Prices are data, never code.** Monthly and annual prices are set in
  *Platform → Plans*; AI credit pack prices in *Platform → Billing*. An
  unpriced item (NULL or 0) cannot be bought; the API answers 409
  `price_not_configured`.
- 18% GST (`SAAS_GST_RATE_BP=1800`) is added on top, rounded half-up to the
  paisa.
  - **Same state as the seller:** CGST + SGST.
  - **Different state:** IGST.
  - **Place of supply** is the buyer's state from the clinic profile. If it is
    unknown, it is treated as intra-state.
  - SAC code: 998314.
- No proration in M7.2. Renewing the same plan extends from the current
  period end; changing plan starts a new period at payment time.

## Payment flow

```
clinic ──POST /saas/orders (Idempotency-Key)──▶ API computes amount + GST from the catalogue
                                                 └─▶ provider.create_order (Razorpay Orders API | simulator)
browser ──hosted checkout (Razorpay TEST)──▶ razorpay_payment_id + signature
browser ──POST /saas/orders/{id}/verify──▶ HMAC(order_id|payment_id, key_secret) checked
Razorpay ──POST /saas/webhooks/razorpay──▶ HMAC(raw body, webhook_secret) checked, deduped by event id
                     both paths ──▶ record_payment(): order row FOR UPDATE, unique payment id,
                                    amount+currency must equal the order → fulfil once → GST invoice
```

### Safeguards

- **Amounts come from the server.** The client never sends an amount
  (`extra="forbid"`), and a webhook whose amount or currency differs from
  the order is logged as `mismatch` and not fulfilled.
- **Exactly once.** A replayed or concurrent capture cannot extend a
  subscription twice. This is tested with 4 simultaneous webhooks, and with
  Razorpay's `payment.captured` and `order.paid` arriving for the same
  payment.
- **The webhook is the safety net.** If the browser never returns, the
  webhook still completes the order. Its database work runs off the event
  loop: a lock wait on the event loop would stall the whole server, a
  deadlock found by the concurrency test.
- **Read-only clinics can pay.** Billing endpoints are not gated by
  `enforce_writable`, so a clinic whose subscription lapsed can always pay
  to recover.
- **Failed-payment recovery.** `POST /saas/orders/{id}/retry` creates a
  fresh order at today's price.
- **Late payments are honoured (M8.1).** UPI and net-banking confirmations
  can arrive after an order has expired (24 h) or been cancelled.
  - If the provider captured the money, the order is fulfilled at its own
    price and audited as `saas.payment.late`.
  - The clinic's money is never kept without delivering what it paid for.
  - If the clinic already renewed through another order, the vendor sees two
    captures and can refund one.
- **Forged signatures are audited.** A failed checkout signature check is
  written to the audit trail in its own transaction (`saas.payment.signature_invalid`),
  so the record survives the request's rollback.

## Refunds (four-eyes)

1. The clinic owner requests a refund (`billing.saas.refund_request`) of up
   to what remains refundable on a captured payment. Pending and processed
   refunds are both counted.
2. A platform administrator decides (`/platform/billing/refunds/{id}/decide`):
   - The requester can never decide. This is enforced by the API and by a
     database CHECK.
   - On approval, the refund is first committed as `processing`. Only then
     is the provider's refund API called, with the refund id as its
     reference (`notes.refund` and `receipt`).
   - On success it becomes `processed` and a **credit note** (`BNS-CN/FY/n`)
     is issued. The GST split is back-calculated from the refunded amount.
   - A definite refusal by the provider (HTTP 4xx) marks it `failed`.
   - An unknown outcome (timeout, network error, 5xx) leaves it `processing`
     with the error noted. The money may or may not have moved.
     Reconciliation lists it as `refund_processing`, and
     `POST /platform/billing/refunds/{id}/resume` (the console's
     *Re-check with provider* button) asks the provider for a refund with that
     reference **before** requesting a new one, so a refund is never paid twice.
   - Database transitions (trigger): `requested → rejected | processing`,
     `processing → processed | failed`. Everything else is refused.
   - A refund returns money only. It does not take back the subscription
     period or AI credits already granted; doing so is a vendor decision made
     case by case (product decision, M8.1).
3. Invoices are never edited. `saas_payments`, `saas_invoices` and
   `saas_webhook_events` are append-only: a trigger refuses changes, and since
   M8.1 the application role also has no UPDATE or DELETE grant on them.
   Orders and refunds can only move forward.

## Lifecycle

`POST /platform/billing/lifecycle` (schedule it daily, like the comms
reminder job) applies three transitions:

| From | To |
|---|---|
| `active` with the period ended | `past_due` (grace: `SAAS_GRACE_DAYS`, default 7) |
| `past_due` after grace | `read_only` (reads keep working, writes return 402) |
| Unpaid orders older than 24 h | `expired` |

Trials that end without payment are already read-only through the
effective-status rule from M7.1.

## Reconciliation

`GET /platform/billing/reconciliation[?check_provider=true]` lists:

- paid orders without a captured payment or without an invoice
- captured payments on unpaid orders
- duplicate captures
- webhooks rejected, failed or mismatched in the last 30 days
- failed refunds, and approved refunds still `processing`
- (Razorpay only, optional) orders Razorpay reports as paid that are not paid
  locally, including created, failed and expired orders

## Configuration

| Variable | Meaning |
|---|---|
| `PAYMENTS_PROVIDER` | `simulator` (development/test only) or `razorpay`. Unset: simulator in development, razorpay elsewhere |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | **TEST** keys only (`rzp_test_…`); live keys are refused |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook HMAC secret. Point the Razorpay dashboard at `https://<api>/api/v1/saas/webhooks/razorpay` |
| `SAAS_GST_RATE_BP`, `SAAS_GRACE_DAYS` | 1800, 7 |
| `SAAS_SELLER_NAME` / `_GSTIN` / `_STATE` / `_ADDRESS` | Seller block on invoices (GSTIN unset in the demo) |
| Web `RAZORPAY_CHECKOUT=1` | Adds Razorpay's checkout frame to the CSP; off by default |

## Permissions

| Role | Permissions |
|---|---|
| owner | `billing.saas.read`, `billing.saas.pay`, `billing.saas.refund_request` |
| admin | read, pay |
| billing, auditor | read |
| platform administrator (MFA) | refund decisions, lifecycle, reconciliation, credit-pack prices |

## Test evidence

- `apps/api/tests/test_m72_saas_billing.py`: 18 tests. The Razorpay adapter
  is tested against a fake HTTP server (Basic auth, Orders API, signatures,
  refunds API, outage → 503).
- `apps/web/e2e/billing.spec.ts`: live browser flow covering decline → retry →
  paid → GST invoice → refund request → vendor approval → reconciliation.

## Not done / needs the owner

- **Not verified against Razorpay's servers.** No real Razorpay test account
  or keys were available, and `api.razorpay.com` was not reachable from the
  build environment.
- **Not built:** Razorpay Subscriptions (auto-debit/mandates) and UPI
  AutoPay. M7.2 uses one-time orders per period.
- **Not built:** proration, coupons, reseller/partner commission tracking,
  e-invoicing (IRN) and TDS handling.
- **Needs the owner:** an accountant's review of the invoice series format
  (`BNS/2026-27/000001`) and the GST treatment.

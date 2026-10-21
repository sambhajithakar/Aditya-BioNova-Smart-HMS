# Domain-module audit — Aditya BioNova Smart HMS (backend)

Scope: `apps/api/app/routers/{patients,appointments,opd_queue,encounters,prescriptions,billing,pharmacy,lab,ipd,inventory,expenses,reports}.py`, `apps/api/app/services/*.py`, `models.py`, `schemas.py`, migrations 0005–0008, domain tests, and the docs TASKS/REQUIREMENTS/API_DOCUMENTATION/DATABASE_SCHEMA/CHANGELOG.
Method: static reading only. I did not run pytest and did not change any files. Every finding below was checked against the code at the line cited. Some findings depend on runtime behaviour; those are marked "(inferred)".

Note that applies to many findings: PostgreSQL **foreign-key checks bypass row-level security**. A table that has an FK to `branches`, `encounters` or `appointments` will accept another tenant's UUID unless the application validates it first. Several write paths skip that validation (listed per module).

---

## 0. Cross-cutting

### Verified working
- Every request runs in one transaction: `db.py:34-44` (commit when the request finishes, rollback on exception). The RLS GUCs are transaction-local: `db.py:60-71`.
- Money is stored as `Numeric(12,2)` everywhere: `models.py:833-846, 899-903, 937, 993, 1041`. The services compute with `Decimal`: `services/billing.py:276-286`.

### Defects
- **Medium — `idempotent_store` rolls back the whole request on a key race.** `services/clinical.py:195-199` calls `db.rollback()` on IntegrityError. That throws away the record the current request just created (patient, payment, admission, dispense, …) and its audit event, yet the router still returns 201 with that phantom body (for example `patients.py:132-141`, `billing.py:415-424`). Two requests sent at the same moment with the same key can therefore return two different IDs, and only one of them exists. `idempotent_replay` (`clinical.py:138-169`) does no locking.
- **Medium — trigger exceptions surface as 500.** The only handler is the generic one at `main.py:73-79`. Plpgsql `RAISE` from the stock, lab and invoice triggers is never mapped to 409, except in `inventory.py:251-260`. Example: a pharmacy write-off larger than on-hand (`services/pharmacy.py:180-210`, with no app-side check) reaches `apply_stock_movement` and returns 500.
- **Low — API money is `float`.** Input and output are floats: `schemas.py:635-636, 664, 695, 729, 784, 1351`, and reports at `1411-1418`. There is no limit on decimal places. A payment or refund of `0.004` passes `gt=0`, rounds to `0.00`, then trips `ck_pay_amount_positive` / `ck_ref_amount_positive` (`0006:439,472`) and returns an uncaught 500 (`billing.py:368-386`, `545-564`).
- **Medium — UTC day boundaries for an Indian (IST) product.** OPD `service_date` uses the UTC date (`opd_queue.py:44-45`). Reports use UTC midnight-to-midnight (`reports.py:38-43`). Pharmacy uses `date.today()` (`services/pharmacy.py:97`, `pharmacy.py:215`). Expenses use `date.today()` (`expenses.py:208`). As a result, OPD tokens issued between 00:00 and 05:30 IST land on the previous service day, and daily reports are shifted by 5.5 hours. (Doc acknowledges as follow-up: DATABASE_SCHEMA.md "Known schema follow-ups".)
- **Medium — cross-tenant FK references accepted.** The following IDs reach an INSERT without a tenant check:
  - `pharmacy.py:134-145` (`branch_id` on receive)
  - `pharmacy.py:409` (`branch_id` on dispense)
  - `lab.py:170-178` (`branch_id`, `encounter_id`)
  - `ipd.py:160-166` (ward `branch_id`)
  - `inventory.py:100-108` (`branch_id`)
  - `opd_queue.py:117` (`appointment_id`)
  - `encounters.py:124-126` (`appointment_id`, `provider_user_id`)
  - `prescriptions.py:172-175` (`encounter_id`, which is not checked for patient match either)
  - `billing.py:135-143`, where the encounter is checked for tenant but not for `patient_id` match
  - `appointments.py:97-101` and `ipd.py:393` (`provider_user_id` / `attending_user_id` not checked to be org members)
- **Low — not every list endpoint is paginated.** TASKS M2 says all list endpoints are paginated, but `/ipd/wards`, `/ipd/beds`, `/lab/tests`, `/prescriptions/drugs`, `/billing/invoices/{id}/ledger` and `/pharmacy/stock/alerts` return unpaginated lists (`ipd.py:184,247`, `lab.py:130`, `prescriptions.py:144`, `billing.py:614`, `pharmacy.py:210`).

---

## 1. Patients (`routers/patients.py`, `services/clinical.py`)

### Verified working
- UHID is allocated under a per-org advisory xact lock (`clinical.py:55-67`), backed by `uq_patient_org_uhid` (`models.py:311`).
- Duplicate detection is tenant-scoped and covers phone and name+DOB (`clinical.py:89-129`). The audited override is at `patients.py:71-93, 117-131`.
- Merge is non-destructive and refuses a self-merge or a double merge (`patients.py:260-286`).

### Defects
- **High (clinical safety) — merge does not carry over clinical data.** `patients.py:285-286` only flips status and `merged_into_id`. Allergies, encounters, prescriptions, invoices and admissions stay on the retired record. The allergy gate (`services/billing.py:404`) reads only the survivor's `allergies` text, so an allergy recorded on the merged-away record is silently lost for future prescribing.
- **Medium — DOB is typed `datetime` but stored as `Date`.** `schemas.py:188, 228, 284` use `datetime`; the column is `Date` (`models.py:286`; `0005:74`). The API echoes DOB as a datetime. (Inferred) a tz-aware value such as `…T00:00+05:30` will be cast to the previous day under the UTC session timezone.
- **Low — the UHID retry loop cannot help.** `create_patient_uhid_retry` (`clinical.py:70-86`) recomputes the same `max+1` every iteration. `max(uhid)` is lexicographic and breaks after P9999999.
- **Low — merges are not locked.** Concurrent A→B and B→A can both succeed (`patients.py:263-286`, no `FOR UPDATE`).
- **Low — search does a full scan.** It uses leading-wildcard `LIKE` on lower(name/uhid/phone) (`patients.py:169-174`) with no trigram index.

---

## 2. Appointments (`routers/appointments.py`)

### Verified working
- `ends>starts` is checked (`:83-84`). Foreign patient or branch returns 404 (`:34-46`). Overlap returns 409 (`:49-73`). Completed and cancelled appointments are frozen (`:202-205`).

### Defects
- **Medium — provider double-booking race.** The overlap check is a plain count (`:60-69`) with no lock and no exclusion constraint, so two concurrent bookings both succeed.
- **Low — status transitions are unrestricted.** PATCH accepts any status (`:207-224`): `no_show → scheduled`, `scheduled → completed` and so on. `no_show` is not frozen.
- **Low — naive datetimes are accepted.** `schemas.py:316-317` does not require timezone-aware values.

### Missing
- Doctor schedules and slots, appointment reminders (SMS/WhatsApp/e-mail), online booking.

---

## 3. OPD queue (`routers/opd_queue.py`)

### Verified working
- Tokens are allocated under a per-(org, day) advisory lock (`:102-112`), backed by a unique constraint. The state machine is at `:34-41, 197-202`.

### Defects
- **Medium — duplicate active entries for one patient.** The "already in today's active queue" check (`:87-100`) runs *before* the advisory lock, and no partial unique index exists. Two concurrent joins create two active entries for the same patient.
- **Low — some transitions have no endpoint.** There is no cancel route and no `called → waiting` route, although the state machine allows both (`:34-41`; routes are only call/start/complete/skip).
- **Low — token and priority design.** One token series is shared across all branches of the org (`:105-111`). The board orders by token only and ignores `priority=urgent` (`:185`).

---

## 4. Encounters (`routers/encounters.py`, migration 0006)

### Verified working
- One open encounter per patient: partial unique index `uq_enc_one_open` (`0006:164-167`), mapped to 409 (`encounters.py:133-139`).
- Header is frozen after completion by `trg_enc_completed_immutable` (`0006:646-661`). The queue entry is linked and completed (`:141-144, 360-370`).

### Defects
- **Low — child rows are not frozen in the database.** The trigger covers only UPDATE on `encounters`. Vitals and diagnoses can still be INSERTed into a completed encounter via SQL (protected in the app only, `_require_open`), and encounter DELETE is not blocked.

---

## 5. Prescriptions (`routers/prescriptions.py`, `services/billing.py`, migration 0006)

### Verified working
- Items must reference an active `drug_catalog` row (`billing.py:449-467`).
- The allergy gate blocks signing unless acknowledged, and the acknowledgement is persisted and audited (`prescriptions.py:290-320`).
- The amendment chain is implemented: v1 is flipped to superseded and v(N+1) is signed (`:327-403`).
- `trg_rx_immutable` allows only signed→superseded, with identical columns (`0006:585-616`).

### Defects
- **High — signed prescriptions can gain new items.** `trg_rxitem_immutable` is created `BEFORE UPDATE OR DELETE` only (`0006:640-643`), even though its function has an INSERT branch (`:623-625`). New rows can therefore be INSERTed into a **signed** prescription, which breaks the "signed Rx immutable" claim. Compare `trg_invitem_frozen`, which correctly includes INSERT (`0006:708-711`). The raw-SQL test (`test_m3_clinical_billing.py:288-320`) never tries an INSERT.
- **Medium — documented draft editing does not exist.** API_DOCUMENTATION says "draft → 409 (edit it directly)" and the code says the same at `prescriptions.py:344-347`, but there is no PATCH or DELETE endpoint for drafts. A wrong draft can never be fixed or discarded.
- **Medium — the allergy matcher misses brand names and common synonyms.** `services/billing.py:373-381, 410-418` matches only generic name, class and allergy_terms. `brand_hint` is ignored. With the seed data in `0006` (e.g. `Augmentin`, `Septran`, `Crocin`), a recorded allergy "Augmentin" does **not** block Amoxicillin-Clavulanate.
- **Low — no locking on amend.** Concurrent amends of the same signed Rx both build v(N+1), and the second hits the trigger as a 500.
- **Low — Rx item `quantity` is a free-text string** (`models.py:785`), so a numeric dispensing cap is impossible (see Pharmacy).

---

## 6. Billing (`routers/billing.py`, `services/billing.py`)

### Verified working
- Totals are computed on the server with Decimal (`billing.py:145-160`).
- Invoice numbers are allocated under an advisory lock (`services/billing.py:250-273`) with a unique constraint (`0006:372`).
- Freeze-on-issue covers financial columns (`0006:663-685`) and items, including INSERT (`0006:687-711`).
- The ledger is append-only (trigger plus REVOKE, `0006:714-727`). Unique partial indexes prevent double posting per charge/payment/refund/void (`0006:513-530`).
- The refund bound is checked against the per-payment total (`billing.py:545-552`). The receipt runs a ledger consistency check (`:694`).

### Defects
- **High — overpayment via sandbox payments.** `record_payment` checks the amount against the ledger `balance_due` (`:368-374`), and pending sandbox payments are not reserved. Two sandbox payments for the full balance can both be created, and `sandbox_confirm` (`:459-485`) settles both without re-checking the balance or the invoice status. Result: `amount_paid` = 2× total. The DB does not prevent it either, because there is no `amount_paid <= total` constraint (`0006:376-379`).
- **High — no row locks on payments or refunds.** `record_payment`, `_settle_payment` and `refund_payment` (`:362-390, 439, 540-567`) read-modify-write `inv.amount_paid` in Python with no `SELECT … FOR UPDATE`. Concurrent payments can both pass the balance check, and concurrent refunds can both pass the `max_refund` check (overpay or over-refund). Under a lost update, `amount_paid` diverges from the ledger, and `assert_ledger_consistent` then makes `/receipt` return 500 for that invoice permanently (`services/billing.py:352-369`).
- **Medium — a pending sandbox payment can be confirmed on a voided invoice.** `void_invoice` checks only `amount_paid > 0` (`:262-265`), and confirm does not check `inv.status`.
- **Medium (GST) — tax is charged on the pre-discount value.** Tax is computed per line on `qty × price` (`:149-155`), and the discount is then subtracted from the subtotal only (`:157-160`). Under GST the tax should be on the discounted value.
- **Medium (GST) — invoice numbering does not meet GST invoice rules.** Numbers are taken at **draft** creation (`:162`), so voided or abandoned drafts leave gaps in the series. The series is per tenant, not per financial year or branch. `max()` is lexicographic and breaks after INV-999999, giving a 503 (`services/billing.py:256-273`).
- **Low — invoice trigger leaves gaps.** `forbid_issued_invoice_change` (`0006:663-680`) does not freeze `status` or `amount_paid`. With raw SQL an issued invoice can be flipped back to `draft` and its financials then edited.
- **Low — confirm/fail are not real callbacks.** They are staff endpoints guarded by `billing.payment` (`:459, 488`) with no signature verification, so any cashier can mark a sandbox payment as succeeded. This is acceptable for a spike, but it is not a callback.

### Missing commercially
- **GST:** GSTIN on org/branch, HSN/SAC codes, CGST/SGST/IGST split, place of supply, GSTR exports. A single `tax_rate` per line is all that exists.
- No service/tariff master or price list; every invoice line is free text (`schemas.py:631-643`).
- No auto-billing from pharmacy dispenses, lab orders or IPD stays.
- No insurance/TPA/pre-auth/claims. `insurance` exists only as a payment method (`schemas.py:407`).
- No deposits/advances, credit notes or separate receipt numbers.

---

## 7. Pharmacy (`routers/pharmacy.py`, `services/pharmacy.py`, migration 0007)

### Verified working
- FEFO is correct: ordered by expiry, then received_at, then id, `FOR UPDATE`, splits across batches, raises 409 on shortfall (`services/pharmacy.py:85-130`).
- The append-only movement ledger has a trigger-maintained on-hand that blocks negative stock and dispensing of expired stock (`0007:454-519`).
- Recalled batches are frozen (`0007:539-557`). Dispenses are immutable (`0007:520-537`).
- Rx dispensing requires a signed Rx and only drugs on that Rx (`pharmacy.py:354-405`).
- Duplicate drug lines are rejected (`schemas.py:841-847`).

### Defects
- **High — no dispensing quantity cap and no repeat-dispense guard.** A signed Rx can be dispensed any number of times and in any quantity (`pharmacy.py:394-424`): nothing compares against Rx quantity or previous dispenses. Amending to v2 permits a full re-dispense.
- **High (commercial) — dispenses are recorded at cost price and never billed.** `unit_price = batch.unit_cost` (`services/pharmacy.py:158`). There is no MRP or selling price, no GST, and no invoice link.
- **Medium — a write-off larger than on-hand returns 500, not 409** (`services/pharmacy.py:197-208`; the trigger raises at `0007:486-490`).
- **Medium — branch inference can pick the wrong branch.** `_infer_branch` (`pharmacy.py:457-478`) picks the branch of the earliest-expiry `active` batch, even if that batch is expired or nearly empty, and considers only the first drug. A 409 can result while another branch holds stock.
- **Low — stock alerts are not branch-aware.** `/stock/alerts` has no branch filter, a hard-coded low-stock threshold of `< 10` (`:248`) with no per-drug reorder level, and no pagination.

### Doc claims false or stale
- "**recalled batches are frozen**": there is no API to recall a batch. The test sets the status with raw SQL (`test_m5_pharmacy_lab.py:349-351`).
- "**dispense documents are corrections-by-return**": the `return` movement type exists in the CHECK constraint (`0007:234`), but there is no return or reversal endpoint.
- "**reason-coded adjustments**": the reason is free text (`schemas.py:822-826`).

### Missing
- Supplier master, purchase orders, GRN, purchase returns, MRP/selling price, schedule H/H1/X register, narcotics register, inter-branch stock transfer, patient returns.

---

## 8. Laboratory (`routers/lab.py`, migration 0007)

### Verified working
- Four-eyes is enforced in the app: the verifier cannot be the importer (`lab.py:459-466`).
- The state machine is DB-enforced with column freezing (`0007:587-653`).
- Amendment creates a new version, using a deferrable FK and a partial unique index on live results (`lab.py:557-626`; `0007:361-401`).
- Re-import of a live result returns 409 (`lab.py:378-392`).

### Defects
- **Critical — ordered tests are never stored.** `post_lab_order` validates `test_ids` (`lab.py:168`) and then discards them. No order-item table exists (`models.py:1310-1372`); the IDs survive only in audit metadata (`:190`). Consequences:
  - any catalog test can be resulted against any order (`:368`);
  - an order is marked `released` when every *imported* result is released, even if ordered tests were never resulted (`:541-553`);
  - the worklist cannot show what was ordered;
  - nothing can be billed per test.
- **High — only one specimen per order.** Collection requires `status == "ordered"` (`:282-287`) and then sets `specimen_collected`. A second specimen (e.g. urine for URINE plus blood for CBC in the same order) returns 409. If the only specimen is rejected, the order stays `specimen_collected` (`:334-335`) and cannot get a new specimen; the only way out is to cancel.
- **Medium — empty results can be imported and released.** `value_text=""` together with `value_numeric=None` is accepted (`schemas.py:1026-1030`). Linking a specimen is optional (`:1041`).
- **Medium — barcode allocation has no lock.** `_next_barcode` uses `max()+1` (`lab.py:93-111`), so concurrent collections hit `uq_specimen_org_barcode` and return 500.
- **Medium — the abnormal flag is user-supplied.** There is no auto-flagging against the reference range. Ranges are free-text strings that are not age- or sex-specific (`0007:66-89`, e.g. CBC "age/sex specific"). Panels such as CBC, LFT and LIPID have a single value with no analyte-level parameters. There is no critical-value alerting.
- **Low — the order trigger does not fully freeze closed orders.** For released or cancelled orders, `forbid_closed_laborder` (`0007:658-683`) still allows changes to `clinical_notes`, `encounter_id` and `cancel_reason`, so the claim that cancelled orders are "frozen" holds only for status and header.
- **Low — four-eyes is not enforced in the database.** The trigger (`0007:604-613`) never compares `verified_by` with `imported_by`.

### Missing
- Lab report print or PDF with letterhead and sign-off, tenant-specific test master and pricing, analyte parameters, delta checks, sample tracking or TAT, analyzer interface (planned M8).

---

## 9. IPD (`routers/ipd.py`, migration 0008)

### Verified working
- Partial unique indexes ensure one active admission per bed and per patient (`0008:202-207`), and the race is mapped to 409 (`ipd.py:396-405`).
- The transfer ledger is append-only. The admission trigger enforces bed/ward consistency and freezes discharged admissions (`0008:443-530`).
- Nursing inserts are blocked after discharge by trigger (`0008:536-560`). Admission idempotency is at `ipd.py:318-327, 424-432`.

### Defects
- **High (clinical safety), and the doc claim is false — SpO2 below 85 cannot be recorded.** `NursingRecordIn._spo2` rejects any `spo2 < 85` outright (`schemas.py:1218-1226`), so a genuine hypoxic reading can never enter the structured vitals. CHANGELOG/TASKS say "SpO₂ < 85 demands a documented escalation note", but no note makes it acceptable. The test only asserts 84 → 422 (`test_m6_ipd_operations.py:448`).
- **Medium — N+1 queries on the ward list.** `list_wards` → `_ward_out` runs a bed query **and** a full active-admissions scan per ward (`ipd.py:69-93, 196`).
- **Low — transfer gaps.** A transfer that loses a race on `uq_admission_bed_occupied` is not caught and returns 500 (`ipd.py:529-531`). Closed target wards are accepted (`:515-517` checks existence only).
- **Low — discharge checks nothing financial or clinical.** It has no check for outstanding bills, pending lab results or the medication list. The discharge summary is a single free-text field (`schemas.py:1182-1184`).

### Missing
- IPD billing with bed/day tariffs, packages, deposits and interim bills (explicitly deferred).
- Discharge summary print, MAR/medication orders, OT scheduling, IPD doctor rounds/orders, diet and housekeeping.

---

## 10. Inventory (`routers/inventory.py`)

### Verified working
- Trigger-maintained on-hand with no negative stock, frozen when retired (`0008:563-612`). Oversell is mapped to 409 (`inventory.py:251-260`). Idempotency is at `:221-233, 279-287`.

### Defects
- **Low — `low_only` filters after pagination.** `low_only=true` is applied after LIMIT/OFFSET (`:150-157`), so `total` is wrong and pages come back short.
- **Low — case-sensitive duplicate check.** The duplicate-name check is case-sensitive (`:88-99`), and `branch_id` is not validated (see §0).

### Missing
- Supplier/PO/GRN, issue to department or patient, inter-branch transfer, batch/expiry for consumables.

---

## 11. Expenses (`routers/expenses.py`)

### Verified working
- The branch is validated for tenancy (`:69-77`). DB trigger: only recorded→void is allowed, and DELETE is blocked (`0008:615-650`).

### Defects
- **Low — void needs no separate approval.** The same `expense.manage` permission records and voids (`:158-163`). The summary sums with `float` (`:227`).

---

## 12. Reports (`routers/reports.py`)

### Defects
- **High — refunds are double-counted in revenue.** Revenue counts only payments with `status == "succeeded"` (`reports.py:100-107`), but a refund changes the payment status to `refunded` / `partially_refunded` (`billing.py:581-584`), and refunds are then subtracted again (`:108-115, 170`). A fully refunded ₹1000 payment produces net −1000 instead of 0. The test only asserts `revenue >= 250` and never refunds (`test_m6_ipd_operations.py:722-745`).
- **Medium — UTC day windows.** Revenue is bucketed by `Payment.created_at` (not settlement time), using UTC day windows (`:38-43`).
- **Low — finance totals use float arithmetic** (`:131, 167-170`).

### Missing
- OPD footfall, doctor-wise revenue, pharmacy sales and margin, lab volume and TAT, GST reports, day-book/cash closing, AR ageing.

---

## 13. Documentation claims vs code

| Claim | Where | Reality |
|---|---|---|
| Signed Rx items immutable ("items follow their prescription's status") | DATABASE_SCHEMA M3, CHANGELOG M3 | INSERT not covered (`0006:640-643`) |
| SpO₂ < 85 accepted with escalation note | CHANGELOG M6, TASKS M6 | Always rejected (`schemas.py:1218-1226`) |
| Recalled batches frozen / corrections-by-return | CHANGELOG/TASKS M5 | No recall or return API; tested only via raw SQL |
| "Draft → edit it directly" | API_DOCUMENTATION M3 | No draft edit or delete endpoint |
| Lab orders carry ordered tests | Implied by "orders → specimens → results" | Test list not persisted |
| `{items,total,limit,offset}` on all list endpoints | API_DOCUMENTATION, TASKS M2 | Six endpoints return bare lists |
| API docs: "42 paths at M3"; idempotency only on patients/queue/payments | API_DOCUMENTATION | All M5/M6 endpoints (pharmacy, lab, ipd, inventory, expenses, reports) are undocumented. Idempotency also exists on pharmacy receive/dispense, admissions, inventory movements and expenses |
| DATABASE_SCHEMA "(M2)" | DATABASE_SCHEMA.md | M5/M6 tables, triggers and RLS are not documented; the migrations list stops at 0005 |
| R3.3 pharmacy/lab ⬜ | REQUIREMENTS.md | Stale: implemented in M5 |
| "reason-coded adjustments" | CHANGELOG M5 | Reason is free text |
| "test_reports_summary_math" | tests | Asserts only `>=`, never exact figures or refunds |

---

## 14. Missing commercial features (none of these exist in the API; grep confirmed)

GST invoicing (GSTIN/HSN/SAC/CGST-SGST-IGST); service tariff or price master; IPD billing, packages and deposits; insurance/TPA/cashless pre-auth and claims; discharge summary print; lab report PDF/print; structured reference ranges; pharmacy suppliers, POs, GRN, purchase and sales returns, MRP; multi-branch stock transfer; OT scheduling; ABHA/ABDM (ABHA ID, consent, HIP/HIU); doctor schedules and slots; notifications (SMS, WhatsApp, e-mail); patient portal; structured allergy list. Only `/print/rx/[id]` exists on the web side (Rx and receipt).

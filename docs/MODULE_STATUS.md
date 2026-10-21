# Module status report: Aditya BioNova Smart HMS

**Date:** 2026-10-21
**Branch:** `claude/pensive-albattani-n0zcba`, draft PR #1, **not merged**

**The product is not production-ready.** The open release gates are listed in
[RELEASE_READINESS.md](RELEASE_READINESS.md).

## How to read this report

| Status | Meaning |
|---|---|
| **COMPLETE** | Built for the current scope. Covered by automated tests (API on real PostgreSQL with RLS, web E2E in a real browser, Flutter widget tests). Exercised with **synthetic data only**. This does *not* mean clinically validated or production-ready |
| **PARTIAL** | Works, with known gaps (listed) |
| **MISSING** | Not built. An edition switch may exist so it can be sold later |
| **NOT TESTED** | Built, but never run where it matters: on a real phone, real Bluetooth hardware, a real vendor or a real printer |

The **Real / Simulated** column says whether the feature does the real thing
inside this software, or stands in for an outside service:

| Value | Meaning |
|---|---|
| **Real** | Real logic and real database writes |
| **Simulated** | An in-process stand-in. No outside service is contacted |
| **Mock** | Messages are recorded in an outbox and never delivered |

### Evidence behind the statuses

| Check | Result |
|---|---|
| API tests (pytest, real PostgreSQL with RLS on) | 353 passed, 94.41% coverage |
| Web unit tests | 159 |
| Web E2E (Playwright, live API and database, nothing mocked) | 29/29 |
| Flutter tests | 237 |
| CI | green on every job |
| Demo walkthrough | 24 web steps driven through the real UI on the seeded demo, all passing (see [DEMO.md](DEMO.md)) |

## 1. Platform, security and administration

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Multi-tenant isolation (PostgreSQL RLS, non-owner app role) | COMPLETE | Real | RLS on every tenant table (70 of 71). `auth_sessions` is exempt by design, because sign-in happens before a tenant is chosen. The app role owns no tables, so RLS always applies to it. Cross-tenant tests run in CI |
| Sign-in, refresh, logout; httpOnly cookie session (web) | COMPLETE | Real | |
| TOTP two-step sign-in, recovery codes, per-role MFA policy | COMPLETE | Real | |
| Password reset, invitations | COMPLETE | Real, with **mock e-mail** | The reset or invite link is written to the mock outbox. No e-mail is sent |
| Rate limiting, lockout, security headers, CSP | COMPLETE | Real | |
| Roles and permissions (owner, admin, doctor, nurse, receptionist, pharmacist, lab technician, billing, auditor) | COMPLETE | Real | Custom roles (Enterprise) are **MISSING** |
| Audit log, including PHI reads | COMPLETE | Real | Viewing only. Audit export (an edition switch) is **MISSING** |
| Organization profile, branches, members | COMPLETE | Real | |
| 7 editions, entitlements, limits | COMPLETE | Real | **Prices are not set.** That is the owner's decision |
| Platform console (tenants, plans, support, SaaS billing) | COMPLETE | Real | |
| Support tickets | COMPLETE | Real | |
| Smart Setup wizard | COMPLETE | Real | |
| Backup and restore | COMPLETE | Real | The drill runs in CI (fingerprints identical). Off-site storage is **not set up** |
| DPDP Act compliance (consent, data-principal requests, retention) | PARTIAL | Real | "Data & exit" export exists. A legal review is **NOT TESTED** |

## 2. Clinic (OPD) workflows

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Patient registration, UHID, duplicate check and merge review | COMPLETE | Real | Web and Android. Android also works offline |
| Appointments, slots | COMPLETE | Real | Double-booking is guarded. **Reminders are MOCK** (outbox) |
| OPD queue and tokens; QR check-in | COMPLETE | Real | No live push: the screen refreshes on demand |
| Consultation: vitals, diagnosis, notes | COMPLETE | Real | Free-text diagnosis with an optional code field. No ICD-10 master yet (PARTIAL for coding) |
| e-Prescription: explicit dose, sign, print (prescriber registration number) | COMPLETE | Real | Printing has been verified only as Chromium print output. Paper printers are **NOT TESTED** |
| OPD billing: invoice, issue, pay, void, refund, receipt | COMPLETE | Real | Patient-side GST e-invoicing (IRN) is **MISSING** |
| Online patient payments (UPI or card gateway) | PARTIAL | **Simulated** | Cash, UPI and card are *recorded* as payments. No payment gateway for patients |
| Follow-ups | COMPLETE | Real | Messages are MOCK |
| Certificates and referral letters | MISSING | — | |
| Patient portal or app | MISSING | — | |

## 3. Pharmacy and inventory

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Stock batches, expiry, alerts, adjustments, movements | COMPLETE | Real | GS1 barcode scan on Android. The scan on a real camera is **NOT TESTED** |
| Dispense against a signed prescription; OTC dispense | COMPLETE | Real | Verified in the demo walkthrough (stock 200 → 170) |
| Billing a dispense (pharmacy sale invoice, H10) | MISSING | — | Dispensing does not create an invoice yet |
| General inventory, expenses | COMPLETE | Real | |
| Purchase orders, suppliers master | MISSING | — | |

## 4. Laboratory

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Orders, specimens, results, verify, release, amend | COMPLETE | Real | |
| Lab report print | PARTIAL | Real | Basic. Not reviewed by a pathologist |
| Analyser interfaces (HL7/ASTM) | MISSING | — | |

## 5. Hospital (IPD)

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Wards, beds, admission, transfer, discharge | COMPLETE | Real | |
| Nursing records (append-only) | COMPLETE | Real | Medication administration record (MAR), intake/output and care plans are **MISSING** |
| IPD billing (bed-days, deposits, running bill) | MISSING | — | |
| Emergency / triage, OT scheduling, insurance / TPA | MISSING | — | Edition switches exist; nothing is built |
| ABDM / ABHA, HL7 FHIR | MISSING | — | |

## 6. Android app (offline-first)

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Sign-in with PIN lock; encrypted offline store (Keystore) | COMPLETE | Real | Widget tests only. **NOT TESTED on a phone** |
| Offline queue, registration, consultation drafts, Rx drafts, billing; sync with conflicts | COMPLETE | Real | Sync runs only while the app is open (no background sync) |
| Rural Clinic mode (large touch targets, 4-step navigation, quick picks) | COMPLETE | Real | |
| English / मराठी / हिंदी | COMPLETE | Real | Native-speaker review is open. The Android PDF has no Devanagari font yet |
| Thermal / A4 PDF and share | PARTIAL | Real | Draft PDF works. Printing to a real printer is **NOT TESTED** |
| Installable APK | PARTIAL | Real | Builds in CI and here, debug-signed. **Installation on a phone is NOT TESTED.** Play Store release needs the owner's signing key |
| LAN demo build (server address on the phone, DEMO strip) | COMPLETE | Real | Opt-in build only. Ordinary builds are HTTPS-only |

## 7. Bluetooth medical devices (M8.2)

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Standard-profile parsers (BP 0x2A35, SpO2 0x2A5E / 0x2A5F) | COMPLETE | Real | 24 shared synthetic vectors, checked in Python and Dart |
| Device register (allow-list, hashed address, retire) | COMPLETE | Real | Web and Android |
| Capture from a consultation, offline outbox | COMPLETE | **Simulated devices** | The in-app simulator generates the readings |
| Clinician review: accept with patient confirmation, reject with reason; never auto-accepted | COMPLETE | Real | Web and Android |
| Real Bluetooth transport (`flutter_reactive_ble`) | NOT TESTED | Real code, **no hardware** | No device model is supported. Nothing purchased (see [HARDWARE_PURCHASE_RECOMMENDATION.md](HARDWARE_PURCHASE_RECOMMENDATION.md)) |
| Glucometer, thermometer, ECG, weighing scale | MISSING | — | |

## 8. Communications

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Templates, previews, reminder runs, outbox | COMPLETE | **Mock** | E-mail, SMS and WhatsApp are written to the outbox. **Nothing is delivered** |
| Real e-mail / SMS (DLT) / WhatsApp vendors | MISSING | — | Needs vendor choice and DLT registration |

## 9. SaaS subscription billing (vendor side)

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| Plans, trial, checkout, GST invoice, refunds, late payments, reconciliation | COMPLETE | **Simulated** | The in-process payment simulator moves no money. Live payments are refused at startup |
| Razorpay sandbox adapter | NOT TESTED | Real code | Needs Razorpay test keys |
| Live payments | MISSING (by decision) | — | Needs your explicit approval |
| AI credit packs (purchased credits never expire) | COMPLETE | Simulated payment | |
| Auto-debit, proration, coupons, e-invoicing (IRN) | MISSING | — | |

## 10. AI features (assistive only; never diagnoses or treats)

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| AI gateway: entitlements, credit metering, PHI redaction, audit | COMPLETE | Real | The redactor does not remove personal names |
| Business Copilot (questions over the clinic's own figures) | PARTIAL | **Mock model** | Real queries over the data. Answers come from templates; no language model is connected |
| Clinical voice Scribe | PARTIAL | **Mock** | No speech recognition model. Works from typed text. Every draft needs a clinician |
| Demand forecasts | PARTIAL | Real (statistical) | Simple statistics, not machine learning |
| Knowledge assistant | PARTIAL | Real (BM25) | Keyword retrieval with quotes; no embeddings |
| Operations agents | PARTIAL | Real rules | Proposals only; a human approves |
| Document extraction (OCR) | MISSING | — | |
| Hosted language model (Indian data residency) | MISSING | — | Owner decision |

## 11. Operations and delivery

| Module | Status | Real / Simulated | Notes |
|---|---|---|---|
| CI (API, web, E2E, mobile, APK, Docker, audits, secret scan, backup drill) | COMPLETE | Real | |
| Docker images and compose stack | COMPLETE | Real | Loopback-only by default |
| Synthetic-data demo kit (compose overlay, seed, `demo-up.sh`) | COMPLETE | Real | Runs in CI |
| `demo-up.ps1` (Windows) | NOT TESTED | Real | No PowerShell was available to run it |
| Production hosting, TLS, monitoring, off-site backups | MISSING | — | Not approved |
| Load test at target scale; penetration test | NOT TESTED | — | |

## Observations from the demo walkthrough (for review)

- **Pharmacist menu.** On the web, the pharmacist's menu also lists Members,
  Organization, Branches and Printers. The API decides what each role may
  change, but whether pharmacists should see these pages is a product
  decision to review.
- **Rural doctor on Android.** In Rural Clinic mode the rural *doctor*
  account shows two steps, Queue and Fast Rx. Register and Bill appear only
  for roles that hold those permissions. This is by design, but a
  single-doctor clinic may want the doctor to hold all four.
- **Prescriptions.** Signing a prescription works without a recorded
  diagnosis; only the free-text field is offered. Decide whether a diagnosis
  should be required.

# IMPLEMENTATION PLAN — Aditya BioNova Smart HMS (Commercial)

Inputs: [AUDIT_REPORT.md](AUDIT_REPORT.md), [GAP_ANALYSIS.md](GAP_ANALYSIS.md).
Status: **proposal — awaiting product-owner approval before M7.0 starts.**

## 1. Principles

1. **Fix before build.** No new module starts while a Critical/High defect is open in a module it depends on.
2. **Keep the architecture.** Modular monolith (FastAPI + PostgreSQL RLS + Next.js + Flutter) stays. No microservices, no rewrite. Extend the existing DB-guard + test patterns.
3. **Every defect fix ships with a failing-first regression test** (raw-SQL proof where a DB guard is involved).
4. **Development branch only.** Work lands on `claude/pensive-albattani-n0zcba` (or successor feature branches) via PR into `main`; CI must be green; no direct commits to `main`.
5. **No public deployment and no real patient data** until the M14 human gates pass.
6. **Docs updated in the same PR** as the code they describe (TASKS, TEST_RESULTS, API/DB docs).
7. **AI is assistive, opt-in, audited, and never prescribes.**

## 2. Milestone roadmap (prioritised)

| # | Milestone | Goal | Depends on | Size* |
|---|---|---|---|---|
| **M7.0** | **Correctness & security hardening** *(proposed first)* | Close all Critical + High defects; make CI trustworthy | — | L (≈3–4 wks) |
| M7.1 | Identity & tenant administration | MFA, password reset, lockout, invitations, member admin, branch-scoped RBAC, admin/settings UI | M7.0 | M |
| M7.2 | SaaS commercial layer | Plans/editions/entitlements, trials, subscriptions, gateway (sandbox), super-admin console, tenant export | M7.1 | L |
| M8 | Billing 2.0 (GST) | Tariff/price master, GST invoice (GSTIN, SAC/HSN, CGST/SGST/IGST), FY series, credit notes, real UPI gateway sandbox | M7.0 | L |
| M9 | Pharmacy commercial | Tenant item master, MRP/selling price, counter sale + bill, returns, suppliers/PO/GRN, schedule registers, pharmacy-only edition | M8 | L |
| M10 | Laboratory commercial | Analyte parameters, age/sex ranges + auto-flag, critical alerts, report PDF, lab billing, walk-in/referrer, lab-only edition | M8 | L |
| M11 | Hospital depth | IPD billing (bed-day, packages, deposits), discharge summary, MAR, ER triage, OT scheduling; insurance/TPA (phase 1) | M8 | XL |
| M12 | Android & offline v2 | Offline unlock, background sync, retry/backoff, server version checks, pharmacy/lab/IPD rounds on mobile, mr/hi i18n, crash reporting, device QA | M7.0 | L |
| M13 | AI Intelligence (assistive) | Governance layer → operational forecasting → deterministic DDI/dose checks → note drafting (voice, trilingual) → lab-summary drafts | M7.2, M10 | L |
| M14 | Integrations & release gates | ABDM (ABHA/HIP), SMS/WhatsApp/e-mail, FHIR export, observability, backups+DR drill, staging IaC, load test, pentest, DPDP/CDSCO legal review, clinical validation, supervised pilot (5–10 sites) | all | XL |

\*Size is relative engineering effort for planning only; dates are set after M7.0 velocity is known.

Parallelisable once M7.0 is done: M7.1 ∥ M8 ∥ M12.

---

## 3. M7.0 — Correctness & Security Hardening (proposed first milestone)

**Scope rule:** fixes only — no new modules, no architectural change. Each item = test first, then fix.

### 3.1 Patient safety (P0)
| Item | Fix | Acceptance test |
|---|---|---|
| C1 | Editable dose/route/frequency/duration/quantity in web consultation; required fields, no silent defaults | Playwright: doctor sets "500 mg BD 3 days" → signed Rx shows exactly that |
| H1 | Add INSERT to `trg_rxitem_immutable` (new migration) | Raw-SQL: INSERT into signed Rx blocked |
| H2 | Accept SpO₂ < 85 when an escalation note is supplied; still reject physiologically impossible values | API: 84 + note → 201; 84 without note → 422 |
| H3 | Merge carries allergies (union) and re-points clinical records, or blocks merge with conflicting data until reviewed | Allergy on retired record still blocks signing on survivor |
| H4 | Structured Rx quantity; dispense cap = prescribed − already dispensed | Second dispense beyond Rx → 409 |
| H5 | Rx print: prescriber name + registration no., clinic header, drug names from the Rx itself (not active catalog) | Print of Rx with deactivated drug shows name |
| H6 | `enc_status` param fix | Completed encounter not loaded as active |
| C2 + H7 | `lab_order_items` table (migration + backfill from audit metadata where possible); results must match an ordered item; release requires all items resulted; multiple specimens; re-collection after rejection | Result for un-ordered test → 422; release with missing result → 409 |

### 3.2 Money integrity (P0)
| Item | Fix | Acceptance test |
|---|---|---|
| H8 | Report revenue = gross succeeded+refunded payments; net = revenue − refunds − expenses | Refunded ₹1000 → net 0 |
| H9 | `SELECT … FOR UPDATE` on invoice for pay/confirm/refund; reserve pending sandbox payments; CHECK `amount_paid BETWEEN 0 AND total` | Concurrent payment test (threads) → no overpay |
| H11 | Idempotency-Key on `POST /prescriptions` and `POST /billing/invoices` | Replay returns same id |
| H12 | Idempotency via `INSERT … ON CONFLICT` in a savepoint; reject keys > 100 chars with 422 | Concurrent same-key → one record, both responses consistent |
| H13 | Per-attempt UUID keys in web; disable buttons in flight; refund UI | Playwright double-click → one payment |
| M | Invoice immutability: block issued→draft and DELETE; payments/refunds append-only triggers | Raw-SQL proofs |
| M | GST on post-discount amount | Unit test of totals |

### 3.3 Security (P0)
| Item | Fix |
|---|---|
| H14 | `POST /members` never attaches an existing user from another tenant: invitation token flow (or 409 without revealing identity); never return foreign user's profile |
| H15 | Validate/truncate `X-Request-ID` (≤64, `[A-Za-z0-9-]`) |
| H16 | Rate limiting (login, register, refresh) + progressive account lockout; audit lockouts |
| H17 | Refuse known/default/short secrets when `ENVIRONMENT != development/test`; honour `JWT_*_TTL_SECONDS` |
| H18 | Audit PHI reads (patient, encounter, Rx, lab result, admission detail endpoints) |
| H19 | Web: refresh token in httpOnly SameSite=Strict cookie via Next route handler; access token in memory; silent refresh; CSP + security headers; `middleware.ts` guard |
| M | Refresh-token row lock; absolute session lifetime; org-suspension check per request; trusted-proxy list for `X-Forwarded-For`; fix `insert_audit_event` empty-GUC guard; reject cross-tenant foreign IDs (branch/appointment/encounter) with 404; scrypt N → 2¹⁷ with transparent rehash on login |

### 3.4 Android (P0)
C3 INTERNET permission in main manifest · H23 `allowBackup=false` + fail-closed store with recovery screen · H22 offline unlock with cached session + device PIN · H20 per-user outbox partition / wipe on sign-out · H24 keep unsynced offline patients in pickers · HTTP timeouts.

### 3.5 Engineering hygiene (P0)
* Declare partial indexes in models → `alembic check` clean, and add it to CI.
* Python lock file; pin Docker images; SHA-pin GitHub Actions; `permissions: contents: read`.
* CI: add Flutter job (`flutter analyze`, `flutter test`), `pip-audit`, `npm audit`, gitleaks, ESLint; Playwright smoke suite for login → register patient → consult → sign Rx → bill → pay.
* Upgrade Next.js to clear the postcss advisory (or pin patched postcss via `overrides` if Next 16 migration is deferred).
* Containers: non-root, `.dockerignore`, healthchecks, separate migration job, runtime-configurable API origin; `/health/ready` checks DB.
* Map DB trigger errors to 409; commit before response (explicit commit in handler or middleware).
* Docs refresh: README status, TEST_RESULTS (M4–M7.0), API_DOCUMENTATION (generated from contract), DATABASE_SCHEMA (0006–000x), SECURITY_CHECKLIST corrections.

### 3.6 M7.0 exit criteria
* All C1–C3 and H1–H24 closed with regression tests; Medium items above closed or explicitly deferred by the owner.
* API, web (lint + unit + Playwright smoke), Flutter (analyze + test), `alembic check`, dependency scans: **all green in CI**.
* Docker stack builds and passes a smoke test in CI (private, not deployed).
* Updated TEST_RESULTS.md with real numbers.

---

## 4. Later milestones — key acceptance criteria

**M7.1 Identity & admin** — TOTP MFA (mandatory for owner/admin), e-mail reset with single-use tokens, invitation acceptance, member suspend/role change/session revoke UI, branch-scoped data access enforced in RLS or service layer, settings UI (clinic profile, letterhead, branches, masters).

**M7.2 SaaS layer** — `plans`, `entitlements`, `subscriptions`, `tenant_usage` tables (vendor-scoped, not tenant RLS); entitlement checks as a FastAPI dependency (like `require_permission`); trial → paid → grace → read-only lifecycle; gateway webhooks with signature verification; vendor super-admin console with consented, audited impersonation; tenant export (CSV + FHIR bundle).

**M8 Billing 2.0** — tariff master per branch; GST engine (intra/inter-state, exempt healthcare services vs taxable goods), FY-reset invoice series allocated on *issue*; credit notes instead of edits; Decimal end-to-end in API (no float).

**M9 Pharmacy** — tenant drug master importable from CSV; purchase cycle with supplier ledger; counter sale with GST bill; returns; H1/narcotic registers; pharmacy-only edition toggled by entitlements.

**M10 Laboratory** — analyte model; reference ranges by age/sex/unit; auto H/L/critical flags; critical-value notification; signed PDF with QR verification; lab-only edition.

**M11 Hospital** — IPD running bill from bed-days + services + pharmacy issues; deposits; discharge summary; MAR; ER triage & MLC; OT scheduling; TPA pre-auth tracking.

**M12 Android v2** — WorkManager background sync, exponential backoff, server-side `X-Base-Version` checks (412), offline unlock, mr/hi i18n, pharmacy/lab/IPD rounds screens, crash reporting, physical-device QA matrix.

**M13 AI** — governance first: provider abstraction, tenant opt-in, PHI redaction, full prompt/output audit, explicit clinician accept. Order: (1) stock & no-show forecasting, (2) deterministic DDI/dose-range engine on a licensed knowledge base, (3) ambient/voice note drafting (EN/मराठी/हिंदी), (4) lab-result patient summaries. Legal review of CDSCO SaMD classification before (2)–(4) reach customers.

**M14 Release gates (human)** — independent pentest + ASVS L2, DPDP compliance review, clinical safety validation, backup/restore drill, load test at target scale, supervised pilot at 5–10 sites. **No "production-ready" claim before these pass.**

---

## 5. Decisions needed from the product owner

1. **Approve M7.0 scope** (§3) as the first milestone — fixes only, no new modules.
2. E-mail / SMS / WhatsApp provider (blocks password reset, MFA recovery, reminders).
3. Payment gateway for both patient payments and SaaS subscriptions (Razorpay / Cashfree / PhonePe).
4. Edition & pricing model (Clinic / Hospital / Pharmacy / Lab / bundles; per-user vs per-branch vs per-bed).
5. Next.js 16 upgrade now vs postcss override (security advisory).
6. AI provider and data-residency stance (India-region hosting requirement?).
7. Hosting provider for private staging.
8. ABDM certification timing (needed for government/hospital tenders).

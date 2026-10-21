# GAP ANALYSIS — All-in-One Commercial HMS

Baseline: commit `91c5f2a` (M1–M6), audited 2026-10-20 — see [AUDIT_REPORT.md](AUDIT_REPORT.md).
Target: a single commercial SaaS product serving **Clinic, Hospital, Pharmacy and
Laboratory** customers in India, with web + Android (offline), AI assistance,
subscription billing and production-grade security.

Legend: ✅ Done (tested) · ⚠️ Partial · 🔴 Broken (defect ID from AUDIT_REPORT) · ❌ Missing.
Priority: **P0** release-blocker · **P1** needed for first paid customer · **P2** competitive parity · **P3** later/differentiator.

---

## 1. Platform & security

| Capability | Status | Gap | Priority |
|---|---|---|---|
| Multi-tenant isolation (RLS) | ✅ | Add FORCE RLS; tenant-consistent composite FKs; reject cross-tenant foreign IDs (M-findings) | P0 |
| RBAC (roles/permissions) | ✅ | Branch-scoped access (`memberships.branch_id` unused); custom roles; UI hides unauthorised actions | P1 |
| Member management | 🔴 H14 | Invitation/consent flow; suspend/role change/revoke sessions endpoints | P0 |
| Auth: login/refresh/logout | ✅ | Refresh race; absolute session lifetime; org suspension enforcement per request | P0 |
| MFA (TOTP), password reset/change, lockout | ❌ | Needs e-mail/SMS provider decision | P0 |
| Rate limiting / abuse protection | ❌ H16 | Login/register/OTP limits, CAPTCHA on public signup | P0 |
| Secrets/config hardening | 🔴 H17 | Refuse default secrets outside dev; honour TTL env vars; secret manager | P0 |
| Audit trail | ⚠️ H15, H18 | Validate request-id; audit PHI reads (purpose-of-use); fix definer-function guard | P0 |
| Web session security | 🔴 H19 | httpOnly cookie refresh, CSP + security headers, server-side route guard (middleware) | P0 |
| Data protection (DPDP Act 2023) | ❌ | Consent records, data-principal requests (export/erasure where lawful), retention policy, breach notification runbook | P1 |
| Encryption at rest | ⚠️ | Mobile ✅; server relies on volume encryption — document KMS; field-level encryption for Aadhaar/ABHA if stored | P1 |
| Dependency/SAST/secret/image scanning | ❌ | pip-audit, npm audit (current: postcss high), CodeQL, gitleaks, Trivy; lock files | P0 |
| Independent pentest / ASVS L2 | ❌ | Human gate before launch | P1 |

## 2. Clinic (OPD) edition

| Capability | Status | Gap | Priority |
|---|---|---|---|
| Patient registration, UHID, dedupe | ✅ | Edit UI; merge must carry allergies/history (🔴 H3) | P0 |
| Appointments | ⚠️ | Double-booking race; doctor schedules/slots, calendar view, reminders (SMS/WhatsApp) | P1 |
| OPD queue / tokens | ⚠️ | Live updates (SSE/poll), per-branch token series, priority ordering, cancel endpoint, IST day boundary | P1 |
| Consultation (vitals, diagnosis) | ⚠️ 🔴 H6 | ICD-10 coding, templates/favourites, longitudinal patient chart, attachments | P1 |
| e-Prescription | 🔴 C1, H1, H5 | Editable dose/frequency/duration; DB INSERT guard; legally compliant print (prescriber reg. no., clinic header, generic names per NMC); draft edit/delete; brand↔generic allergy mapping | P0 |
| OPD billing & receipts | ⚠️ 🔴 H8, H9, H11 | GST-compliant invoice (GSTIN, SAC/HSN, CGST/SGST/IGST), FY invoice series, tariff/price master, discount approval, credit notes | P0/P1 |
| Payment gateway | ⚠️ sandbox sim | Razorpay/Cashfree/PhonePe UPI integration with webhook signature verification | P1 |
| Certificates (fitness/sick leave), referral letters | ❌ | Templates + print | P2 |
| Patient portal / app | ❌ | Booking, reports, bills | P3 |

## 3. Hospital (IPD) edition

| Capability | Status | Gap | Priority |
|---|---|---|---|
| Wards/beds, admission, transfer, discharge | ✅ | N+1 in ward list; discharge summary print | P1 |
| Nursing records | 🔴 H2 | Allow critical values with escalation; MAR (medication administration record); intake/output; care plans | P0/P1 |
| IPD billing | ❌ | Bed-day tariffs, package billing, deposits/advances, running bill, interim & final bill | P1 |
| Insurance / TPA / PM-JAY | ❌ | Pre-auth, claim tracking, co-pay split, cashless workflow | P2 |
| Emergency (ER/triage) | ❌ | Quick registration, triage levels, MLC flag | P2 |
| OT scheduling & notes | ❌ | OT calendar, surgical checklist (WHO), anaesthesia notes | P2 |
| ICU charting | ❌ | High-frequency vitals, device integration (see M8 devices) | P3 |
| Diet / housekeeping / CSSD | ❌ | | P3 |

## 4. Pharmacy edition

| Capability | Status | Gap | Priority |
|---|---|---|---|
| Drug catalog, batches, expiry, FEFO | ✅ | Catalog is a global seed (45 drugs) — tenant item master, brand/generic, HSN, schedule (H/H1/X) flags | P1 |
| Dispensing against signed Rx | 🔴 H4 | Quantity caps vs Rx, repeat-dispense guard, structured quantity | P0 |
| Pharmacy sales billing | 🔴 H10 | MRP/selling price, GST by HSN, counter sale (walk-in), bill print, returns | P0/P1 |
| Purchasing | ❌ | Suppliers, purchase orders, GRN, purchase returns, supplier ledger | P1 |
| Stock controls | ⚠️ | Recall API, reason-code master, inter-branch transfer, physical stock audit | P1 |
| Schedule H1 register / narcotics register | ❌ | Statutory registers | P1 |
| Standalone pharmacy tenant (no clinic) | ❌ | Edition flags so a pharmacy-only customer sees only pharmacy | P1 |

## 5. Laboratory edition

| Capability | Status | Gap | Priority |
|---|---|---|---|
| Test catalog | ⚠️ | Panels have no analyte-level parameters; free-text reference ranges | P0 |
| Orders | 🔴 C2 | Order-item table; per-test status; multiple specimens per order (H7) | P0 |
| Specimens / barcodes | ⚠️ | Barcode race; label printing | P1 |
| Results, four-eyes, amendments | ✅ | DB-level four-eyes backstop; empty results blocked; auto-flagging vs age/sex ranges; critical-value alerts | P0/P1 |
| Lab report print/PDF | ❌ | Branded report with signatures, QR verification | P1 |
| Lab billing | ❌ | Test price master → invoice | P1 |
| Outside/walk-in lab patients, referring doctors, commissions | ❌ | | P2 |
| Analyzer interfacing (ASTM/HL7) | ❌ | | P3 |
| Radiology (RIS/PACS link) | ❌ | | P3 |

## 6. Android & offline

| Capability | Status | Gap | Priority |
|---|---|---|---|
| Release build | 🔴 C3 | INTERNET permission, `allowBackup=false`/backup rules, R8 config, signing pipeline | P0 |
| Encrypted offline store + outbox | ✅ | Hard failure instead of silent in-memory fallback (H23) | P0 |
| Offline after restart | 🔴 H22 | Offline unlock (local PIN/biometric) using cached session | P0 |
| Sync engine | ⚠️ | Timeouts, retry/backoff, connectivity trigger, background sync (WorkManager), token refresh, 408/429 handling | P0/P1 |
| Conflict resolution | ⚠️ | Server must honour `X-Base-Version`; resolvable duplicate-patient path | P1 |
| Multi-user device safety | 🔴 H20 | Wipe or partition outbox per user on sign-out | P0 |
| Server idempotency for all outbox ops | 🔴 H11 | Rx + invoice creation | P0 |
| Mobile modules | ⚠️ register/queue/Rx/billing | Pharmacy, lab worklist, IPD nursing rounds, i18n (mr/hi), push notifications | P1/P2 |
| Crash reporting, app lock / FLAG_SECURE | ❌ | | P1 |
| Device QA on entry-level hardware | ❌ | Human gate | P1 |
| Flutter tests in CI | ❌ | | P0 |

## 7. AI Intelligence

Currently **none** (intentionally excluded). Commercial-grade AI must be
assistive-only, opt-in per tenant, auditable, and never autonomous in prescribing.

| Capability | Status | Notes | Priority |
|---|---|---|---|
| AI governance layer | ❌ | Tenant opt-in, per-feature flags, PHI minimisation/redaction, prompt+output audit log, human-accept step, provider DPA | P1 (prerequisite) |
| Clinical note drafting (voice → SOAP draft, trilingual) | ❌ | Doctor reviews/edits before save | P2 |
| Drug-interaction / dose-range checks | ❌ | Rule/knowledge-base driven (deterministic), not LLM | P1 |
| Lab result interpretation summary | ❌ | Draft patient-friendly explanation; clinician releases | P2 |
| Operational analytics (no-show prediction, stock forecasting, bed occupancy forecast) | ❌ | Non-clinical; lower regulatory risk — good first AI feature | P2 |
| Natural-language report queries | ❌ | Tenant-scoped, read-only, RLS-respecting | P3 |
| Regulatory | ❌ | Any diagnostic/CDS claim may fall under CDSCO SaMD rules — legal review required | gate |

## 8. SaaS subscription & commercial layer

| Capability | Status | Gap | Priority |
|---|---|---|---|
| Plans / editions (Clinic, Hospital, Pharmacy, Lab, bundles) | ❌ | Plan catalog, feature entitlements, limits (users, branches, beds) | P0 for launch |
| Trials, subscriptions, renewals, dunning | ❌ | Recurring billing via gateway; grace period; read-only mode on expiry | P1 |
| SaaS invoices (GST) for the tenant | ❌ | | P1 |
| Self-serve signup + onboarding wizard | ⚠️ register endpoint only | Clinic profile, letterhead, branches, staff invite, masters import | P1 |
| Super-admin console (vendor side) | ❌ | Tenant list, plan changes, suspension, support impersonation with consent + audit | P1 |
| Tenant data export / offboarding | ❌ | Full export (CSV/FHIR), deletion workflow | P1 |
| Support tickets / in-app help | ❌ | | P2 |
| Usage metering & analytics | ❌ | | P2 |

## 9. Integrations & compliance (India)

| Capability | Status | Priority |
|---|---|---|
| ABDM: ABHA creation/linking, HIP/HIU, health-record consent | ❌ | P2 (P1 for hospital tenders) |
| SMS / WhatsApp / e-mail notifications | ❌ | P1 |
| e-Invoice (IRN) for B2B where applicable | ❌ | P3 |
| Tally / accounting export | ❌ | P2 |
| FHIR R4 export | ❌ | P2 |
| NABH/NABL-oriented reports & registers | ❌ | P2 |

## 10. Engineering, operations & quality

| Capability | Status | Gap | Priority |
|---|---|---|---|
| API test suite | ✅ 102 tests, 93 % | Add tests for every defect fixed; concurrency tests | P0 |
| Web tests | ❌ | ESLint, component tests, Playwright E2E for the golden paths | P0 |
| Migration hygiene | 🔴 | Fix ORM drift; `alembic check` in CI; data-safe downgrades | P0 |
| Reproducible builds | ❌ | Python lock file (uv/pip-tools), pinned images by digest, SHA-pinned actions | P0 |
| Containers | 🔴 H21 | Non-root, `.dockerignore`, healthchecks, separate migrate job, runtime API_ORIGIN | P0 |
| Observability | ❌ | Structured logs, metrics, tracing, error tracking (self-hosted Sentry/GlitchTip), uptime | P1 |
| Backups & DR | ❌ | Automated encrypted backups, PITR, tested restore drill | P1 |
| Staging environment + IaC | ❌ | Private staging only (no public deploy until gates) | P1 |
| Performance | ❌ | p95 latency budget, load test (k6), index review | P2 |
| Documentation | 🔴 stale | README, API_DOCUMENTATION, DATABASE_SCHEMA, TEST_RESULTS refresh; generated API docs from contract | P0 |

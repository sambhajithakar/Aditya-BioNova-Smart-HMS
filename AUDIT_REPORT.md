# AUDIT REPORT — Aditya BioNova Smart HMS

| | |
|---|---|
| Audit date | 2026-10-20 |
| Repository | `sambhajithakar/Aditya-BioNova-Smart-HMS` (only repository touched) |
| Audited commit | `91c5f2a` (M6) — identical to `origin/main` |
| Development branch | `claude/pensive-albattani-n0zcba` (no commits to `main`) |
| Data used | Synthetic test fixtures only. No real patient data. Nothing deployed. |
| Companion docs | [GAP_ANALYSIS.md](GAP_ANALYSIS.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · evidence in [docs/audit/](docs/audit/) |

---

## 1. Executive summary

The repository is a **well-structured, genuinely tested modular monolith**, not a
prototype shell: FastAPI + PostgreSQL 16 with row-level security on every tenant
table, append-only ledgers enforced by database triggers, a Next.js web portal with
14 working screens, and a Flutter Android app with a real encrypted offline outbox.
The automated test suite **re-ran green in this audit (102/102, 93 % line coverage)**.

However, it is **not commercially releasable today**. The audit found:

* **3 Critical** and **~20 High** defects — several of them patient-safety or
  money-integrity issues (prescription dose cannot be set in the web UI; lab orders
  silently discard the ordered tests; signed prescriptions can still gain items at
  DB level; finance report shows −₹1000 for a refunded ₹1000 payment; the release
  Android APK has no INTERNET permission; tenant A can enrol tenant B's users).
  Four were **reproduced at runtime** (H1, H8, H14, H15); the three Critical ones were
  confirmed line-by-line in code (§4).
* Large **commercial gaps**: no SaaS subscription/plan layer, no GST-compliant
  invoicing, no tariff master or IPD billing, no pharmacy purchasing/sales billing,
  no lab report printing, no MFA/password reset/rate limiting, no AI features, no
  ABDM integration, no observability/backups, no E2E tests.
* **Documentation drift**: README still says "Milestone M1"; API_DOCUMENTATION and
  DATABASE_SCHEMA stop at M3; TEST_RESULTS stops at M3; several "✅" claims in
  TASKS/SECURITY_CHECKLIST are false (§5).

**Recommendation:** do not start new modules yet. The first milestone should be a
**correctness & security hardening sprint (M7.0)** that fixes every Critical/High
defect below without architectural change, then proceed to the SaaS + GST billing
layer. See IMPLEMENTATION_PLAN.md §2.

---

## 2. Scope and method

| Area | What was done | Executed? |
|---|---|---|
| FastAPI backend | Full static review of all routers, services, models, schemas (≈9.6k LoC) | ✅ tests run |
| PostgreSQL / migrations | All 8 Alembic migrations reviewed; upgrade → downgrade base → upgrade round-trip on empty DB; `alembic check` for ORM drift | ✅ executed |
| Security / tenancy | RLS coverage of all 40 tables, RBAC seed vs usage, JWT/session/refresh flows, audit trail | ✅ + runtime probes |
| Next.js web | All 14 pages, API client, auth, i18n, CSS; every API call checked against the OpenAPI contract | ✅ typecheck + build run |
| Flutter Android | All `lib/` and `test/` Dart, manifests, Gradle | ⚠️ **static only — Flutter SDK not available in the audit container; the 40 Dart tests were NOT executed** |
| Infra / CI | Dockerfiles, compose, CI workflow, scripts | ⚠️ static only — Docker images not built/run |
| Documentation | All 11 root docs read and claims cross-checked against code | ✅ |
| Dependencies | `pip-audit`, `npm audit --omit=dev` | ✅ executed |

Four independent reviewers (backend-security, backend-domain, web, mobile+infra)
produced line-referenced findings; the most serious were re-verified by hand and
with runtime probes. Full per-area findings: `docs/audit/A1…A4`.

---

## 3. Real test results (executed 2026-10-20)

Environment: Linux container, Python 3.13.16, PostgreSQL 16.15 (local cluster on
:5433, app queries as non-owner `hms_app` → RLS active), Node 22.22.0.

| Check | Command | Result |
|---|---|---|
| API lint | `ruff check apps/api --select F,E --line-length 100` | ✅ All checks passed |
| API test suite | `cd apps/api && pytest` | ✅ **102 passed, 0 failed** in 18.1 s |
| API coverage | `pytest --cov=app` | ✅ **93 %** lines (3870 stmts, 264 missed); lowest `services/clinical.py` 79 % |
| Migrations round-trip | `alembic upgrade head → downgrade base → upgrade head` (empty DB) | ✅ clean |
| ORM ↔ migration drift | `alembic check` | ❌ **FAILED** — 13 drift ops. Partial unique indexes (`uq_admission_bed_occupied`, `uq_admission_patient_active`, `uq_enc_one_open`, `uq_labresult_live_per_test`, 4× `uq_ledger_*`) exist only in migrations, not in models. A future `alembic revision --autogenerate` would emit **DROP** for these safety indexes. |
| OpenAPI contract | `scripts/generate-contracts.sh` + `git diff` | ✅ 74 paths, snapshot in sync |
| Web typecheck | `npm run typecheck` | ✅ clean |
| Web build | `npm run build` | ✅ 17 routes built |
| Web lint / unit / E2E | — | ❌ **none exist** (no ESLint config, no Jest/Vitest, no Playwright) |
| Python vuln scan | `pip-audit -r apps/api/requirements.txt` | ✅ No known vulnerabilities |
| Node vuln scan | `npm audit --omit=dev` | ⚠️ **1 high, 1 moderate** — `postcss ≤ 8.5.22` via `next` (GHSA-qx2v-qp2m-jg93 and 3 related); fix requires Next 16 (breaking) |
| Flutter tests (40) | `flutter test` | ⚠️ **NOT RUN** — SDK unavailable here; count of 40 verified statically |
| Docker stack | `docker compose up` | ⚠️ **NOT RUN** — never executed by anyone per DEPLOYMENT.md |

Note: `requirements.txt` uses version ranges with no lock file; this run resolved
FastAPI 0.151 / Starlette 1.9 / SQLAlchemy 2.1.5 — newer than CI's earlier runs.
Builds are therefore not reproducible (finding SEC-M10).

---

## 4. Defects — prioritised

Severity: **C** = Critical (patient safety, data integrity or release-blocking),
**H** = High, **M** = Medium. "Proven" = reproduced at runtime in this audit;
"Code" = verified by reading the cited line.

### 4.1 Critical

| ID | Area | Defect | Evidence |
|---|---|---|---|
| C1 | Web / clinical | **Prescription dose, frequency and duration are hard-coded** to "1 tablet · TDS · 5 days" in the consultation screen; the doctor cannot change them, so every web-signed Rx carries this dosing. | Code: `apps/web/src/app/consultation/page.tsx:431` |
| C2 | Lab | **Lab orders discard the ordered tests.** `test_ids` are validated then thrown away (no order-item table). Any test can be resulted on any order; an order can be "released" with ordered tests never resulted. | Code: `apps/api/app/routers/lab.py:168-190`, `models.py:1310-1372` |
| C3 | Android | **Release APK cannot reach the network** — `INTERNET` permission exists only in the debug/profile manifests. | Code: `apps/mobile/android/app/src/main/AndroidManifest.xml` (0 matches) |

### 4.2 High — patient safety & clinical integrity

| ID | Defect | Evidence |
|---|---|---|
| H1 | **Signed prescriptions can gain new items** — immutability trigger is `BEFORE UPDATE OR DELETE`, not INSERT (invoice-items trigger correctly includes INSERT). | **Proven** (raw INSERT into signed Rx succeeded as `hms_app`). `0006_m3…py:640-641` |
| H2 | **SpO₂ < 85 can never be recorded** in nursing vitals, though docs say it is accepted with an escalation note. Hypoxic patients cannot be charted. | Code: `schemas.py:1218-1226` |
| H3 | **Patient merge drops the retired record's allergies/history** — allergy gate then misses them. | Code: `routers/patients.py:285-286` |
| H4 | **Signed Rx can be dispensed unlimited times / any quantity** (Rx quantity is free text). | Code: `routers/pharmacy.py:394-424`, `models.py:785` |
| H5 | **Printed Rx lacks prescriber name/registration no. and clinic identity**; deactivated drugs print as "—". | Code: `apps/web/src/app/print/rx/[id]/page.tsx:77,193,243,274` |
| H6 | **Consultation page loads completed encounters** (sends `?status=` but API expects `enc_status`). | Code: `consultation/page.tsx:68` vs `encounters.py:166` |
| H7 | Lab order supports only **one specimen**; a rejected specimen strands the order. | Code: `lab.py:282-287, 334-335` |

### 4.3 High — money integrity

| ID | Defect | Evidence |
|---|---|---|
| H8 | **Finance report double-counts refunds** — refunded ₹1000 payment shows `net = −1000`. | **Proven**: `{'revenue': 0.0, 'refunds': 1000.0, 'net': -1000.0}`. `reports.py:100-115` |
| H9 | **Overpayment / over-refund possible** — no row locks on `amount_paid` read-modify-write; sandbox payments not reserved against balance; no `amount_paid <= total` constraint. A lost update makes `/receipt` 500 permanently. | Code: `billing.py:362-390, 439, 459-485, 540-567` |
| H10 | **Pharmacy dispenses are valued at cost price and never billed** (no MRP/selling price/GST/invoice link). | Code: `services/pharmacy.py:158` |
| H11 | `POST /prescriptions` and `POST /billing/invoices` **ignore `Idempotency-Key`** although the mobile outbox relies on it → lost-response retry creates duplicate invoices/Rx. | Code: `prescriptions.py:163`, `billing.py:111` |
| H12 | Idempotency race: concurrent duplicate key rolls back the transaction but the handler still **returns 201 with a record that was never saved**; keys > 100 chars always hit this path. | Code: `services/clinical.py:155, 188, 196-199` |
| H13 | Web: idempotency keys are derived from business data (legit repeats silently replayed); cash payment button not disabled in flight; **no refund UI**. | Code: `pharmacy/page.tsx:150,178`, `billing/page.tsx:136-140` |

### 4.4 High — security

| ID | Defect | Evidence |
|---|---|---|
| H14 | **Cross-tenant user enrolment** — `POST /members` with another tenant's e-mail adds that existing user to the caller's org without consent, ignores the supplied password and returns the victim's real name (enumeration + login disruption). | **Proven**: org A enrolled `owner@clinic-b…`, response 201 with `"full_name":"Dr. Test Owner"`. `members.py:68-80` |
| H15 | **Unvalidated `X-Request-ID` > 64 chars crashes every audited write** (500) — also suppresses failed-login audit, hiding brute force. | **Proven** (`StringDataRightTruncation varchar(64)`). `main.py:63`, `0001:161` |
| H16 | **No rate limiting / lockout anywhere**; open `/auth/register` runs a 16 MiB scrypt per call → brute-force and DoS surface. | Code: no limiter in `main.py`/`auth.py` |
| H17 | **Public default JWT secret accepted in production** (`"insecure-dev-only-secret-change-me"` passes the ≥16-char check). | Code: `config.py:28,36-41` |
| H18 | **PHI reads are not audited** (no GET writes an audit event) — contradicts SECURITY_CHECKLIST. | Code: e.g. `patients.py:190-201` |
| H19 | Web: **access + refresh tokens in localStorage, no CSP, refresh never called** (staff logged out every 30 min, losing forms); route guard is client-only. | Code: `apps/web/src/lib/auth.ts:18-29`, `next.config.mjs` |
| H20 | Mobile: sign-out leaves outbox + patient cache on device → **pushed under the next user's login**; refresh token never used. | Code: `apps/mobile/lib/auth/session.dart`, `sync/engine.dart` |
| H21 | Containers run as root, no `.dockerignore` (local `.env` can be baked into the image), migrations run on every start. | Code: `infra/docker/api.Dockerfile:13,19` |

### 4.5 High — offline/mobile reliability

| ID | Defect | Evidence |
|---|---|---|
| H22 | App always starts at network login → **offline features unreachable after a restart without signal** (test injects a token and hides this). | Code: `apps/mobile/lib/main.dart:152` |
| H23 | Decrypt/Keystore failure silently falls back to an **in-memory store** (offline work not persisted); with default `allowBackup`, a restored device hits this forever. | Code: `main.dart:133-135`, main manifest |
| H24 | Queue refresh replaces the patient list, dropping unsynced offline registrations; raw device UUID then sent as `patient_id`. | Code: `screens/queue_tab.dart:56,76-79` |

### 4.6 Medium (selected — full lists in docs/audit)

* ORM↔migration drift would drop safety indexes on autogenerate (§3).
* Cross-tenant foreign IDs accepted for `branch_id`, `appointment_id`, `encounter_id` (Postgres FK checks bypass RLS) — `pharmacy.py:134,409`, `lab.py:170`, `ipd.py:160`, `opd_queue.py:117`, `encounters.py:124`.
* Race conditions: appointment double-booking, duplicate OPD queue entries, lab barcode allocation.
* Day boundaries computed in UTC for an IST product (`opd_queue.py:44`, `reports.py:38-43`, mobile "today").
* GST computed on pre-discount amount; invoice numbers allocated at draft (gaps, no financial-year series).
* Issued invoices can be set back to draft and deleted at DB level; payments/refunds have no immutability trigger; completed encounters deletable.
* `insert_audit_event` org guard passes when the GUC is empty; refresh-token race mints two sessions; sessions extend forever; `X-Forwarded-For` trusted from any client; scrypt N=2¹⁴ (below OWASP 2¹⁷).
* Commit happens after the response is sent (FastAPI ≥0.1xx dependency teardown) — a commit failure still returns 2xx.
* DB trigger errors surface as 500 instead of 409.
* Web: `button.ghost` is white-on-transparent → likely invisible action buttons on white cards (`globals.css:130-137`); patient pickers capped at 100; branch always `branches[0]`; ~70 untranslated strings; no responsive CSS; UI ignores RBAC.
* Mobile: no HTTP timeout, no automatic retry/backoff, 408/429 parked as conflicts, "Keep local" cannot resolve duplicate-patient 409, discarded registration strands dependants.
* Infra: Next.js rewrite destination likely baked at **build** time (`API_ORIGIN`) → container may proxy to its own localhost (unverified — needs a build); compose exposes Postgres on all interfaces with `change_me`; `/health` doesn't check DB; floating image tags; CI actions not SHA-pinned, no `permissions:` block, no Flutter job, no security scanning.
* Downgrade migrations fail on populated databases (delete referenced seed rows).

---

## 5. Documentation claims vs reality

| Claim (doc) | Verdict |
|---|---|
| README: "Status: Milestone M1 … clinical modules not built yet", "33 tests" | ❌ Stale — M1–M6 built, 102 API tests |
| TEST_RESULTS.md | ❌ Stale — stops at M3 (72 tests); header says M1+M2 |
| API_DOCUMENTATION.md | ❌ Omits every M5/M6 endpoint (contract has 74 paths) |
| DATABASE_SCHEMA.md | ❌ Stops at migration 0005; RLS table omits 0006–0008 tables; claims composite tenant FKs that don't exist; org INSERT policy description inaccurate |
| TASKS M3/M6: "signed Rx immutable", "SpO₂ < 85 accepted with escalation note" | ❌ False (H1, H2) |
| TASKS M4: "no double invoice", stale-write protection via `X-Base-Version` | ❌ False — API ignores both (H11) |
| TASKS M5: "reason-coded adjustments", batch recall | ⚠️ Reasons are free text; no recall/return API |
| TASKS M1/M2: "refresh rotation" (web), "full i18n", "live queue board", "design system" | ⚠️ Backend only / partial / no polling |
| SECURITY_CHECKLIST: "no account enumeration", "PHI access recorded", "security headers" | ❌ Register & members reveal e-mails; GETs unaudited; headers on API only |
| SECURITY_CHECKLIST: scrypt "OWASP-approved" params | ⚠️ N=2¹⁴ below OWASP minimum 2¹⁷ |
| Lost-device runbook relies on admin session revocation / password reset | ❌ Neither endpoint exists |
| `.env.example` `JWT_*_TTL_SECONDS` | ❌ Silently ignored by settings |
| REQUIREMENTS R3.3 marked ⬜ | ⚠️ Implemented — stale the other way |
| Verified TRUE | RLS on every tenant table (40 tables listed); GUCs transaction-local; JWT alg pinned + session re-check; refresh reuse-detection; FEFO with row locks + trigger-maintained stock ledger; expired/recalled stock blocked; lab four-eyes (app-level); invoice items frozen on issue; append-only ledger with double-post guards; one active admission per bed/patient; AES-256-GCM offline store with fresh nonce + Keystore key; outbox `$ref` deferral; 40 Dart tests exist; OpenAPI snapshot in sync |

---

## 6. Feature status matrix (summary — detail in GAP_ANALYSIS.md)

| Module | Status |
|---|---|
| Multi-tenant core, RLS, RBAC, audit | ✅ Complete, with H14–H18 security defects |
| Auth (login/refresh/logout) | ✅ Backend complete · ❌ MFA, reset, lockout missing · ⚠️ web never refreshes |
| Patients / UHID / dedupe / merge | ✅ Works · 🔴 merge loses allergies (H3) |
| Appointments / OPD queue | ✅ Works · ⚠️ races, UTC days, no schedules/calendar |
| Consultation / Rx | ⚠️ Backend solid · 🔴 web dose hard-coded (C1), DB INSERT gap (H1) |
| Billing / receipts / ledger | ⚠️ Works for OPD cash · 🔴 report & concurrency defects (H8–H9) · ❌ GST/tariffs/IPD/insurance |
| Pharmacy | ⚠️ Stock + FEFO solid · 🔴 no sales billing, unlimited dispense · ❌ purchasing/suppliers/returns |
| Laboratory | 🔴 Order items missing (C2) · ❌ ref-range engine, report print, analyzers |
| IPD / nursing | ⚠️ Bed board & ADT work · 🔴 SpO₂ (H2) · ❌ IPD billing, OT, ICU, ER |
| Inventory / expenses / reports | ⚠️ Works · 🔴 refund double-count (H8) |
| Web portal | ⚠️ 14 screens functional · ❌ admin/settings, user mgmt, tests |
| Android / offline | ⚠️ Solid sync core · 🔴 release build broken (C3), offline-after-restart (H22) |
| SaaS subscription | ❌ Not started |
| AI intelligence | ❌ Not started (deliberately excluded so far) |
| DevOps / observability / backups | ❌ Not started beyond compose + CI |

Legend: ✅ complete · ⚠️ partial/incomplete · 🔴 broken (defect) · ❌ missing.

---

## 7. What is strong and should NOT be rebuilt

* Database-first integrity model (RLS + triggers + append-only ledgers + partial unique indexes) — keep and extend.
* Request pipeline in `deps.py`/`db.py` (verified token → session re-check → transaction-local GUCs → RBAC).
* Idempotency service pattern (fix its race, don't replace it).
* FEFO stock allocation and stock ledger.
* Mobile outbox / id-map / encrypted store design.
* Test style: raw-SQL proofs of DB guards, RBAC matrices, cross-tenant 404s.

---

## 8. Remediation status after M7.0 (2026-10-20)

Fixed on the development branch (draft PR #1, not merged). "Test" names the
evidence; details in TEST_RESULTS.md.

| ID | Status | Evidence |
|---|---|---|
| C1 dose hard-coded | ✅ Fixed | web Rx builder requires explicit dose/frequency/duration; E2E prints typed dose |
| C2 lab tests discarded | ✅ Fixed | `lab_order_items` + release-completeness trigger; test_m7_integrity |
| C3 release APK no INTERNET | ✅ Fixed (static) | main manifest + static test; **APK not built** (no Android SDK) |
| H1 signed-Rx INSERT | ✅ Fixed | trigger covers INSERT; raw-SQL proof |
| H2 SpO₂ < 85 | ✅ Fixed | accepted with ≥10-char escalation note; <50 rejected |
| H3 merge loses allergies | ✅ Fixed | allergies unioned, open records re-pointed, allergy gate reads merged records |
| H4 unlimited dispensing | ✅ Fixed | `dispense_quantity` cap across amendment chain; concurrency test |
| H5 Rx print legal details | ✅ Fixed | prescriber name + registration no. (settable via `PATCH /auth/me`), clinic/branch, names from Rx |
| H6 `enc_status` | ✅ Fixed | web uses `enc_status=open` |
| H7 one specimen per order | ✅ Fixed | multiple specimens, re-collection after rejection |
| H8 refund double-count | ✅ Fixed | ledger-based revenue/refunds; refunded ₹1000 → net 0 |
| H9 overpayment races | ✅ Fixed | row locks, sandbox reservation, `amount_paid` CHECK; threaded tests |
| H10 dispenses not billed | ⬜ **Open** | needs MRP + GST sales billing — scheduled in M9 |
| H11 Rx/invoice idempotency | ✅ Fixed | Idempotency-Key honoured; replay tests |
| H12 idempotency race | ✅ Fixed | SAVEPOINT reservation; >100-char keys 422 |
| H13 web idempotency/refund | ✅ Fixed | per-attempt keys, in-flight disable, refund UI; E2E single payment |
| H14 cross-tenant member grab | ✅ Fixed | 409 + invitations accepted with own password; test + E2E |
| H15 X-Request-ID crash | ✅ Fixed | validated/replaced; test |
| H16 no rate limiting | ✅ Fixed | limits + enumeration-safe lockout; tests |
| H17 default JWT secret | ✅ Fixed | refused outside dev; `FIELD_ENCRYPTION_KEY` required |
| H18 PHI reads unaudited | ✅ Fixed | `phi.read` audit, fail-closed |
| H19 web tokens/CSP | ✅ Fixed | httpOnly cookie, memory token, nonce CSP, middleware; E2E asserts |
| H20 mobile sign-out leak | ✅ Fixed | warn + wipe; ops tagged with creator; Dart tests |
| H21 containers | ✅ Fixed | non-root, read-only, `.dockerignore`, migrate job; built + smoke-tested in CI |
| H22 offline after restart | ✅ Fixed (Dart tests) | offline start + PIN lock; device QA pending |
| H23 silent in-memory store | ✅ Fixed (Dart tests) | fail-closed recovery screen, `allowBackup=false` |
| H24 offline patients dropped | ✅ Fixed (Dart tests) | merged pickers, `$ref` only |
| ORM ↔ migration drift | ✅ Fixed | `alembic check` clean, enforced in CI |
| npm postcss advisory | ✅ Fixed | npm override; `npm audit --omit=dev` 0 |

Medium findings: most closed (cross-tenant foreign ids, booking/queue/
barcode races, IST day boundaries, GST on discounted amount, invoice/payment
immutability, DB errors → 409/422, commit-before-response, refresh race,
absolute sessions, trusted proxies, scrypt parameters, audit guard,
correlation ids on all errors, `alembic_version` grants). Still open:
financial-year invoice series (M8), structured lab reference ranges (M10),
mobile i18n (M12), downgrade of seed-data migrations on populated databases,
`style-src 'unsafe-inline'` in the web CSP, mandatory-MFA policy (M7.1).

**This remains a development build.** No production-readiness claim is made:
independent security testing, clinical validation and DPDP/ABDM/CDSCO legal
review are still required (IMPLEMENTATION_PLAN.md, M14).

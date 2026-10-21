# Test Results — M8.1 corrections (2026-10-21)

All of the following were **executed** on 2026-10-21 on the review branch,
after the M8.1 commits, using synthetic data only.

| Suite | Command | Result |
|---|---|---|
| API lint | `ruff check apps/api scripts --select F,E --line-length 100` | ✅ clean |
| API tests | `cd apps/api && pytest --cov=app --cov-fail-under=90` | ✅ **312 passed, 0 failed** (299 before M8.1); coverage **94.24%** (11,786 statements) |
| Migrations | upgrade → downgrade base → upgrade, `alembic check` (fresh database) | ✅ single head `0018`, no drift |
| Web | `npm run typecheck && npm run lint && npm test` | ✅ 0 errors; **156 unit tests passed** (150 before) |
| Web E2E (live API + PostgreSQL + Chromium) | `npx playwright test` | ✅ **28/28** (27 before) |
| Mobile | `flutter analyze && flutter test` | ✅ no issues; **177 passed** (174 before) |
| Android release signing | `flutter build apk --release` without `key.properties` | ✅ **fails** with the signing message, as intended |
| Android APK (demo) | `HMS_ALLOW_DEBUG_SIGNING=1 flutter build apk --release` | ✅ built, 75.7 MB; `apksigner`: CN=Android Debug; **not run on a device** |
| Web runtime without sharp/libvips | `next start` with `node_modules/sharp` and `@img` removed | ✅ pages, icons and manifest served |
| Secret scan | gitleaks, full history | ✅ no leaks, after allow-listing 1 reviewed synthetic test code |
| Docker web image | `docker build` | ⏳ no Docker daemon in this environment; verified by the CI "Docker" job |

### M8.1 regression tests added
| Finding | Tests |
|---|---|
| H1 late payments | expired order paid by webhook; cancelled order paid by checkout; paid stays final; reconciliation asks the provider about expired orders |
| M2 refund processing | lost provider response → `processing` → resume finds the refund by reference (one provider refund, one credit note); 4xx → `failed`; database state machine; a processing refund counts against the refundable amount |
| M1 purchased credits | a pack bought in an earlier month is used now; allowance first, then the pack; refused once both are spent; `/saas/credits` and usage figures |
| M3 PHI audit | `phi.read` rows for scribe, follow-ups, patient comms and the delivery log; settings stay unaudited |
| M4 reminders | a replaced template does not re-send (fails before the fix) |
| L2 licences | Flutter licence page reachable; ML Kit and Material Icons notices registered; web list matches package-lock.json; no GPL/AGPL/SSPL |
| W1 printing | `effectivePaper` unit cases; E2E: saved A5 profile is highlighted, an explicit A4 choice overrides it |
| Low items | `system_scope` restore and abort; durable forged-signature audit; revoked grants; governance `?period=` validation; check-in at another branch; scribe clinician binding; RLS preconditions; percent-encoded token paths; mobile check-in code format and 409 mapping |

---

## Previous run: M7.2 billing, comms v2, setup/QR check-in, AI-1, offline-first Android, device/PWA (2026-10-20)

All of the following were **executed** on the merged branch, using synthetic data only. All but the last two rows were run on 2026-10-20 at commit `0a8d1c7`. The CI row is a different run, on commit `0a2424d`.

| Suite | Command | Result |
|---|---|---|
| API lint | `ruff check apps/api --select F,E --line-length 100` | ✅ clean |
| API tests | `cd apps/api && pytest` | ✅ **299 passed, 0 failed** (200 after M7.1); coverage **94%** (11,683 statements) |
| Migrations | upgrade → downgrade base → upgrade, `alembic check` | ✅ single head `0016`, no drift |
| Backup/restore drill | `scripts/backup_restore_drill.sh` | ✅ **668/668 rows**; RLS, policies, triggers and grants identical |
| Web | `npm run typecheck && npm run lint && npm test` | ✅ 0 errors; **150 unit tests passed** |
| Web E2E (live API + PostgreSQL + Chromium) | `npx playwright test` | ✅ **27/27** |
| Mobile | `flutter analyze && flutter test` | ✅ no issues; **174 passed** |
| Android APK | `flutter build apk --release` (+ `--split-per-abi`) | ✅ built; `apksigner verify` OK. Universal 75.3 MB, armeabi-v7a 23.3 MB, arm64-v8a 27.3 MB. Debug certificate; **not run on a device** |
| Secret scan | gitleaks, full history | ✅ after allow-listing 2 reviewed synthetic test codes |
| GitHub Actions | run 44 (`0a2424d`) | ✅ API, web, E2E, mobile, Docker, contracts, drill, audit and the APK artifact. Gitleaks was red there and is fixed in `181803f` |

### New automated coverage
| Area | Tests | Highlights |
|---|---|---|
| SaaS billing (M7.2) | 18 API + 8 web unit + 1 E2E | see below |
| Comms v2 + follow-ups | 16 API + web unit + 2 E2E | see below |
| Setup wizard / QR check-in / printers | 20 API + web unit (QR encoder checked against segno) + E2E | see below |
| AI-1 | 45 API (engines, API, evaluation) + web unit | see below |
| Android offline v2 | +53 Flutter | see below |
| Device / PWA | 39 web unit + 7 E2E | see below |

SaaS billing (M7.2):
- GST maths, and pricing computed only on the server
- idempotent orders
- forged signatures rejected
- webhook replay, amount mismatch, and 4 concurrent captures → exactly one fulfilment
- failed-payment retry, and a read-only clinic can still pay
- AI credit packs
- refund four-eyes rule (API and database)
- append-only financial records
- tenant RLS
- lifecycle past-due → read-only
- reconciliation
- Razorpay adapter against a fake HTTP server
- live keys and production simulator refused

Comms v2 + follow-ups:
- placeholder whitelist
- opt-out wins
- quiet hours
- quota and spend cap
- reminder idempotency
- append-only delivery log
- follow-up lifecycle
- missed appointments

Setup wizard / QR check-in / printers:
- the QR code is opaque and stored hashed
- single use; duplicate and concurrent confirm return one queue entry
- a code from another clinic gets 404
- expiry
- printer profiles

AI-1:
- forecasts beat the naive baselines, except pharmacy demand (reported)
- no-show risk, AUC 0.686 vs 0.643
- knowledge search hit@3 = 1.00
- 13/13 prompt-injection attempts resisted
- scribe section accuracy 0.842 on held-out transcripts

Android offline v2:
- dependency ordering, id rewrite
- crash recovery with a stable idempotency key
- backoff, poison isolation
- conflicts, revocation wipe
- 5,000-operation run
- QR client matches the real `/checkin/confirm`

Device / PWA:
- shortcut parser
- service worker never caches `/api`
- offline fallback
- 360 px layout
- print sizes

### Defects found and fixed during integration
- **Webhook deadlock.** Async webhook handlers ran blocking database work on the event loop; under concurrent webhooks a lock wait froze the server. The work now runs in the threadpool, and the concurrency test proved the fix.
- **APK had never built.** The Android namespace and application id literally contained `` `in` `` (a Kotlin escape), which AGP 9 rejects. Fixed to `com.adityabionova.smarthms`.
- **Migration drift.** The comms, setup and AI-1 models did not declare their indexes, so `alembic check` would have failed CI. The indexes are now declared.
- **Check-in contract mismatch.** The mobile check-in client targeted a hypothetical `/opd/check-in`; it now calls the real `/checkin/confirm`.
- **Plan usage showed zero sends.** SMS/WhatsApp usage was hard-coded to 0; it now counts real sends from the delivery log.
- **Duplicate printer test pages.** Both workstreams built one; `/print/test` now uses the saved printer profile and `/print/paper-test` is the paper-size sheet.
- **Production settings rejected.** Production would have refused to start because of the simulator default; the provider now defaults to razorpay outside development.

### Not verified (honest gaps)
- **No real devices.** There was no physical Android device, Windows laptop or printer. Device results come from Chromium emulation (docs/DEVICE_COMPATIBILITY.md).
- **Razorpay test mode** was not exercised against Razorpay's servers: there were no test keys, and api.razorpay.com was unreachable from here.
- **No live AI, ASR, OCR, e-mail, SMS or WhatsApp.**
- **Not done yet:** load test, penetration test, clinical validation, legal review.

---

# Test Results — M7.1 tenant administration & SaaS foundation + AI-0 (2026-10-20)

All results **executed** on commit `9bb5c28`+docs (synthetic data only). Same
toolchain as M7.0 below. CI: GitHub Actions runs 30/31 (`9bb5c28`) — **all
jobs green**, including Playwright E2E against a live API seeded by
`scripts/seed_demo.py` and the Docker build + compose smoke.

| Suite | Command | Result |
|---|---|---|
| API lint | `ruff check apps/api --select F,E --line-length 100` | ✅ clean |
| API tests | `cd apps/api && pytest` | ✅ **200 passed, 0 failed** (167 after M7.0) |
| API coverage | `pytest --cov=app` | ✅ **94 %** (6,463 statements) |
| Migrations | `alembic heads` / `alembic check` | ✅ single head `0012`; no drift |
| Backup/restore drill | `scripts/backup_restore_drill.sh` | ✅ 578/578 rows; RLS, policies, triggers, grants identical; tenant-scoped login after restore |
| Web unit | `npm test` (Vitest) | ✅ **69 passed** (43 after M7.0) |
| Web typecheck / lint | `npm run typecheck && npm run lint` | ✅ 0 errors, 0 warnings |
| Web E2E | `npx playwright test` (live web + API + PostgreSQL) | ✅ **15 passed** locally and in CI |
| Mobile | `flutter analyze && flutter test` | ✅ no issues, **121 passed** (91 after M7.0) |
| Copilot golden set | `pytest tests/test_ai_copilot.py` | ✅ 24/24 EN/मराठी/हिंदी questions → correct report + period; 6/6 out-of-scope refused; prompt-injection set refused (**mock parser**, not a model) |

### New API tests
| File | Tests | Covers |
|---|---|---|
| test_m71_tenancy_saas.py | 20 | sign-up starts a trial on the default edition; public plan catalogue has no hard-coded prices; unknown/private plans refused; Rural Clinic features enforced server-side; user + branch limits; expired trial is read-only, not locked out; a tenant cannot change its own subscription even in SQL; role MFA policy blocks until enrolled; org profile + onboarding; export contains only own-tenant data; offboarding request/cancel; support tickets + isolation; plan-change request opens a billing ticket; platform needs super-admin **with MFA** (demo bypass dev-only); platform manages tenants/plans/subscriptions; **platform flag never exposes patient data**; internal support notes hidden from tenant; bed limit via override; overrides kept unless given + status filter |
| test_ai_copilot.py | 12 | AI logs tenant-isolated + append-only; feature gate, opt-in, read-only; live calls consume credits up to the limit; concurrent requests never overspend; live disabled ⇒ zero outbound calls; provider ceiling rejects **before calling**; questions redacted before leaving the server; golden-set accuracy; injection cannot reach beyond the catalogue; answers match report figures; Copilot sees only its own tenant; Indian number formatting |
| test_m7_security.py | +1 | lockout holds across a rate-limit window boundary (sliding-window fix) |

### New E2E (Playwright)
7. Owner edits the organisation profile
8. Branch create, edit and deactivate
9. Subscription page shows the plan, usage and plan comparison
10. Support ticket create, then reply
11. Feature-gated navigation hides Pharmacy for a Rural Clinic tenant
12. A role under the MFA policy is redirected to /settings/security
13. Platform admin: tenants list → open tenant → change plan (seeded super-admin)
14. Owner switches on the Copilot and asks in मराठी → मराठी answer, "mock" label, "How this was computed"
15. The Copilot is not offered on an edition without it

### Defects found and fixed during M7.1 / AI-0
- Rate-limit lockout could be escaped by failures straddling a fixed
  window boundary → sliding-window estimate + conservative lockout count
- Platform PUT of a subscription wiped existing overrides when the field was
  omitted → `None` keeps, `{}` clears (tested)
- Copilot keyword hazards (Hindi "आय" matched "आये", "net" matched
  "internet") → padded tokens; golden set added
- Copilot answered Devanagari questions in English when the UI language was
  sent → answer language now detected from the question
- CI E2E installed only the production lock (no httpx) so the seeder could
  not import TestClient → dev lock in that job (reproduced in clean venvs)

### Not verified (honest gaps)
- **Android APK not built**: this environment's network policy blocks
  `dl.google.com` (Android SDK). Dart tests only; no device QA
- **AI is mock inference only** — no model provider is approved or called;
  the OpenAI-compatible live adapter is tested against a fake server only
- Marathi/Hindi strings need native-speaker review
- Live comms, Razorpay, load/pentest, clinical validation — not done

---

# Test Results — M7.0 security & correctness hardening (2026-10-20)

All results below were **executed**, not estimated. Synthetic data only.
Local: Python 3.13, PostgreSQL 16.15 (app queries as non-owner `hms_app`,
RLS active), Node 22, Flutter 3.47.7, Chromium (Playwright). CI: GitHub
Actions on branch `claude/pensive-albattani-n0zcba` (draft PR #1).

| Suite | Command | Result |
|---|---|---|
| API lint | `ruff check apps/api --select F,E --line-length 100` | ✅ clean |
| API tests | `cd apps/api && pytest` | ✅ **167 passed, 0 failed** (102 before M7.0) |
| API coverage | `pytest --cov=app` | ✅ **94 %** (5,070 statements) |
| Migrations | `alembic upgrade head → downgrade base → upgrade head` | ✅ clean, single head `0010` |
| Migration drift | `alembic check` | ✅ "No new upgrade operations detected" (failed before M7.0) |
| Backup/restore drill | `scripts/backup_restore_drill.sh` | ✅ encrypted backup, tamper + overwrite guards, restore; 348/348 rows, policies, triggers, grants identical |
| Python vulns | `pip-audit --strict` on both lock files | ✅ none (cryptography 50.0.2) |
| Web typecheck / lint | `npm run typecheck && npm run lint` | ✅ 0 errors, 0 warnings |
| Web unit | `npm test` (Vitest) | ✅ **43 passed** |
| Web build | `npm run build` | ✅ |
| Web E2E | `npx playwright test` (live web + API + PostgreSQL) | ✅ **6 passed**, 3 consecutive runs |
| Node vulns | `npm audit --omit=dev` | ✅ 0 vulnerabilities (1 high before M7.0) |
| Mobile | `flutter analyze && flutter test` | ✅ no issues, **91 passed** (40 before; first time executed) |
| Secret scan | gitleaks 8.30.1, full history | ✅ no leaks (1 reviewed false positive allow-listed) |
| Docker | CI: hadolint, build api + web, compose smoke | ✅ images built, migrate → API ready → web proxy (first ever build) |
| GitHub Actions | run 14 (`bccd8a3`) | ✅ all 8 jobs green; e2e job added afterwards |

### API tests by file
| File | Tests | Covers |
|---|---|---|
| test_auth.py | 10 | register/login/refresh rotation + reuse detection, enumeration-safe errors |
| test_tenancy.py | 14 | cross-tenant 404s, forged headers, raw RLS proofs |
| test_rbac_audit.py | 9 | permission matrix, append-only audit |
| test_m2_clinical.py | 15 | patients, dedupe/merge, appointments, OPD queue |
| test_m3_clinical_billing.py | 24 | encounters, signed Rx, billing ledger, GST totals |
| test_m5_pharmacy_lab.py | 17 | FEFO stock, dispensing, lab four-eyes, amendments |
| test_m6_ipd_operations.py | 13 | beds/admissions, nursing, inventory, expenses, reports |
| **test_m7_integrity.py** | 24 | H1–H4, C2/H7, H8, H9 (threaded concurrency), H11–H12, immutability, GST, cross-tenant ids, races, IST |
| **test_m7_security.py** | 38 | MFA (RFC 6238 vector, replay, recovery codes), lockout, rate limits, password reset, sessions, absolute lifetime, org suspension, H14 invitations, PHI-read audit, audit-function guard, commit-before-response, error mapping, comms providers, alembic_version grants |
| test_ops.py | 3 | `/health/ready` incl. DB-down 503 |

### E2E (Playwright, real API — no mocks)
1. Clinical + billing chain: register clinic → login (httpOnly refresh
   cookie, nothing in Web Storage) → patient → consultation → Rx with an
   explicitly typed dose → sign → print shows the dose → invoice → issue →
   double-click pay sends ONE payment → logout redirects; zero CSP violations
2. Web-origin security headers; backend token endpoints not proxied
3. TOTP enrolment in settings → sign-in requires the second factor
4. Invitation e-mail (dev outbox) → /accept-invite → dashboard
5. Forgot password → reset link → sign in with new password
6. Professional registration number saved from settings

### Defects found and fixed during M7.0 integration
- Self-deadlock: MFA verify held `FOR UPDATE` on the user row while the
  failed-attempt audit row (separate connection) needed `KEY SHARE` for its
  FK → `FOR NO KEY UPDATE`
- The new audit-function guard exposed a login path writing an MFA-challenge
  audit event without tenant context → fixed
- MFA disable: consumed recovery code flushed after the bulk delete → 500
- Compose migrate job failed in CI: production guard requires
  `FIELD_ENCRYPTION_KEY` → compose/CI now supply it
- Rx print registration number had no way to be set → `PATCH /auth/me`
- Security page race: late profile load overwrote user input → field
  disabled until loaded
- Restore drill: partial-index predicates re-rendered after restore →
  normalised comparison

### Not verified (honest gaps)
- Android **APK build and device QA** (no Android SDK / devices) — Dart
  tests only
- Live e-mail/SMS/WhatsApp and Razorpay — intentionally not connected
- Load/performance, penetration test, clinical validation — human gates

---

# Test Results — Milestones M1 + M2

Environment: Ubuntu 24.04 VM, Python 3.12, PostgreSQL 16.15 (local instance,
application queries run as non-owner `hms_app` → **RLS active in tests**),
Next.js 15.5.27 / TypeScript 5.9.3. M1: 2026-10-12, M2: 2026-10-13.

## Summary

| Suite | Command | Result |
|---|---|---|
| API lint | `ruff check apps/api --select F,E --line-length 100` | ✅ clean |
| API tests | `cd apps/api && pytest` | ✅ **48 passed, 0 failed** (≈4.8 s; 33 M1 + 15 M2) |
| Web typecheck | `npm run typecheck` | ✅ clean |
| Web production build | `npm run build` | ✅ 7 routes (M2 adds /patients, /appointments, /queue), type+lint pass |
| OpenAPI contract | `scripts/generate-contracts.sh` | ✅ 20 paths, snapshot committed |
| Docker stack | `docker compose up` | ⚠️ **not executed** — no Docker daemon in this workspace; files provided, unverified |
| GitHub Actions CI | push/PR | ⚠️ not run yet (repository not pushed); workflow mirrors the local commands above |

## Coverage by acceptance area

**Authentication (tests/test_auth.py)**
- register → /me round trip; no password/hash leakage in output
- duplicate e-mail 409, duplicate slug 409, weak password 422
- login success; wrong password and unknown e-mail return *identical* 401 bodies
- multi-org login requires `organization_slug` (409 lists slugs)
- refresh rotation; replay of rotated token → 401 + whole family revoked +
  `auth.refresh_reuse_detected` audited; newest token dead afterwards
- logout kills access *and* refresh tokens immediately
- tampered JWT, wrong-key JWT, missing token → 401

**Tenant isolation (tests/test_tenancy.py)** — API level *and* raw SQL
- branch/member/audit listings scoped to caller's tenant
- cross-tenant branch id → 404; forged `X-Org-Id` header ignored
- member created via tenant A lands in A only
- raw `hms_app` connections: no GUC context → **0 rows everywhere**;
  org A context sees only A; org B only B; INSERT with wrong org → RLS
  violation; org INSERT without bootstrap flag → denied; audit INSERT for
  foreign org → denied
- membership visibility requires user context
- audit immutability: UPDATE/DELETE raise `append-only` (table owner) and are
  grant-denied (app role)

**RBAC & audit (tests/test_rbac_audit.py)**
- receptionist: reads OK, branch/member management and audit → 403
- auditor: audit read OK, all writes → 403 (regression test for the M1 seed
  bug found and fixed in migration 0004)
- support role cannot list branches
- owner role ungrantable (403), unknown role 422, duplicate membership 409
- branch codes unique *per tenant* only
- audit trail contains register/login/branch/member actions; failed logins
  recorded with reasons (operator-only visibility)

## Defects found & fixed during M1
1. RLS `RETURNING` rejection during registration → org-id claimed in tenant
   context before insert (code) — regression covered by register tests.
2. Org-NULL security events could not be written through `RETURNING` →
   `insert_audit_event()` SECURITY DEFINER function (migration 0003).
3. **RBAC seed bug:** auditor role had full admin permissions → fixed in
   migration 0004, guarded by `test_auditor_can_read_audit_only`.
4. Test e-mail domains used reserved `.test` TLD rejected by email-validator
   → switched to `example.com` (test-only change).

## Known gaps / not tested yet
- No load/performance measurement (p95 <500 ms goal measured at M7 with
  realistic data).
- No backup/restore drill executed (procedure drafted, DEPLOYMENT.md).
- Docker images built-by-CI not yet verified end-to-end.
- Browser UI flows verified by build/typecheck only — manual sign-in check
  pending in the dev preview; Playwright E2E starts at M2.
- Security: no external penetration test (pre-launch gate).

## Reproduce

```bash
./scripts/setup_local_db.sh
cd apps/api && ../../.venv/bin/python -m pytest -v
```

---

# Milestone M2 — Registration → Appointments → OPD queue (2026-10-13)

## M2 coverage (tests/test_m2_clinical.py, 15 tests)

**Patient registration & supervised dedupe**
- UHID issued per tenant (`P0000001`, `P0000002`…); same demographics in a
  second tenant do NOT collide (tenant-scoped duplicate detection)
- duplicate phone → 409 with `candidates[].matched_on=["phone"]`
  (country-code +91 normalized); duplicate name+dob → same, both flags
  listed when both match
- `allow_duplicates=true` creates the record and is audited
  (`patient.created` with `allow_duplicates: true`)
- search by name/UHID/phone with `{items,total,limit,offset}` pagination
- supervised merge: self-merge 409, merge 200, source retained as
  `merged` + `merged_into_id` (never deleted), source read-only (409 on
  PATCH), hidden from search, double-merge 409

**Appointments**
- create → reschedule → cancel lifecycle; completed/cancelled frozen (409)
- provider double-booking in an overlapping window → 409; free window OK
- ends≤starts → 422
- foreign patient id / foreign branch id → **404** (no FK-error leak)
- date-range + status filters with pagination

**OPD queue**
- tokens 1, 2, … per tenant per day; duplicate active entry → 409
- state machine: waiting→called→in_consultation→completed stamps
  called_at/started_at/completed_at; illegal jumps (waiting→start,
  completed→call) → 409; terminal states frozen
- `Idempotency-Key` replay returns the SAME entry (no duplicate token);
  same key + different payload → 409

**Tenancy / RBAC negative tests**
- cross-tenant patient GET/PATCH → 404; cross-tenant queue call → 404;
  tenant B's board shows 0 of tenant A's entries
- forged `X-Org-Id` on clinical routes ignored (404)
- support role: patient/queue endpoints → 403 (blueprint rule: vendor
  support never sees identifiable patient data)
- doctor: queue read+manage OK, patient registration → 403;
  nurse: patient/appointment read OK, queue.manage → 403
- raw SQL RLS proofs: no GUC context → 0 rows; tenant B context sees 0 of
  tenant A's patients; INSERT with foreign organization_id → denied
  (WITH CHECK)

## Defects found & fixed during M2
1. Phone duplicate detection missed `+91…` / `0…` prefixes → schema-level
   digit normalization before matching (regression-tested via `+91` case).
2. (test-only) `_patient()` defaults collided across tests in the shared
   session DB → unique per-call phone/name sequence.

## M2 known gaps
- Playwright E2E not started (needs headless browser in CI) — starts M3.
- Password reset e-mail pending the e-mail provider decision (M7 gate).
- Translation QA: M2 strings translated programmatically; native-speaker
  review still pending.
- `service_date` uses the UTC day; facility-local day boundary is M3.

---

# M3 results (2026-10-13) — consultation → prescription → billing → receipt

**Suite: 72 passed, 0 failed (7.84 s)** — 33 M1 + 15 M2 + 24 new M3.
Lint `ruff check apps/api --select F,E --line-length 100` clean;
`tsc --noEmit` clean; `next build` green (11 routes); OpenAPI snapshot
regenerated (20 → 42 paths).

## New M3 coverage (`tests/test_m3_clinical_billing.py`, 24 tests)

**Consultation**
- encounter flow: start → vitals → diagnosis → complete; second open
  encounter for the same patient → 409; out-of-range vitals and
  systolic ≤ diastolic → 422; edits after completion → 409 (DB trigger)
- cross-tenant: org B GET/PATCH/complete of org A's encounter → 404;
  org B's list never contains it
- raw RLS: without `app.current_org_id`, `encounters`, `encounter_vitals`,
  `prescriptions`, `invoices`, `payments`, `ledger_entries` all return 0
  rows; with a foreign org context the encounter is invisible

**Prescription (blueprint §R3.5)**
- only `prescription.sign` holders draft/sign (receptionist → 403)
- allergy gate: penicillin-allergic patient + amoxicillin → blocking
  warning; sign without acknowledgement → 409; explicit acknowledgement →
  200 with `allergy_acknowledged=true` (audited)
- duplicate-drug → advisory (`blocking: false`), still signable
- unknown drug id → 422 `Unknown or inactive drug(s)` — no free-text meds
- signed Rx immutability proven with raw SQL as `hms_app`:
  content UPDATE → `immutable`, item UPDATE → `immutable`,
  DELETE → `immutable`, and the row is byte-unchanged afterwards
- amendment: creates signed v2 with `supersedes_id`; old row →
  `superseded` retaining its original items; amending a superseded row →
  409; `prescription.signed` + `prescription.amended` present in audit
- double-sign → 409; empty items → 422

**Billing**
- server-side totals (subtotal 267.50, 12% tax on the pharmacy line →
  8.10); discount > subtotal → 422; per-tenant numbering `INV-000001`
- freeze-on-issue proven raw: invoice `total` UPDATE → `frozen`,
  line-item UPDATE → `immutable`; re-issue → 409
- payment idempotency: same key+payload → replayed payment id, ledger has
  exactly ONE credit, `amount_paid` counted once; same key + different
  payload → 409; amount > balance → 422; paying a draft → 409
- sandbox gateway: pending → confirm → succeeded (double confirm → 409);
  fail → `failed` with no ledger credit and balance unchanged
- refunds: over-refund → 422; partial → `partially_refunded`; full →
  `refunded`; one cent over the remainder → 422; further refund blocked
- ledger append-only proven raw: UPDATE/DELETE → blocked (REVOKE or
  `append-only` trigger); void of an unpaid issued invoice posts
  `charge` + `adjustment` and the receipt balance is 0
- ledger invariant: debits − credits == `total − amount_paid` for a
  charged/paid/refunded invoice
- cross-tenant: B cannot GET the invoice/receipt/ledger, issue it or
  refund its payment (all 404); B's own numbering restarts at 1
- RBAC matrix: receptionist invoices but cannot refund (403); billing role
  refunds but cannot open encounters (403); support/auditor get 403 on
  billing, encounters and prescriptions; doctor reads clinical data but
  cannot invoice (403)

**E2E acceptance chain** — register → token → call → encounter → vitals →
diagnosis → warnings block → acknowledge → sign → complete (queue
auto-completes) → invoice → issue → sandbox pay → confirm → receipt with
`balance_due == 0` and ledger `[charge, payment]`; all nine audit actions
present in the trail.

## Defects found & fixed during M3
1. **`func.case` misuse** — the ledger balance query used `func.case(...)`;
   SQLAlchemy's `case()` is a top-level construct. Fixed at the source.
2. **Raw-SQL test harness** — `set_config(..., is_local=true)` is
   transaction-scoped, so `autocommit=True` silently dropped the RLS GUC
   and the guards "passed" vacuously (UPDATE matched 0 rows). Tests now run
   in one transaction with SAVEPOINT recovery (`_expect_blocked`).
3. **Void receipt 500** — the ledger-consistency invariant assumed
   `total − amount_paid`, but a voided invoice is fully reversed by its
   adjustment entry. Invariant now special-cases `status == "void"`.
4. (test-only) `_draft` built one item from `drugs[0]`, so the E2E never
   actually prescribed the second (allergy-triggering) drug.

## M3 known gaps
- Playwright E2E still not started (headless browser in CI).
- Sandbox gateway is a local simulation; no provider webhook signature
  verification yet — that lands with the real sandbox gateway (M7).
- A5 print size is CSS-ready but not verified on a physical printer.
- Translation QA review by a native speaker still pending.

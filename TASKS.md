# TASKS — milestone plan & live status

Rule: only *completed = tested* items are checked. Simulated, blocked and
pending work is labelled explicitly. (M1 scope approved by the product owner;
implementation sessions continue milestone by milestone.)

## M1 — Foundation + secure multi-tenant core ✅ (2026-10-12)
- [x] Isolated repository `Aditya-BioNova-Smart-HMS` (existing
      website/OncoTrial untouched)
- [x] Monorepo: apps/api, apps/web, packages/contracts, infra/docker, CI
- [x] Postgres schema + Alembic migrations 0001–0004
- [x] RLS tenant isolation (non-owner app role) + append-only audit + RBAC seed
- [x] Auth: register/login/refresh-rotation+reuse-detection/logout/me
- [x] Branches, members, audit endpoints with permission guards
- [x] Web: login + dashboard shell, EN/मराठी/हिंदी switcher, design system
- [x] Tests: 33/33 (auth, RBAC, cross-tenant API + raw RLS proofs)
- [x] Docs: all 11 required files + SBOM/licence register
- [ ] ⏳ Dev-server preview sign-off (browser check by owner)
- [x] Push to customer's GitHub org + first GitHub Actions run (2026-10-17:
      `sambhajithakar/Aditya-BioNova-Smart-HMS`, CI green on M1–M6)

## M2 — Registration → Appointments → OPD queue ✅ (2026-10-13)
- [x] patients (+ supervised duplicate detection/merge), patient profile
- [x] appointments (provider-conflict detection, reschedule/cancel, frozen
      terminal states), tokens, OPD queue state machine, doctor's
      authorized queue view
- [x] Web pages: /patients (search + duplicate-aware registration + profile),
      /appointments (booking + list), /queue (live board with
      call/start/complete/skip)
- [x] i18n: full M2 workflow strings in EN/मराठी/हिंदी
- [x] API pagination ({items,total,limit,offset}) + Idempotency-Key on
      POST /patients and POST /opd/queue; contracts regenerated (20 paths)
- [x] Tests: 48/48 — includes cross-tenant 404s, forged-header test,
      RBAC matrix (support/auditor see NO patient data), raw RLS proofs,
      queue state-machine + idempotency-replay proofs
- [ ] ⏳ Playwright E2E (needs a headless browser in CI; starts M3)
- [ ] ⏳ Password reset e-mail (needs e-mail provider decision — see M7)
- [ ] ⏳ Translation QA review by a native speaker (plan in DEPLOYMENT.md)

## M3 — Consultation → Prescription → Billing → Receipt ✅ (2026-10-13)
- [x] encounters (+ one-open-per-patient guard), range-checked vitals,
      structured diagnosis; completed encounters frozen by DB trigger
- [x] signed Rx with versioned amendments — immutability enforced by DB
      trigger (only legal post-sign change: signed → superseded), audited;
      allergy check blocks signing unless explicitly acknowledged;
      duplicate-drug warnings advisory; items must reference the validated
      `drug_catalog` (45 seeded drugs, no free-text medication entry)
- [x] invoices (server-computed totals, per-tenant INV-000001 numbering,
      freeze-on-issue), receipts, refunds with bounds, append-only ledger
      (trigger + revoked grants + unique partial indexes vs double-posting);
      `Idempotency-Key` on payment creation; sandbox payment gateway spike
      (pending → confirm/fail callbacks)
- [x] printable A4 trilingual Rx + receipt (`/print/rx/[id]`, browser
      print/PDF pipeline); full E2E acceptance chain tested
- [x] Web pages: /consultation (vitals, diagnosis, safety-gated signing),
      /billing (invoice → issue → payment → receipt), print view —
      EN/मराठी/हिंदी strings
- [x] Tests: 72/72 — cross-tenant 404s for every new table, raw RLS
      proofs, signed-Rx/ledger/invoice-freeze raw-SQL immutability proofs,
      RBAC matrix (support/auditor see no clinical or financial data),
      idempotency replay, refund bounds, E2E chain audit assertions
- [ ] ⏳ Playwright E2E (needs a headless browser in CI — still pending)
- [ ] ⏳ Real payment gateway in sandbox (Razorpay/Cashfree/PhonePe
      shortlist) — M7 gate; M3 ships the local sandbox simulation only

## M4 — Android app + offline core (Flutter) ✅ (2026-10-17) — device QA pending
- [x] app shells: ONE binary with two role-aware apps (Staff = register →
      queue → billing; Doctor = queue → Fast Rx), switched by the role the
      server reports on `/auth/me`; secure login against the real
      `POST /auth/login` contract (failures surface the server's `detail`)
- [x] encrypted local storage: the whole offline state is one AES-256-GCM
      sealed file (fresh random nonce per write, `HMS1` as AAD, atomic
      temp-file + rename writes); the AES key and the session tokens live
      in the Android Keystore (`flutter_secure_storage`) — no PHI and no
      token is readable at rest on a lost/stolen device
- [x] offline workflows through the outbox: **registration, OPD queue,
      Fast Rx draft (validated drug catalog only — never free-text
      medication), billing** — every mutation carries a client UUID as the
      server `Idempotency-Key`, and per-workflow dedupe keys collapse a
      double-tap into ONE op (no double-booking, no double invoice)
- [x] local → server id map: a patient registered offline gets a device id;
      dependent ops reference it as `$ref:<local>` and the sync engine
      swaps in the server id before pushing — a still-unresolved reference
      DEFERS the op instead of ever attaching a queue entry/Rx/invoice to
      the wrong patient; `$ref` never reaches the API
- [x] conflict queue (no last-write-wins): 409/412 and policy rejections
      park the op in the sync centre with explicit "Keep local (re-send)" /
      "Discard" resolution; explicit sync states per queued item —
      Saved on device · Pending sync · Syncing… · Synced · Conflict
- [x] restart recovery: outbox, directory cache, id map and Rx drafts are
      persisted on every change and restored by `AppGraph.open()`; signing
      a prescription is online-only (the server's blocking allergy check
      and `prescription.sign` permission must see the patient first)
- [x] signed release build process: `android/app/build.gradle.kts` reads
      `android/key.properties`; `key.properties`, `*.keystore` and `*.jks`
      are git-ignored (verified), so keys can never enter the repo; without
      the file the build falls back to the debug key and says so
- [x] Tests: 40/40 — outbox dedupe/serialize/restore, sync-engine outcome
      matrix, id-map substitution + deferral, encrypted store (round trip,
      NO plaintext at rest, tamper and wrong-key detection, atomic writes),
      end-to-end restart recovery, and the offline registration/queue/Rx/
      billing widget flows (including the role gate and sign-after-sync)
- [ ] ⏳ Device QA: airplane-mode visit, restart recovery and the duplicate
      matrix on entry-level Android hardware — proven in the Dart test
      harness against a fake transport, NOT yet on physical devices
- [ ] ⏳ Notifications, vitals/device capture and the encounter workspace
      on mobile (web already covers them; they reuse this outbox/engine)

## M5 — Pharmacy + Laboratory ✅ (2026-10-16)
- [x] stock in batches with explicit expiry against the validated drug
      catalog (no free-text stock); receiving writes the batch AND its
      opening ledger row; FEFO allocation locks batches in expiry order;
      reason-coded adjustments; expiring/expired/low-stock alert report
- [x] DB-enforced stock integrity: append-only `stock_movements` ledger with
      trigger-maintained on-hand (SUM(in)-SUM(out)), expired stock cannot
      be dispensed, recalled batches frozen, dispense documents immutable
- [x] dispensing against SIGNED prescriptions only (items must be on the
      Rx; OTC against a registered patient); `Idempotency-Key` replay
- [x] lab orders → specimens (unique per-tenant barcode, reject transition)
      → results with the imported → verified → released state machine;
      FOUR-EYES verification (verifier ≠ importer); released results are
      immutable — supersession-only amendments (deferrable FK + partial
      unique index on live results); released/cancelled orders frozen
- [x] RBAC for all 8 M5 permissions (pharmacist & lab_technician roles;
      least privilege for support/auditor); cross-tenant 404s; raw RLS
      proofs for all 7 new tables
- [x] Tests: 89/89 (17 M5) — FEFO split across batches, ledger invariant,
      trigger backstops proven with raw SQL, RBAC matrix, four-eyes,
      amendment supersession, idempotency replay
- [x] Web pages: /pharmacy (expiry/low-stock alerts, receive stock, FEFO
      dispensing against a signed Rx or OTC, batch & movement ledger) and
      /lab (order creation against the test catalog, specimen barcodes,
      import → verify → release → amend worklist) — EN/मराठी/हिंदी
- [x] Live flow verified through the web origin (page's own API path):
      receive → alerts → OTC dispense with branch inference; lab order →
      specimen → import → four-eyes 403 → second-person verify → release

## M6 — IPD + operations ✅ (2026-10-17)
- [x] wards/beds per branch with derived occupancy: physical bed status
      (available/maintenance/blocked) + TWO partial unique indexes so at
      most one active admission per bed and per patient (raw-SQL backstop)
- [x] admissions with `Idempotency-Key` replay; bed/ward transfers through
      an append-only `admission_transfers` ledger; discharge with a
      closed outcome list + mandatory summary; discharged admissions are
      column-frozen and can never be deleted (DB triggers, raw-SQL proofs)
- [x] nursing records: range-checked inpatient vitals (SpO₂ < 85 requires
      an escalation note) + free-text notes — append-only and only legal
      while the admission is open (trigger backstop after discharge)
- [x] inventory: item master, append-only `inventory_movements` ledger with
      trigger-maintained on-hand (negative stock impossible even via raw
      SQL), retired items frozen, low-stock alerts by reorder level
- [x] expenses: frozen amounts/dates, only `recorded → void` (reason
      required) is legal, DELETE blocked, per-category period summary
- [x] reports: `GET /reports/summary` — IPD occupancy + flows, finance
      (succeeded payments − refunds − recorded expenses by category),
      inventory health — all tenant-scoped behind `report.read`
- [x] RBAC: 11 M6 permissions with least-privilege grants (doctor/nurse/
      billing get their slice; support + auditor get ZERO M6 access);
      strict RLS on all 8 new tables (zero-row proof for a foreign tenant)
- [x] Web pages: /ipd (bed board, admit/transfer/discharge/nursing),
      /inventory, /expenses, /reports — shell nav + EN/मराठी/हिंदी strings
- [x] Tests: 102/102 (13 M6) — uniqueness/state-machine/freeze/ledger
      proofs with raw SQL, idempotency replay, RBAC matrix, cross-tenant
      404s for every new endpoint
- [x] Live flow through the web origin: admit → idempotent replay →
      double-book 409 → nursing (+422 out of range) → transfer →
      receive/oversell 409 → expense record + void → discharge + frozen
      409 → report figures
- [ ] ⏳ Inpatient day-rate/tariff billing — out of scope until the owner
      decides the pricing model (outpatient billing already covers invoices)

## M7.0 — Correctness & security hardening ✅ (2026-10-20) — on review branch
Audit: AUDIT_REPORT.md (3 Critical, 24 High). Draft PR
sambhajithakar/Aditya-BioNova-Smart-HMS#1 — not merged.
- [x] Patient safety: editable dose/frequency/duration in web Rx (C1); lab
      order items + release only when complete + multi-specimen (C2, H7);
      signed Rx INSERT guard (H1); SpO₂ < 85 with escalation note (H2);
      merge carries allergies/open records (H3); dispense cap (H4); legal Rx
      print with prescriber registration no. (H5); `enc_status` (H6)
- [x] Money integrity: report revenue/refunds from the ledger (H8); invoice
      row locks + sandbox reservation + `amount_paid` CHECK (H9); dispense
      Idempotency-Key on Rx +
      invoices and race-free idempotency (H11, H12); per-attempt keys, refund
      UI, no double submit in web (H13); invoice/payment/refund immutability;
      GST on post-discount amount
- [x] Security: no cross-tenant member attach + invitations (H14);
      X-Request-ID validation (H15); rate limits + enumeration-safe lockout
      (H16); production secret enforcement (H17); PHI-read audit, fail-closed
      (H18); httpOnly refresh cookie, nonce CSP, middleware guard (H19);
      TOTP MFA + recovery codes; password change/forgot/reset; session list/
      revoke + absolute lifetime; member suspend/role/branch admin;
      trusted-proxy IPs; audit-function guard; commit-before-response
- [x] Android: release INTERNET permission (C3); no backup + fail-closed
      encrypted store (H23); offline start with PIN app lock (H22); per-user
      outbox + safe sign-out (H20); offline patients kept in pickers (H24);
      MFA login, refresh, timeouts, retry/backoff
- [x] Provider-agnostic communications: mock outbox by default; Brevo e-mail,
      DLT SMS (HTTP) and Meta WhatsApp Cloud adapters built + unit-tested,
      hard-suppressed until `COMMS_LIVE_ENABLED` + credentials (owner approval)
- [x] Ops: hash-locked Python deps; Docker non-root/read-only + migrate job;
      encrypted backups + guarded restore + automated drill; `/health/ready`;
      CI with pip-audit, npm audit, gitleaks, alembic drift, Flutter, Docker
      build + compose smoke, drill, web lint/unit, Playwright E2E
- [x] Synthetic demo clinic seeder (`scripts/seed_demo.py`, 9 role accounts)
- [x] Tests: API 164 · web 43 unit + 5 E2E · Flutter 91 — see TEST_RESULTS.md
- [ ] H10 open: dispenses are still valued at cost and not billed — fixed by
      pharmacy sales billing (MRP + GST) in M9
- [ ] ⏳ Device QA of the Android build (no Android SDK/devices in CI yet)
- [ ] ⏳ Independent review of the M7.0 changes (owner/reviewer)
- [x] Mandatory-MFA policy per role/tenant (delivered in M7.1)

## M7.1 — Identity, tenant administration & commercial foundation ✅ (2026-10-20) — on review branch
- [x] Organisation profile, onboarding checklist, branches (address/GSTIN),
      audit-log viewer, data export, offboarding request/cancel
- [x] Role-aware mandatory MFA (`mfa_required_roles`), enforced server-side
- [x] 7 editions as data (Rural Clinic, Clinic Starter, Clinic Plus + AI,
      Multi-Specialty Clinic, Hospital Core, Hospital Advanced, Enterprise);
      34 features, 6 limits; **prices NULL** until the owner sets them
- [x] Trials, read-only mode on lapse, user/branch/bed limits, feature gates
- [x] Platform console for the vendor super-admin (MFA outside dev): tenants,
      subscriptions, overrides, plan editor, support queue; aggregate counts
      only — PHI tables stay tenant-only (raw RLS proof)
- [x] Customer support tickets with internal notes
- [x] Web settings/platform/support pages; Android mr/hi i18n + Rural mode
- [x] `docs/COMMERCIAL_FEATURE_MATRIX.md` generated from the catalogue
- [ ] ⏳ Owner: set plan prices / quotas (catalogue editor in the console)
- [ ] Feature keys exist for modules not built yet (Scribe, agents, OT, ER,
      TPA, ABDM, FHIR …) — switches only, **not features**; see the matrix

## AI-0 — AI gateway governance + Business Copilot ✅ (2026-10-20) — mock inference
- [x] Kill switches, tenant opt-in, data classes C0–C3 + provider ceiling,
      append-only credit ledger with advisory lock, sealed request audit
- [x] Business Copilot (EN/मराठी/हिंदी): whitelisted report catalogue (9),
      figures computed from own records, mock/live label, "how computed"
- [x] Live OpenAI-compatible adapter with redaction — tested with a fake
      server only; **disabled** (`AI_LIVE_ENABLED=false`)
- [x] `docs/AI_ARCHITECTURE.md` (architecture, evaluation, roadmap)
- [ ] ⏳ Owner: approve an AI provider / India-hosted option before any live call
- [ ] Scribe, agents, RAG, document AI, ML forecasting — not built

## M7.2 — Payments & SaaS billing (next)
- [ ] Razorpay **sandbox** subscriptions + webhook signature verification
      (Cashfree adapter as alternative); trial → paid → grace → read-only
- [ ] SaaS invoices (GST), AI credit packs, reseller/partner tracking
- [ ] No live keys or real transactions without owner approval

## Roadmap after M7.0 (owner decisions of 2026-10-20 applied)
Order and acceptance criteria: IMPLEMENTATION_PLAN.md.
- ~~M7.1 Identity & tenant admin~~ ✅ (see above). Still open from the
  original scope: letterhead/masters UI and branch-scoped data access in RLS
- **M7.2 SaaS payments** — Razorpay subscriptions in **sandbox only**
  (Cashfree as alternative), monthly/annual billing, SaaS invoices, AI
  credit packs, reseller tracking (plans/entitlements/limits/console done)
- **M8 Billing 2.0** — tariff master, GST invoice (GSTIN, SAC/HSN,
  CGST/SGST/IGST), FY invoice series, credit notes; Razorpay patient
  payments (sandbox, webhook signature verification)
- **M9 Pharmacy commercial** — MRP/selling price, counter sale + GST bill,
  returns, suppliers/PO/GRN, Schedule H/H1/X registers, pharmacy-only edition
- **M10 Laboratory commercial** — analyte parameters, age/sex reference
  ranges + auto-flagging, critical alerts, signed report PDF, lab billing,
  lab-only edition
- **M11 Hospital depth** — IPD running bill (bed-days, packages, deposits),
  discharge summary, MAR, ER triage/MLC, OT scheduling, TPA tracking
- **M12 Android & offline v2** — background sync, pharmacy/lab/IPD rounds on
  mobile, mr/hi i18n, crash reporting, device QA matrix
- **M13 AI Intelligence** — provider-independent gateway; India-hosted
  options evaluated for sensitive data; **no identifiable patient data to a
  third-party AI service without privacy/contract/regulatory safeguards**
  (de-identification + tenant opt-in + audit). Order: Business Copilot
  (operational analytics, stock/no-show forecasting) → deterministic DDI /
  dose-range checks → AI Clinical Scribe (voice → draft note, EN/मराठी/हिंदी,
  clinician must review/accept) → lab-result summaries; CDSCO SaMD review
- **M14 Integrations & release gates** — ABDM (ABHA/HIP), live comms after
  approval, FHIR export, observability, PITR/off-site backups, staging IaC,
  load test, independent pentest, DPDP review, clinical validation,
  supervised pilot (5–10 sites). **Do not claim production-ready before these
  human gates pass.**

## Backlog / decisions pending owner
- Approve live comms vendors + DLT registration (Brevo vs Amazon SES; SMS
  vendor; Meta WhatsApp business verification) — sandbox/mock until then
- Plan prices and quotas for the seven editions (configured in the platform console, not coded)
- AI provider shortlist + India data-residency decision
- Hosting provider for private staging
- Pilot BP/SpO2 device model for physical validation

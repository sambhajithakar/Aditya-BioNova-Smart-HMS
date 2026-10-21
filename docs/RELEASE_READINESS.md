# Release readiness checklist — Aditya BioNova Smart HMS

Status at 2026-10-21 (after M8.2 and the demo kit), branch `claude/pensive-albattani-n0zcba` (draft PR #1).
**Verdict: NOT production-ready.** The engineering gates below are green on
synthetic data. The human, legal and clinical gates are still open, and they
cannot be closed by writing more code.

Legend: ✅ done and evidenced · 🟡 partial · ⬜ not started / owner action.

## A. Engineering gates (automated, re-run on every push)

| Gate | State | Evidence |
|---|---|---|
| API tests (real PostgreSQL, RLS on) | ✅ 353 passed, 94.41% coverage (CI floor 90%) | TEST_RESULTS.md |
| Migrations 0001→0019: round-trip and `alembic check` drift | ✅ | CI "API" job |
| Backup → tamper guard → restore drill | ✅ 668/668 rows, fingerprints identical | `scripts/backup_restore_drill.sh` |
| Web: typecheck, lint, unit, build | ✅ 159 unit tests | CI "Web" job |
| Web E2E in a live browser (API + DB, no mocks) | ✅ 29/29 | `apps/web/e2e` |
| Flutter analyze + tests | ✅ 237 passed | CI "Mobile" job |
| Android APK builds (release mode, debug certificate by explicit opt-in) | ✅ universal 77.5 MB; release without a key now fails by design | CI `android-apk` artifact; `apksigner verify` |
| PR #1 review findings (H1, M1–M4, L1–L2, A1, W1 and lows) | ✅ fixed with regression tests (M8.1) | CHANGELOG.md |
| M8.2 device capture and review (simulated devices) | ✅ parsers, API, Android, web, E2E | docs/DEVICE_INTEGRATION.md |
| Dependency audit (pip-audit, npm audit), secret scan (gitleaks) | ✅ | CI |
| Docker build and compose smoke | ✅ | CI |
| Synthetic-data demo kit (compose overlay, seed, LAN demo APK) | ✅ in CI (`scripts/demo-up.sh`); the Windows script and phone install are not yet run | docs/DEMO.md, docs/MODULE_STATUS.md |

## B. Product gates (owner decisions)

| Item | State |
|---|---|
| Plan prices, AI credit pack prices, quotas | ⬜ Set them in the platform console; they are NULL by design |
| Razorpay account, TEST keys, then live approval | ⬜ Only the sandbox and the simulator are built; live keys are refused at startup |
| Seller GSTIN and invoice format reviewed by an accountant | ⬜ |
| E-mail, SMS (DLT entity, sender id and templates) and WhatsApp vendors | ⬜ Delivery is mock only |
| AI provider or India-hosted model, DPA and data residency | ⬜ Inference is mock or statistical only |
| Android application id `com.adityabionova.smarthms` (permanent once published) | ⬜ Confirm before any Play release |
| Release signing key, created and held by the owner (never in the repo) | ⬜ |
| Hosting and private staging environment | ⬜ |

## C. Verification gates (independent, human)

| Item | State |
|---|---|
| Real-device QA (entry Android phones, tablets, 4 GB Windows laptops, thermal and A4 printers) | ⬜ Emulation only so far: docs/DEVICE_COMPATIBILITY.md |
| Bluetooth BP monitor / pulse oximeter validation on hardware (M8.2f) | ⬜ No model supported. Purchase awaiting approval: docs/HARDWARE_PURCHASE_RECOMMENDATION.md; protocol in docs/DEVICE_SUPPORT.md |
| CDSCO classification of device-reading capture | ⬜ Consultant review |
| Load and performance test at target scale | ⬜ |
| Independent penetration test and OWASP ASVS L2 review | ⬜ |
| DPDP Act 2023 compliance review (consent, retention, breach process) | ⬜ |
| ABDM certification (only if ABHA/HIP features are sold) | ⬜ Not built |
| CDSCO SaMD classification of the AI features (Scribe and forecasts) | ⬜ |
| Clinical safety validation of the workflows | ⬜ |
| Native-speaker review of the मराठी and हिंदी strings | ⬜ |
| Supervised pilot at 5–10 clinics with synthetic data, then consented real data | ⬜ |

## D. Known engineering gaps (tracked in TASKS.md)

### Offline
- The web app does no offline writes; only the Android app does.
- Android has no background sync while the app is closed.
- The API does not yet have:
  - an Idempotency-Key on `POST /appointments` and `POST /encounters`
  - `If-Match` versioning on `PATCH /patients/{id}`

### AI
- No ASR or OCR models.
- Retrieval is keyword-only (BM25, no embeddings).
- The pattern-based redactor does not remove personal names.

### Billing
- A refund returns money only. It does not take back the subscription period
  or AI credits already granted (product decision, M8.1; documented in
  docs/SAAS_BILLING.md).
- No auto-debit or Razorpay Subscriptions.
- No proration, coupons or reseller commission tracking.
- No e-invoicing (IRN).

### Pharmacy (H10)
- Dispenses are still not billed.

### PDF on Android
- No Devanagari font yet.

### Not built
- Hospital modules: OT, ER, TPA
- ABDM and FHIR

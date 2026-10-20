# Aditya BioNova Smart HMS

Multi-tenant Hospital & Clinic Management System for Indian clinics and
hospitals — offline-first mobile workflows (M4+), trilingual UI (English / मराठी / हिंदी),
role-based access, audit trails and a commercial SaaS business layer.

> **Status: M1–M6 modules + M7.0 hardening + M7.1 tenant administration &
> SaaS foundation + AI-0 Business Copilot (development branch, under
> review).** Clinic OPD, pharmacy, laboratory, IPD and operations modules
> exist with tenant isolation enforced in PostgreSQL; M7.0 added MFA, rate
> limiting, sessions, invitations, PHI-read auditing, backups and a gated CI;
> M7.1 added tenant settings, 7 configurable editions (prices not set),
> entitlements, limits, a vendor platform console and support; AI-0 added a
> governed AI gateway and a trilingual Business Copilot that currently runs
> on **mock (rule-based) inference only — no AI provider is connected**.
> M7.2 added SaaS billing (Razorpay **test mode / local simulator only**),
> communications v2 (**mock delivery**), the setup wizard, QR check-in,
> printer profiles, AI-1 (statistical forecasts + cited knowledge search +
> human-approved agent proposals + scribe drafts), the offline-first Android
> app v2 (demo APK builds) and a responsive/PWA web shell. Release gates:
> [docs/RELEASE_READINESS.md](docs/RELEASE_READINESS.md). See [TASKS.md](TASKS.md),
> [docs/COMMERCIAL_FEATURE_MATRIX.md](docs/COMMERCIAL_FEATURE_MATRIX.md) and
> [docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md).
> This software is **not production-ready, not certified and not clinically
> validated** — independent security, clinical and legal (DPDP/ABDM/CDSCO)
> validation is required first. **Synthetic data only — never enter real
> patient data.**

## Repository layout

```
Aditya-BioNova-Smart-HMS/
├── apps/
│   ├── api/            FastAPI + PostgreSQL backend (versioned /api/v1)
│   │   ├── app/        application code (routers, models, security, RLS context)
│   │   ├── alembic/    database migrations (schema, RLS policies, RBAC seed)
│   │   └── tests/      pytest suite incl. raw PostgreSQL RLS proofs
│   ├── web/            Next.js 15 + TypeScript web portal (EN / मराठी / हिंदी)
│   └── mobile/         Flutter Android app (offline-first, encrypted outbox)
├── packages/contracts/ OpenAPI snapshot (single source of truth; generated)
├── infra/docker/       Dockerfiles + docker-compose (local/staging stack)
├── scripts/            setup_local_db.sh, generate-contracts.sh
├── .github/workflows/  CI (lint, tests against real Postgres, web build, contract check)
└── README, REQUIREMENTS, ARCHITECTURE, DATABASE_SCHEMA, API_DOCUMENTATION,
    TASKS, TEST_RESULTS, SECURITY_CHECKLIST, LICENSES, CHANGELOG, DEPLOYMENT
```

## Quick start (local development)

Prerequisites: Python 3.12+, Node 20+, PostgreSQL 16 (any local instance).

```bash
# 1) PostgreSQL with a superuser "hms" listening on 127.0.0.1:5433
#    (scripts/setup_local_db.sh provisions the app role + databases)
./scripts/setup_local_db.sh

# 2) Backend
python3 -m venv .venv && .venv/bin/pip install -r apps/api/requirements-dev.txt
cp .env.example .env            # then edit JWT_SECRET
cd apps/api && ../../.venv/bin/alembic upgrade head
../../.venv/bin/uvicorn app.main:app --port 8000

# 3) Web (separate terminal)
cd apps/web && npm ci && npm run dev   # http://localhost:3000
```

Or with Docker (see DEPLOYMENT.md):

```bash
export JWT_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
docker compose -f infra/docker/docker-compose.yml up --build
```

## Tests (all run in CI on every push/PR)

```bash
ruff check apps/api --select F,E --line-length 100
cd apps/api && pytest                      # 299 tests: auth/MFA, RBAC, RLS, clinical, billing, SaaS, comms, AI
cd apps/web && npm run lint && npm test && npm run build   # ESLint, 150 unit tests
cd apps/web && npx playwright test         # 27 E2E against a live, seeded API (see playwright.config.ts)
cd apps/mobile && flutter analyze && flutter test          # 174 tests
cd apps/mobile && flutter build apk --release --split-per-abi   # demo APKs (debug certificate)
./scripts/backup_restore_drill.sh          # encrypted backup -> restore -> compare
```

## Demo (synthetic data, local only)

```bash
cd apps/api && python ../../scripts/seed_demo.py   # needs ENVIRONMENT=development
```

Creates three synthetic tenants, each on a different edition, plus the
vendor console account:

| Tenant | Edition | Accounts |
|---|---|---|
| Sunrise Demo Clinic | Clinic Plus + AI | `owner@sunrise-demo.example.com`, `doctor@…`, `nurse@…`, `receptionist@…`, `pharmacist@…`, `labtechnician@…`, `billing@…`, `admin@…`, `auditor@…` |
| BioNova Demo Hospital | Hospital Advanced | `owner@demo-hospital.example.com` + staff roles; wards, beds, an admission |
| Gram Arogya Rural Clinic | Rural Clinic | `owner@rural-demo.example.com`, `doctor@…` |
| Platform console | — | `platform@aditya-bionova.example.com` (super-admin; MFA not enforced in development only) |

Each tenant gets eight invented patients, appointments, a queue, paid
synthetic invoices and (where the edition allows) stock, a lab order and
expenses. The script prints the shared demo password. E-mails
(password reset, invitations) go to the development-only mock outbox at
`GET /api/v1/dev/outbox` — nothing is ever sent.

## Project rules

- **This repository is fully isolated.** The Aditya BioNova corporate website
  and the OncoTrial SMO product are separate systems and must never be
  modified from here.
- **No real patient data** in development, demos, logs or screenshots.
- Third-party licences are tracked in [LICENSES.md](LICENSES.md); no AGPL
  dependencies are permitted in this product.
- Milestone status and next actions live in [TASKS.md](TASKS.md).

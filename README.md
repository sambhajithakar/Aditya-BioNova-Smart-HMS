# Aditya BioNova Smart HMS

Multi-tenant Hospital & Clinic Management System for Indian clinics and
hospitals — offline-first mobile workflows (M4+), trilingual UI (English / मराठी / हिंदी),
role-based access, audit trails and a commercial SaaS business layer.

> **Status: M1–M6 modules + M7.0 security & correctness hardening
> (development branch, under review).** Clinic OPD, pharmacy, laboratory,
> IPD and operations modules exist with tenant isolation enforced in
> PostgreSQL; M7.0 added MFA, rate limiting, session management, staff
> invitations, PHI-read auditing, backups and a fully gated CI. See
> [AUDIT_REPORT.md](AUDIT_REPORT.md) and [TASKS.md](TASKS.md).
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
cd apps/api && pytest                      # 164 tests: auth/MFA, RBAC, RLS, clinical, billing
cd apps/web && npm run lint && npm test && npm run build   # ESLint, 43 unit tests
cd apps/web && npx playwright test         # 5 E2E against a live API (see playwright.config.ts)
cd apps/mobile && flutter analyze && flutter test          # 91 tests
./scripts/backup_restore_drill.sh          # encrypted backup -> restore -> compare
```

## Demo (synthetic data, local only)

```bash
cd apps/api && python ../../scripts/seed_demo.py   # needs ENVIRONMENT=development
```

Creates "Sunrise Demo Clinic" with one account per role
(`owner@sunrise-demo.example.com`, `doctor@…`, `nurse@…`, `receptionist@…`,
`pharmacist@…`, `labtechnician@…`, `billing@…`, `admin@…`, `auditor@…`),
eight invented patients, appointments, a queue, ward/beds with an admission,
stock and a lab order. The script prints the shared demo password. E-mails
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

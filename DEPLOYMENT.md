# Deployment

**Status (M7.0 ops):** development/private-staging procedures below are
implemented. Production deployment still requires the M14 human gates
(security, clinical, legal, pilot). No public deployment has been performed.
Synthetic data only.

## Environments

| Env | Data | Controls |
|---|---|---|
| Local dev | Synthetic only | No public access; `.env` git-ignored |
| Staging | Synthetic/de-identified | Production-like security; CI runs there first |
| Pilot production | Authorized real records **only after gates** | Tenant isolation, MFA*, backups, audit, DPA |
| Commercial production | Contracted records | SLAs, DR, monitoring, audits |

\* MFA is pending (M7.1) — a hard pre-pilot requirement.

## Required environment variables

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | API | **non-owner** `hms_app` role → RLS enforced |
| `MIGRATION_DATABASE_URL` | Alembic / `migrate` job | table-owner `hms` role; release step only |
| `JWT_SECRET` | API | ≥32 random chars; `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ACCESS_TOKEN_TTL_SECONDS` / `REFRESH_TOKEN_TTL_SECONDS` | API | defaults 1800 / 1209600 (the older `JWT_*_TTL_SECONDS` names are **not** read) |
| `CORS_ORIGINS` | API | JSON list of exact origins |
| `ENVIRONMENT` | API | development / staging / production |
| `FORWARDED_ALLOW_IPS` | API (uvicorn) | address/CIDR of the reverse proxy; default `127.0.0.1` |
| `WEB_CONCURRENCY` | API (uvicorn) | worker processes; image default 2 |
| `API_ORIGIN` | Web — **build time** | baked into the image, see "Web image and API_ORIGIN" |
| `HMS_PG_PASSWORD`, `HMS_APP_PASSWORD` | Postgres/bootstrap | **required** by compose (no defaults); use hex/URL-safe values |

Never commit `.env` or secrets. In production put secrets in the platform's
secret store. Compose refuses to start when a secret is missing
(`${VAR:?}`); a template is in `infra/docker/compose.env.example`.

## Path A — Docker Compose (local / private staging)

```bash
cp infra/docker/compose.env.example infra/docker/.env   # fill every secret (git-ignored)
docker compose -f infra/docker/docker-compose.yml --env-file infra/docker/.env up --build
# API  http://127.0.0.1:8000  (docs at /api/v1/docs; ready probe /api/v1/health/ready)
# Web  http://127.0.0.1:3000
```

Order of start-up: `postgres` (healthy) → `migrate` (one-shot
`alembic upgrade head`, must exit 0) → `api` (healthy) → `web`.
First Postgres boot provisions `hms_app` via `infra/docker/postgres-init/`.

### Container hardening (M7.0)

| Control | API image | Web image | Compose |
|---|---|---|---|
| Base image pinned by tag **and** digest | `python:3.12.15-slim@sha256:a6e3…` | `node:22.23.3-alpine@sha256:0a71…` | `postgres:16.15-alpine@sha256:7218…` |
| Reproducible deps | `pip install --require-hashes --no-deps -r requirements.lock` | `npm ci` from `package-lock.json`; runtime has prod deps only | — |
| Non-root | uid/gid `10001` | `node` (uid 1000) | `no-new-privileges`, `cap_drop: [ALL]` |
| Read-only root FS | yes (`/tmp` tmpfs) | yes (`/tmp`, `.next/cache`, `.next/server/route-cache` tmpfs — the only paths `next start` writes, verified) | `read_only: true` |
| HEALTHCHECK | `GET /api/v1/health` (liveness) | `GET /login` | `depends_on: service_healthy` |
| PID 1 / signals | exec-form `uvicorn` | exec-form `node …/next start` (no npm wrapper) | — |
| Proxy headers | `--proxy-headers`, trusted IPs from `FORWARDED_ALLOW_IPS` | — | — |
| Secrets in image | none; root `.dockerignore` excludes `.git`, `**/.env*`, keys, dumps, caches, host `node_modules`/`.next`, tests, mobile | same | all secrets from env, required |
| Network exposure | — | — | every published port bound to `127.0.0.1` |

### Migration job

The API container **never** changes the schema. Migrations run as a
separate, one-shot release step with the owner role:

* compose: service `migrate` (`command: ["alembic", "upgrade", "head"]`),
  and `api` waits for `condition: service_completed_successfully`;
* other platforms: run the API image once with
  `alembic upgrade head` and `MIGRATION_DATABASE_URL` before rolling out the
  new API version (e.g. a Kubernetes Job / pre-deploy hook). Never run it
  from every replica.

### Health probes

* `GET /api/v1/health` — liveness; never touches the DB (a DB outage must not
  restart healthy API containers).
* `GET /api/v1/health/ready` — readiness; `SELECT 1` via the runtime role;
  `200 {"status":"ready"}` or `503 {"status":"unavailable"}` with no
  host/user/driver details. Point load balancers at this one.

### Web image and API_ORIGIN (audit finding I1)

`apps/web/next.config.mjs` builds the `/api/v1/*` rewrite destination from
`process.env.API_ORIGIN`, and `next build` serialises it into
`.next/routes-manifest.json`. **A runtime `API_ORIGIN` has no effect.**
Fix (no app-code change): `API_ORIGIN` is a build `ARG` in
`infra/docker/web.Dockerfile` (default `http://api:8000`), passed by compose
as `build.args.API_ORIGIN` (`WEB_API_ORIGIN` override), and the build fails if
the value is not present in the routes manifest. Build one web image per API
origin. Verified locally without Docker by reproducing the image stages:
built with `API_ORIGIN=http://127.0.0.1:8911`, started with a *runtime*
`API_ORIGIN=http://127.0.0.1:1` → `/api/v1/health/ready` through the web
server still answered from the build-time origin (200).

### Verification status of the containers

* ✅ `hadolint 2.12.0`: both Dockerfiles clean. `docker compose config`:
  valid; refuses to render without the three secrets.
* ✅ API image layout reproduced outside Docker (only `app/`, `alembic/`,
  `alembic.ini` + lock-installed venv, same uvicorn argv): migrate job,
  `/health` 200, `/health/ready` 200, 2 workers, no `Server` header,
  HEALTHCHECK command exit 0.
* ⬜ **Images were not built in the M7.0 workspace** (no Docker daemon
  available). The CI job `docker` builds both images, runs the compose stack
  and smoke-tests it (migrate exit 0, API ready, web → API proxy, non-root
  users) — first green run pending.

## Path B — bare services (what local verification uses)

1. PostgreSQL 16 with superuser `hms` on `127.0.0.1:5433`
   (local non-root instance documented in README).
2. `./scripts/setup_local_db.sh` → role + `hms_dev`/`hms_test`.
3. `pip install --require-hashes --no-deps -r apps/api/requirements-dev.lock`
4. `cd apps/api && alembic upgrade head`
5. `uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers`
6. `cd apps/web && npm ci && API_ORIGIN=http://127.0.0.1:8000 npm run build && npm run start`

Reverse proxy (nginx/Caddy) terminates TLS; API binds loopback only;
Web proxy path `/api/v1/*` → API (`API_ORIGIN` at **build** time).

## Python dependency locking

`apps/api/requirements.txt` / `requirements-dev.txt` hold version ranges;
`requirements.lock` / `requirements-dev.lock` are generated with
`scripts/lock-api-deps.sh` (pip-tools, `--generate-hashes`, Python 3.12) and
are what CI and the API image install (`--require-hashes`). Re-lock after any
range change or to pick up a security fix
(`scripts/lock-api-deps.sh --upgrade-package <name>`), then commit both files.
CI runs `pip-audit --strict` on both locks.

## Release procedure

1. PR → CI green: lint, tests vs real Postgres, `alembic check`, web build,
   contract diff, Flutter analyze/test, pip-audit/npm audit, gitleaks,
   Docker build + smoke, backup/restore drill.
2. Take a backup (`scripts/backup.sh`) immediately before migrating.
3. Run the **migrate job** (separate step) with a tested rollback
   (`alembic downgrade -1`); keep one-version schema compatibility.
4. Deploy API → web; smoke: `/api/v1/health/ready`, login, one read endpoint.
5. Tag `X.Y.Z`; update CHANGELOG; archive SBOM output (LICENSES.md).

## Backups & restore

Scripts (all synthetic-data tested; secrets are never echoed or put on argv):

```bash
# Backup (owner role; libpq env; encrypted)
PGHOST=… PGPORT=… PGUSER=hms PGDATABASE=hms_dev \
BACKUP_DIR=/srv/hms-backups BACKUP_RETENTION_DAYS=14 \
BACKUP_AGE_RECIPIENT=age1…            # or BACKUP_PASSPHRASE=… (gpg AES256)
  scripts/backup.sh
# -> /srv/hms-backups/hms_dev_20261020T020000Z.dump.age + .sha256, old dumps pruned

# Restore into a NEW database (refuses a non-empty target unless --force)
BACKUP_AGE_IDENTITY=/secure/age-key.txt \
  scripts/restore.sh /srv/hms-backups/hms_dev_20261020T020000Z.dump.age hms_restore
```

* `backup.sh`: `pg_dump -Fc` as the table owner, UTC timestamp, optional
  `age` (public-key — preferred: the backup host never holds the decryption
  key) or `gpg --symmetric --cipher-algo AES256` (passphrase via fd),
  `sha256` file, retention pruning, `umask 077`, warns when unencrypted.
* `restore.sh`: mandatory checksum check, decryption, archive sanity check
  (`pg_restore --list`), create target if missing, refuse non-empty target
  without `--force`, `pg_restore --exit-on-error --single-transaction`.
* Roles are cluster-global and not in a dump: `hms` and `hms_app` must exist
  on the target cluster first (`scripts/setup_local_db.sh` / postgres-init).
* Schedule (proposal): nightly `backup.sh` via cron/systemd timer on a host
  that is not the DB host; copy the encrypted dump + `.sha256` off-site
  (different provider/region, object-lock/immutability for ≥30 days).
  Keep the age identity offline (two custodians).

### Point-in-time recovery (production recommendation — not implemented)

Logical dumps alone give RPO = time since the last dump. For production:

* enable WAL archiving (`wal_level=replica`, `archive_mode=on`,
  `archive_command`/`archive_library` via **pgBackRest** or **WAL-G**) to
  encrypted off-site object storage, plus a weekly physical base backup;
* restore by base backup + WAL replay to a target time
  (`recovery_target_time`), e.g. "just before the bad migration";
* or use a managed PostgreSQL with PITR enabled (verify region/data
  residency for DPDP);
* keep the nightly logical dump as an independent second copy
  (tenant-level export, version-portable).

### RPO / RTO targets (proposals for the product owner)

| Stage | RPO | RTO | Mechanism |
|---|---|---|---|
| Pilot (≤10 sites) | ≤ 15 min | ≤ 4 h | WAL archiving/PITR + nightly encrypted logical dump |
| Commercial | ≤ 5 min | ≤ 1 h | PITR + streaming replica in a second zone; quarterly restore drill |
| Interim (logical dumps only, today) | 24 h | 8 h | nightly `backup.sh` (Blueprint §5 starting point) |

### Restore drill — automated, executed

`scripts/backup_restore_drill.sh` (also CI job `backup-restore-drill`):
scratch DB → `alembic upgrade head` → synthetic tenants/patients created
**through the API as `hms_app`** → encrypted backup → negative checks
(tampered dump rejected, restore over non-empty DB refused) → restore into a
second DB → fingerprint comparison (row count of **every** table, RLS flags,
policies, triggers, functions, grants, default privileges, indexes,
constraints, sequences, alembic revision) → functional checks on the restored
DB (RLS hides rows without tenant context, append-only audit trigger fires,
owner login + tenant-scoped list via API). Any mismatch → non-zero exit.

Result of the local run on 2026-10-20 (PostgreSQL 16, migrations at `0008`):

```
section                source restored
row_counts                 41       41
rls_enabled                41       41
policies                   43       43
triggers                   22       22
functions                  20       20
table_grants               46       46
default_privileges          1        1
indexes                   119      119
constraints               270      270
sequences                   5        5
alembic_version             1        1
total rows                345      345
ok: fingerprints identical
ok: RLS — hms_app sees 0 patients without tenant context
ok: audit_events append-only trigger rejects UPDATE
drill_seed: owner login + tenant-scoped patient list OK for 2 tenants
DRILL PASSED
```

Note: CHECK constraints written as `col IN (...)` are deparsed with
different (equivalent) cast placement after a dump/restore round trip; the
drill compares a cast/parenthesis-normalised form of constraint definitions.
Also exercised manually: `age` encryption + restore, `--force` replace of a
non-empty DB, retention pruning, passphrase never printed.

## Monitoring & operations (backlog)

Structured JSON logs without PHI (correlation id only) → central log store;
uptime/latency alerts on `/api/v1/health/ready` (p95 <500 ms read target);
error tracking with source maps disabled publicly; incident runbook;
patch cadence for base images (bump tag + digest) and dependencies
(re-lock + pip-audit/npm audit in CI).

## Still not done (M7.0 ops)

* Docker images never built/run in this workspace (no daemon) — CI `docker`
  job is the first real build.
* No reverse proxy/TLS config in the repo; no Trivy image scan, SBOM
  generation, CodeQL, Dependabot/Renovate, or scheduled CI.
* No PITR/WAL archiving, no off-site copy automation, no backup monitoring.
* Web runtime ships full production `node_modules` (no `output: "standalone"`
  — would need an app-code change).
* `npm audit --omit=dev --audit-level=high` currently **fails** on the
  postcss advisory bundled with Next 15 (fix = Next upgrade, web owner);
  `alembic check` currently **fails** on ORM/migration drift (being fixed
  separately). Both CI gates are in place and expected red until then.
* No monitoring/alerting, no resource limits/log rotation in compose,
  no staging/prod IaC; mobile release pipeline (signing) not in CI.

## Rollback

- Application: redeploy previous image/tag (config unchanged).
- Database: `alembic downgrade <rev>` tested before any production
  migration; never auto-downgrade. Last resort: restore the pre-migration
  backup into a new DB and repoint `DATABASE_URL`.
- Kill switch: suspend tenant (`organizations.status='suspended'`) → all
  sessions reject on next request without deleting data.

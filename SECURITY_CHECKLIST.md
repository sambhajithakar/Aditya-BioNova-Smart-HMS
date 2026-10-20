# Security Checklist — through M7.0 (OWASP ASVS 5.0-oriented)

**Legend:** ✅ implemented + tested · 🟡 partial/documented limitation · ⬜ pending.
This checklist is *engineering self-assessment only*. Independent security
review, DPDP/ABDM/CDSCO legal assessment and clinical safety review are
**required before any real patient data** — no compliance claim is made here.

## Authentication
- ✅ scrypt password hashing at OWASP parameters (N=2^15, r=8, p=3; per-password
  salt; constant-time compare); legacy N=2^14 hashes upgraded transparently at
  the next login (M7.0, tested)
- ✅ Minimum 10-char passwords (length-only policy per ASVS)
- ✅ Generic 401 for unknown e-mail *and* wrong password; timing equalised
  with dummy hash (tested). Residual: `POST /auth/register` still answers 409
  for a registered e-mail (rate-limited per IP); an admin creating a member
  with an existing e-mail gets 409 (authenticated, audited, rate-limited)
- ✅ Short-lived access JWT (30 min) + rotating refresh tokens (14 d),
  SHA-256 stored, **reuse detection revokes the whole session family** (tested)
- ✅ Logout/revocation effective immediately (session row re-checked per request — tested)
- ✅ JWT signature/issuer/expiry/type validated; wrong-key and tampered tokens 401 (tested)
- ✅ TOTP MFA (RFC 6238; seeds AES-256-GCM encrypted at rest with
  `FIELD_ENCRYPTION_KEY`; ±1 step drift; replay of a used step refused;
  10 single-use recovery codes stored as SHA-256) — login returns an MFA
  challenge (5-min token, attempt-limited) instead of tokens (M7.0, tested +
  browser E2E)
- ✅ Password change (revokes other sessions), forgot/reset (always 202;
  single-use 30-min token; all sessions revoked on reset) (M7.0, tested + E2E)
- ✅ Rate limits (PostgreSQL-backed, shared across instances, hashed keys) on
  login, MFA, register, refresh, password reset, invitation accept; 429 +
  Retry-After. Account lockout after 5 failures/15 min keyed by the submitted
  e-mail — identical for unknown e-mails, so lockout reveals nothing (tested)
- 🟡 MFA is available to every user but not yet *mandatory* per role/tenant
  (policy switch planned with the M7.1 admin settings)

## Authorization & tenancy
- ✅ RBAC permission checks server-side per route (tested incl. negative 403s)
- ✅ Tenant identity only from verified token; forged `X-Org-Id` ignored (tested)
- ✅ PostgreSQL RLS as non-owner role — cross-tenant read/write denied at DB
  layer (raw-SQL proofs: no context → 0 rows; wrong-org INSERT → denied)
- ✅ Cross-tenant identifier manipulation → 404 (IDOR/BOLA, tested)
- ✅ `owner` role cannot be granted through the API (tested)
- 🟡 `users`/`auth_sessions` have no RLS (auth bootstrap) — mitigations in
  ARCHITECTURE.md; no endpoint exposes password hashes (tested)
- ✅ An administrator can no longer attach an *existing* account (possibly
  another tenant's) as a member (H14); existing accounts join only by
  accepting an e-mailed invitation with their own password (M7.0, tested)
- ✅ Member administration: role change, suspend (revokes sessions at once),
  branch, per-member session revocation; owner protected; self-suspend refused
- ✅ Client-supplied foreign ids (branch/appointment/encounter/provider) are
  resolved through RLS and rejected when not visible (M7.0, tested)
- ✅ Organization/membership suspension enforced on every request (M7.0)
- ✅ PHI reads audited: every successful GET on patient/clinical/financial
  resources writes `phi.read` (path only — never query strings), fail-closed
  (no audit row → 500, no data) (H18, M7.0, tested)
- ✅ `insert_audit_event` tenancy guard fixed (an empty org context no longer
  bypasses it — migration 0009, raw-SQL proof)
- ⬜ Purpose-of-use capture and periodic access reviews (later phases)

## Sessions & transport
- ✅ Session-bound tokens; server-side revocation; expiry columns indexed
- ✅ Absolute session lifetime (default 30 d) that refresh rotation cannot
  extend; refresh rotation row-locked (no double rotation); users can list
  and revoke their sessions (M7.0, tested)
- ✅ `X-Forwarded-For` honoured only from configured trusted proxies; client
  `X-Request-ID` validated (≤64 safe chars) — an oversized value previously
  crashed every audited write (H15, M7.0, tested)
- ✅ CORS restricted to configured origins; security headers
  (nosniff, DENY framing, no-referrer, no-store) on every response
- ✅ Secrets only via environment/.env (git-ignored); `.env.example` carries
  placeholders. Outside development/test the API refuses to start with a
  default/short (<32) JWT secret or without `FIELD_ENCRYPTION_KEY` (H17, M7.0,
  tested); compose requires every secret explicitly
- ✅ Secret scanning (gitleaks, pinned + checksum-verified) in CI; the only
  finding (public RFC 6238 test vector) is fingerprint-allowlisted
- 🟡 TLS enforced at ingress in deployment — local dev is plaintext loopback
- ✅ Web: refresh token only in an httpOnly, SameSite=Strict, path-scoped
  cookie set by Next.js route handlers; access token kept in memory and
  silently refreshed; nothing in Web Storage (asserted by Playwright E2E);
  `middleware.ts` guards protected routes (H19, M7.0)
- ✅ Web origin headers: per-request nonce CSP (`strict-dynamic`, no inline
  scripts, `frame-ancestors 'none'`), nosniff, Referrer-Policy,
  Permissions-Policy, COOP/CORP, HSTS in production; zero CSP violations in
  E2E. Residual: `style-src 'unsafe-inline'` (React style attributes)

## Data protection
- ✅ No PHI in code, logs or error bodies; correlation ids only
- ✅ Synthetic test data only (tests generate their own clinics)
- ✅ Audit trail append-only (policy + grants + trigger; tested for owner and app role)
- ✅ Parameterized SQL everywhere (SQLAlchemy core/text params)
- 🟡 Encryption at rest: delegated to disk/volume encryption at deployment;
  the M4 mobile offline store is AES-256-GCM sealed with the key in the
  Android Keystore (tested: no plaintext at rest, tamper/wrong-key
  detection). SQLCipher when the app grows a local SQL store.
- ✅ Encrypted, checksummed backups (`scripts/backup.sh`: pg_dump -Fc + age/gpg,
  sha256, retention) and guarded restore (`scripts/restore.sh`: checksum
  verified, refuses non-empty target without --force) — executed 2026-10-20
- ✅ Automated restore drill executed locally (synthetic data): every table's
  row count, RLS flags/policies, triggers, grants identical after restore;
  RLS + append-only audit + login re-verified on the restored DB
  (`scripts/backup_restore_drill.sh`, result in DEPLOYMENT.md); also green
  in GitHub Actions (run 14, 2026-10-20) on the full 0001–0010 schema
- 🟡 Backup scheduling, off-site immutable copies, WAL archiving/PITR and
  backup monitoring — documented as production recommendations, not built
- ✅ Rate limiting (see Authentication)
- ⬜ Secrets manager and key rotation (`FIELD_ENCRYPTION_KEY` rotation needs a
  re-encryption job — planned)

## Application hardening
- ✅ Input validation via Pydantic (`extra=forbid`, strict types, slug/code regexes)
- ✅ Generic 500 handler (no stack traces to clients; logged server-side)
- ✅ Ruff lint + 164 API tests (incl. failure paths, raw-SQL guard proofs,
  concurrency tests), web ESLint + 43 unit + 5 Playwright E2E, 91 Flutter
  tests — all CI gates (M7.0)
- ✅ Dependency licence register + SBOM (LICENSES.md); **no AGPL dependencies**
- ✅ Python dependencies fully pinned with sha256 hashes
  (`apps/api/requirements*.lock`); CI and the API image install with
  `--require-hashes`; lock install + 105 tests verified in a fresh venv
- ✅ `pip-audit --strict` run on both lock files (2026-10-20): no known
  vulnerabilities (after moving to cryptography 50.0.2 / pytest 9.1.1)
- ✅ `npm audit --omit=dev` (web): 0 vulnerabilities after pinning patched
  postcss via npm `overrides` (Next stays 15.5; Next 16 upgrade deferred
  pending a compatibility assessment — owner decision). Dev-only `braces`
  advisory via eslint-config-next has no fix yet
- ✅ Secret scan: gitleaks 8.30.1 over full git history — no leaks (one
  reviewed false positive allow-listed by fingerprint)
- ✅ CI (SHA-pinned actions, `permissions: contents: read`): pip-audit,
  npm audit, gitleaks, `alembic check`, Flutter, Docker build + compose smoke
  and the restore drill — all green on GitHub Actions run 14 (2026-10-20)
- ✅ Containers: non-root, read-only rootfs, cap_drop ALL, healthchecks,
  digest-pinned bases, `.dockerignore`, loopback-only ports, required
  secrets — hadolint clean; built and smoke-tested in CI (run 14)
- ⬜ Container image scanning (Trivy), SBOM generation, CodeQL/SAST
- ⬜ OWASP ASVS 5.0 full pass + independent penetration test (pre-launch gate)

## Clinical safety boundaries
- ✅ No clinical decision support, no AI prescribing in this codebase
- ✅ Signed prescriptions immutable incl. item INSERT (H1 closed in M7.0,
  raw-SQL proof); versioned amendments; only authorised roles sign; the
  doctor sets every dose/frequency/duration explicitly — no defaults (C1)
- ✅ Allergy gate also covers allergies of merged-away patient records (H3)
- ✅ Dispensing capped by the prescribed quantity across the amendment chain
  (H4); lab orders record ordered tests and cannot be released incomplete
  (C2); critical SpO₂ values recordable with a mandatory escalation note (H2)
- ⬜ Independent clinical safety validation (human gate before real use)

## Incident & operations
- ⬜ Incident response plan, patch management, support escalation (M7–M9)
- ✅ Lost-device response runbook (M4) — see below

## Lost-device response (M4 runbook)
1. **Contain**: the user (or an admin) calls `POST /auth/logout` from any
   device — it revokes that session's tokens. Refresh tokens are
   single-use with reuse detection, so replaying a stolen token revokes the
   whole family; a lost device cannot mint new tokens.
2. **Verify**: an owner/admin reviews `GET /audit-events` for the device's
   user — every PHI read/write is recorded with actor, resource, IP and
   correlation id.
3. **Re-issue**: reset the user's password (owner/admin, M7 will automate
   the e-mail path); the next login issues fresh tokens.
4. **Data at rest on the device**: the offline store is AES-256-GCM sealed
   and the key lives in the Android Keystore — extraction of the app
   sandbox yields neither PHI nor tokens. Nothing to wipe beyond the normal
   remote-wipe step of the MDM/Google account.
5. **Record** the incident (date, user, device, containment steps) in the
   clinic's register; support escalates to security review if audit shows
   data access after the loss.

Not built yet: a per-device "kill switch" beyond token revocation, and MDM
integration — labelled as open, not claimed.

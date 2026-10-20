# Security / Auth / Tenancy / RLS / RBAC / Audit / Migrations audit

Repo: `/home/user/Aditya-BioNova-Smart-HMS` (read-only review; no tests run).
Paths below are relative to `apps/api/` unless they start with a top-level folder.
Installed runtime checked at `/var/tmp/hms-venv`: fastapi 0.151.0, starlette 1.9.0, pyjwt 2.15.1, sqlalchemy 2.1.5.

---

## 1. Verified working (with evidence)

| Area | Evidence |
|---|---|
| GUCs are set transaction-locally (`set_config(..., true)` is equivalent to `SET LOCAL`), so they do not leak across pooled connections | `app/db.py:60-71` |
| Tenant context comes from the verified JWT plus the server-side session row, not from headers | `app/deps.py:70-97` (session row must match `sub`/`org`, not be revoked or expired) |
| The JWT algorithm is pinned on decode (`algorithms=[settings.jwt_algorithm]`); `iss` is validated; `exp/iat/sub/sid/org/typ` are required; `typ=access` is checked | `app/security.py:95-106` |
| Access tokens die on logout or rotation because the session row is re-checked on every request | `app/deps.py:79-87`, `app/routers/auth.py:372-391` |
| Refresh tokens are opaque (`token_urlsafe(48)`) and only their SHA-256 is stored. Rotation keeps a family; reuse revokes the family and is audited in its own transaction | `app/security.py:110-117`, `app/routers/auth.py:308-369`, `88-102` |
| Passwords use scrypt with a per-password salt and a constant-time compare. Unknown e-mail runs a dummy verify for timing equalisation | `app/security.py:32-75`, `app/routers/auth.py:218-237` |
| Login returns a generic 401 for both unknown e-mail and wrong password | `app/routers/auth.py:46-48, 219-237` |
| The runtime role is the non-owner `hms_app` (RLS applies); migrations use a separate URL | `app/config.py:24-26`, `alembic/env.py:29,40`, `tests/conftest.py:23-28` |
| Every tenant table created in migrations has `ENABLE ROW LEVEL SECURITY` plus a USING + WITH CHECK `organization_id = GUC_ORG` policy (see the table inventory in section 2.1) | `0001:197-266`, `0005:205-211`, `0006:570-580`, `0007:439-449`, `0008:426-432` |
| `audit_events` is append-only through three layers: no UPDATE/DELETE policy, revoked grants, and a BEFORE UPDATE/DELETE trigger | `0001:188, 259-281` |
| Reference tables are read-only for `hms_app` | `0001:189-193`; `drug_catalog` `0006:728-729`; `lab_test_catalog` `0007:686-687` |
| Append-only ledgers have UPDATE/DELETE revoked plus triggers | `0006:717-727`; `0007:517-535, 688-690`; `0008:525-530, 610, 652-654` |
| The `owner` role cannot be granted through the API, and assignable roles are allow-listed | `app/routers/members.py:18-61` |
| The auditor was corrected to read-only | `0004:490-508` |
| Every permission used by `require_permission(...)` in routers (39 keys) is seeded by migrations 0002/0005/0006/0007/0008. No permission is used in code without being seeded | Cross-check of `grep require_permission app/routers` against the seed lists |
| The generic 500 handler hides stack traces and returns a correlation id | `app/main.py:73-80` |
| Security headers are set: nosniff, X-Frame-Options DENY, no-referrer, no-store | `app/main.py:67-70` |
| CORS uses explicit origins (no wildcard by default) | `app/main.py:52-59`, `app/config.py:34` |
| Idempotency keys are scoped per tenant (`UNIQUE(organization_id, idempotency_key)`), store status and body, and are checked against the endpoint and a payload hash (409 on mismatch) | `0005:185-203`, `app/services/clinical.py:138-169` |
| No real secrets are committed: `.env` is git-ignored and `git grep` found no hard-coded keys outside the dev defaults in `config.py` | `.gitignore`, `.env.example` |
| Compose refuses to start without `JWT_SECRET` | `infra/docker/docker-compose.yml:30` (`${JWT_SECRET:?...}`) |

---

## 2. Defects

### 2.1 RLS table inventory (all 40 tables created by migrations)

There is no `FORCE ROW LEVEL SECURITY` on any table (`grep -rn FORCE alembic app` returns nothing).

| Migration | Table | RLS enabled | Policy | Notes |
|---|---|---|---|---|
| 0001 | organizations | yes | SELECT / INSERT(bootstrap) / UPDATE | no DELETE policy |
| 0001 | branches | yes | ALL tenant | |
| 0001 | memberships | yes | SELECT (user OR org) / INSERT / UPDATE / DELETE (org) | |
| 0001 | audit_events | yes | SELECT org / INSERT org-or-NULL | |
| 0001 | users | **no** | – | `hms_app` has full SELECT/INSERT/UPDATE/DELETE, including `is_superadmin` and `password_hash` |
| 0001 | auth_sessions | **no** | – | `hms_app` has full DML |
| 0001 | roles, permissions, role_permissions | no (global) | – | SELECT only |
| 0005 | patients, appointments, opd_queue, idempotency_keys | yes | `<t>_tenant` | |
| 0006 | encounters, encounter_vitals, encounter_diagnoses, prescriptions, prescription_items, invoices, invoice_items, payments, refunds, ledger_entries | yes | `<t>_tenant` | |
| 0006 | drug_catalog | no (global) | – | SELECT only |
| 0007 | stock_batches, dispenses, dispense_items, stock_movements, lab_orders, lab_specimens, lab_results | yes | `<t>_tenant` | |
| 0007 | lab_test_catalog | no (global) | – | SELECT only |
| 0008 | wards, beds, admissions, admission_transfers, nursing_records, inventory_items, inventory_movements, expenses | yes | `<t>_tenant` | |

Model `__tablename__` set (40 tables) equals the migration-created set.

### 2.2 Findings

#### HIGH

**H1. An admin can add any existing user from another tenant to their organization without consent; this also leaks that user's name and enables e-mail enumeration.**
- Where: `app/routers/members.py:68-80, 91-115, 31-44`.
- `create_member` looks up `users` by e-mail globally. `users` has no RLS, see `0001:13-15`. If the user exists, it silently reuses them and ignores the supplied password.
- It then creates a membership in the caller's org and returns `MemberOut` with the existing user's `full_name`, taken from the user row (`members.py:39`).
- Consequences:
  - (a) Org A learns whether any e-mail is registered and the real name behind it.
  - (b) The victim gains an unsolicited org-A membership. Their next login without a slug returns 409 and lists org A's slug (`auth.py:258-272`), which is a login disruption.
  - (c) The victim can enter org A with their own password.
- There is no invitation or acceptance flow.

**H2. A client-controlled `X-Request-ID` longer than 64 characters breaks every audited request and lets an attacker suppress failed-login audit events.**
- The middleware accepts any value: `rid = request.headers.get("x-request-id") or uuid4` (`app/main.py:63`).
- That value is passed as `correlation_id` into `insert_audit_event`. The function parameter is `text`, but the column is `String(64)` (`0001:161`), so the insert raises "value too long".
- Effects:
  - Every write endpoint returns 500.
  - On `/auth/login` failures, `record_security_event` (`auth.py:221-236`) raises before the 401. The failed-login audit row is never written.
  - Brute force (see H4) can therefore run without leaving audit records.
  - In the refresh-reuse path the family is revoked (`auth.py:324`) but `auth.refresh_reuse_detected` is lost.

**H3. Idempotency "concurrent duplicate" handling rolls back the whole request but still returns 201 for a record that was never saved.**
- Where: `app/services/clinical.py:196-199` catches `IntegrityError` from the idempotency-row flush and calls `db.rollback()`. That discards the entire transaction: the patient, payment, admission and so on, plus the audit event and the transaction-local GUCs.
- The callers (`patients.py:132-141`; the same pattern in billing, ipd, opd_queue, expenses, inventory and pharmacy) then `return out`. The client receives 201 with an id or UHID that does not exist.
- How it triggers:
  - Two concurrent requests with the same key: the replay check (`clinical.py:152-158`) has no lock, so both create.
  - Any key longer than 100 characters: it is stored truncated (`key[:100]`, `clinical.py:188`) but looked up untruncated (`:155`), so a retry never replays and always collides.
- For `POST /billing/invoices/{id}/payments` this means "payment recorded" responses for payments that do not exist.

**H4. No rate limiting, lockout, or throttling on any auth endpoint.**
- A search for `ratelimit|slowapi|lockout|failed_attempts` in `app/` returns nothing.
- `/auth/login`, `/auth/register` (unauthenticated org creation) and `/auth/refresh` are unthrottled. Each login or register costs one 16 MiB scrypt run, so these endpoints are both a credential-stuffing surface and a CPU/memory DoS surface.
- This is acknowledged as pending in `SECURITY_CHECKLIST.md:17,50` and `API_DOCUMENTATION.md:155`.

**H5. PHI reads are not audited.**
- No GET handler calls `record_event`:
  - `GET /patients`, `GET /patients/{id}` (`patients.py:144-201`)
  - encounters, prescriptions, lab orders and results, admissions, nursing records, invoices and receipts
  - `GET /audit-events` itself (`routers/audit.py:16-40`)
- Only writes are audited.
- This contradicts `SECURITY_CHECKLIST.md:76-77` ("every PHI read/write is recorded") and the `auditing.py:3` docstring ("Every sensitive read/write path records an event").

**H6. The default JWT secret is accepted in every environment.**
- `jwt_secret` defaults to `"insecure-dev-only-secret-change-me"` (34 characters), which passes the only validator: a length of at least 16 (`app/config.py:28, 36-41`).
- There is no check that `ENVIRONMENT != development` rejects the default. Anyone running the image without `JWT_SECRET` (outside compose) signs tokens with a public key.
- The minimum of 16 characters is also below the 32 bytes recommended for HS256.
- Default DB passwords `change_me` are also baked into `config.py:24,26`.

#### MEDIUM

**M1. The DB commit runs after the response has been sent.**
- With FastAPI 0.151 (requirements allow `>=0.115,<1.0`), dependencies with `yield` and the default scope exit after `await response(...)` (`site-packages/fastapi/routing.py:147-152`; `dependencies/utils.py:666`).
- `get_db` commits in that exit (`app/db.py:34-44`).
- Effects:
  - A commit failure, such as the deferred FK in `0007:361-367`, a serialization error or a dropped connection, reaches the client as 2xx after the data has been rolled back.
  - A client that immediately reuses a fresh token can race the commit. For example, register then call `/me`, and the session row may not be visible yet.
- Fix: use `Depends(get_db, scope="function")` or an explicit commit before returning.

**M2. The `insert_audit_event()` tenant guard is bypassed when the org GUC is empty.**
- `IF p_organization_id IS NOT NULL AND p_organization_id <> nullif(current_setting(...),'')::uuid` (`0003:443-447`).
- With no org GUC set, the comparison is NULL, the `IF` is skipped, and the SECURITY DEFINER function inserts an event for any organization.
- The app itself relies on this: `record_security_event` in a fresh session with no GUC writes an org-scoped `auth.refresh_reuse_detected` (`auth.py:325-334`).
- This falsifies `DATABASE_SCHEMA.md:146-148` ("a compromised app role still cannot forge another tenant's audit history").
- `actor_user_id` is not validated either.
- The function is owned by the migration role, which is a superuser in compose and CI (`DEPLOYMENT.md:49`).
- Fix: use `IS DISTINCT FROM`.

**M3. Concurrent refresh-token reuse is not detected.**
- `refresh` reads the session row without `with_for_update()` (`auth.py:316`).
- Two parallel requests with the same refresh token both see `revoked_at IS NULL`. Both rotate and mint two live sessions, and reuse detection never fires.

**M4. Sessions have no absolute lifetime, and org suspension is not enforced on existing sessions.**
- Each rotation creates a new row with `expires_at = now + 14d` (`auth.py:66-67, 354-356`), so a refresh family can live forever.
- `get_current_principal` (`deps.py:62-138`) and `refresh` (`auth.py:340-351`) never check `organizations.status`. Only login does (`auth.py:277-279`).
- A suspended org's staff therefore keep full access until they stop refreshing.

**M5. `X-Forwarded-For` is trusted unconditionally.**
- `get_client_ip` uses the first XFF entry from any client (`deps.py:51-55`).
- Audit `ip_address` and the session `ip_address` can be spoofed. The Next rewrite proxy forwards client headers.

**M6. Tenant consistency of foreign keys is not enforced in the DB.**
- All child FKs are single-column, for example `appointments.patient_id -> patients.id` (`0005:117`). There are no composite `(organization_id, id)` FKs: `grep ForeignKeyConstraint` returns nothing.
- FK checks bypass RLS, so a row in org A can reference org B's patient if the service layer misses a check.
- `DATABASE_SCHEMA.md:153` claims "FKs tenant-consistent via composite policy checks", which is false.

**M7. Immutability triggers have gaps.**
- `trg_inv_issued_frozen` only compares the financial columns; `status` is not frozen (`0006:662-685`).
  - `UPDATE invoices SET status='draft'` on an issued invoice passes.
  - The financials can then be edited, because `OLD.status='draft'`.
  - The trigger is `BEFORE UPDATE` only, so issued invoices can be DELETEd: `hms_app` keeps DELETE through the default privileges in `0001:184-185`.
- `trg_enc_completed_immutable` is `BEFORE UPDATE` only (`0006:656-660`). Completed encounters can be deleted. `encounter_vitals` and `encounter_diagnoses` have no trigger.
- `payments` and `refunds` have no trigger and keep UPDATE/DELETE grants.

**M8. Downgrade paths fail on any database that holds data.**
- `0002:98-101` deletes `roles` while `memberships.role_id` (`ON DELETE RESTRICT`, `0001:118-119`) still exists.
- `0006:745` deletes `drug_catalog` before dropping `prescription_items` (`RESTRICT` FK, `0006:317`).
- `0007:706` deletes `lab_test_catalog` before dropping `lab_results` (`RESTRICT` FK, `0007:346`).
- `0001` downgrade leaves the `hms_app` role and the `ALTER DEFAULT PRIVILEGES` in place.

**M9. Tokens are kept in `localStorage`, and the refresh token is stored but never used.**
- `apps/web/src/lib/auth.ts:18-23` stores both tokens.
- No `/auth/refresh` call exists in `apps/web/src`, so a long-lived (14-day) credential sits exposed to any XSS for no benefit.
- No CSP header is set (`main.py:67-70`).

**M10. `users` and `auth_sessions` have no RLS, and `hms_app` has full DML on them.**
- Any SQL-level compromise can rewrite `is_superadmin` or `password_hash`. `is_superadmin` grants every permission (`deps.py:118-121`).
- This is documented as by design, but it is the largest remaining hole in the defence-in-depth claim.

**M11. The API image runs as root and migrates on startup.**
- `infra/docker/api.Dockerfile` has no `USER` line, so uvicorn runs as root.
- `CMD` runs `alembic upgrade head` at start, so the runtime container needs migration (superuser) credentials (`docker-compose.yml:28-29`).
- `web.Dockerfile` is also root and copies the whole build tree, including dev dependencies.
- Compose publishes Postgres on host port 5432.

**M12. Dependencies are not locked.**
- `requirements.txt` uses ranges only (`fastapi>=0.115,<1.0`, `pyjwt>=2.9,<3.0` and so on). There is no lock file or hashes, and there is no `pip-audit` step in CI (`.github/workflows/ci.yml`).
- A floating FastAPI version already changed transaction semantics (see M1).

#### LOW / INFO

- **L1.** `.env.example:14-15` uses `JWT_ACCESS_TTL_SECONDS` and `JWT_REFRESH_TTL_SECONDS`, but the settings fields are `access_token_ttl_seconds` and `refresh_token_ttl_seconds` (`config.py:31-32`). Because of `extra="ignore"`, these env vars are silently ignored.
- **L2.** Register reveals whether an e-mail exists ("An account with this email already exists", `auth.py:133-137`). This contradicts the "no account enumeration" claim (`SECURITY_CHECKLIST.md:11-12`).
- **L3.** scrypt N=2^14 is below the OWASP Password Storage Cheat Sheet minimum (N=2^17, r=8, p=1), yet it is labelled "OWASP-approved" (`security.py:23-25`, `ARCHITECTURE.md`).
- **L4.** Organizations policies:
  - `org_insert_bootstrap` only checks `app.is_bootstrap='true'`, which any session can set because custom GUCs are user-settable. It does not check `id = GUC_ORG` (`0001:214-217`), contrary to `ARCHITECTURE.md` and `DATABASE_SCHEMA.md:130`.
  - `org_update_member` lets any active member of any role UPDATE the org row, `WITH CHECK (TRUE)` (`0001:218-227`).
  - Membership INSERT RLS does not restrict `role_id`, so an owner role could be inserted at the DB layer.
- **L5.** There is no `FORCE ROW LEVEL SECURITY` on any table. This is acceptable while runtime always uses `hms_app`, but the table owner (the migration role, a superuser in compose and CI) bypasses RLS. There is no guard against misconfiguring `DATABASE_URL` to the owner.
- **L6.** `inventory.py:253-260` returns raw `DBAPIError` text to clients for any DB error, not only trigger messages.
- **L7.** The 403 detail echoes the permission key (`deps.py:148-151`). OpenAPI and docs are exposed in every environment (`main.py:47-48`). `/health` discloses `environment` without auth (`health.py:10-18`).
- **L8.** CORS `allow_headers` omits `Idempotency-Key` (`main.py:57`). Cross-origin clients cannot send it, although the web app uses a same-origin rewrite. HSTS is not set at app level.
- **L9.** Search `q` is interpolated into `LIKE` without escaping `%` and `_` (`patients.py:168-173`). This stays within the tenant; it is info only.
- **L10.** Org-NULL security events (failed logins for a real user, `auth.py:230-236`, with `organization_id` unset) are invisible to every tenant (`audit_select`), and no operator endpoint exists, so nobody can read them.
- **L11.** Idempotency rows never expire. They are scoped per org, not per user, so another user in the same org who reuses a key receives the first user's stored response.
- **L12.** The SECURITY DEFINER function is owned by a superuser in compose and CI. `search_path` is set correctly (`0003:440`), which mitigates this.

---

## 3. Doc claims that are false or stale

| Doc | Claim | Reality |
|---|---|---|
| `SECURITY_CHECKLIST.md:76-77` | "every PHI read/write is recorded with actor, resource, IP" | Reads are not audited (H5); IP can be spoofed (M5) |
| `SECURITY_CHECKLIST.md:71-72` | The user "or an admin" calls `POST /auth/logout` to contain a lost device | Logout revokes only the caller's own session (`auth.py:378-380`). No admin session-revocation endpoint exists |
| `SECURITY_CHECKLIST.md:78` | "reset the user's password (owner/admin)" | No password reset or change endpoint exists at all |
| `SECURITY_CHECKLIST.md:11-12` | "no account enumeration" | Register 409 enumerates (L2); members POST enumerates and leaks names (H1) |
| `SECURITY_CHECKLIST.md:35` | "JWT secret length enforced" | Only ≥16 characters, and the public default secret is accepted (H6) |
| `SECURITY_CHECKLIST.md:41` | "No PHI in ... error bodies" | The duplicate-patient 409 returns candidates' name, DOB and phone (`patients.py:71-91`). This is intentional, but the claim is false. `inventory.py` returns raw DB errors |
| `SECURITY_CHECKLIST.md:55` | "+33 automated tests" | 102 `def test_` functions exist (stale) |
| `ARCHITECTURE.md` (RLS summary) and `DATABASE_SCHEMA.md:130` | org INSERT is "only for the id claimed in GUC(org)" | The policy checks only the bootstrap flag (`0001:214-217`) |
| `DATABASE_SCHEMA.md:146-148` | The audit write-guard means a compromised app role "cannot forge another tenant's audit history" | Bypassed when the GUC is empty (M2) |
| `DATABASE_SCHEMA.md:153` | "FKs tenant-consistent via composite policy checks" | No composite FKs or policies exist (M6) |
| `DATABASE_SCHEMA.md:1-10, 113-119` | Titled "(M2)"; lists migrations 0001–0005 only; idempotency "Used by POST /patients and POST /opd/queue" | 0006–0008 migrations exist. The 0007/0008 tables (stock_*, lab_*, wards, beds, admissions, nursing, inventory_*, expenses) are missing from the RLS table. Idempotency is also used by billing payments, ipd admissions, expenses, inventory and pharmacy |
| `DATABASE_SCHEMA.md:187-188` | "invoice financials and line items freeze on issue" | The status can be flipped back to draft, and issued invoices can be deleted (M7) |
| `ARCHITECTURE.md` "Environments" | "idempotency keys for payments/orders arrive with M3" | Stale; already implemented |
| `ARCHITECTURE.md` / `security.py` docstring | scrypt N=16384 is "OWASP-approved" | Below the OWASP minimum (L3) |
| `auditing.py:3` | "Every sensitive read/write path records an event" | Reads are not audited (H5) |
| `0001` docstring and docs | `users` / `auth_sessions` are "never joined into cross-tenant responses" | `members.py` returns another tenant's user `full_name` (H1) |

---

## 4. Missing features (verified absent in code)

- Rate limiting, login throttling and account lockout (H4).
- MFA / TOTP, password reset, password change, and revoking sessions on password change.
- Admin endpoints to suspend or update a member, change their role, or revoke their sessions. `members.py` has only POST and GET, so `memberships.status='suspended'` cannot be set through the API.
- Member invitation or consent flow (H1).
- Branch-level authorization: `memberships.branch_id` is stored but never used for access control; it is only echoed in `/auth/me` (`auth.py:406`).
- Audit logging of PHI reads; an operator view of org-NULL security events.
- Absolute session lifetime and idle timeout; org-suspension enforcement on live sessions.
- `org.read`, `org.manage` and `org.transfer_ownership` are seeded (`0002:318-327`) but no endpoint uses them. No org profile or settings API exists.
- Trusted-proxy configuration for client IP.
- Dependency lock file, vulnerability scanning in CI, and non-root container users.
- CSP / HSTS headers; refresh token in an httpOnly cookie.

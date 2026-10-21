# Audit: Mobile app (apps/mobile) + Infra / Deployment / CI

Static review only (Flutter not installed; Dart tests not executed). Repo HEAD: `91c5f2a` (M4 = `e65bad4`).
All paths are relative to `/home/user/Aditya-BioNova-Smart-HMS`.

---

## Part 1 — Flutter Android app

### Stack snapshot
- `pubspec.yaml`: Dart `^3.13.5`, Flutter `>=3.38.4` (lock). Direct deps: `http 1.6.0`, `pointycastle 4.0.0`, `flutter_secure_storage 11.2.0`, `path_provider 2.1.6`, `cupertino_icons 1.0.9`; dev `flutter_lints 6.0.0`. No state-management, i18n, connectivity, background-work, push, or crash-reporting package.
- `analysis_options.yaml`: default `flutter_lints`, no extra rules, `android/**` excluded.
- Android: AGP 9.1.0, Kotlin 2.4.0, Gradle 9.3.1, Java/JVM 17. `namespace` = `applicationId` = `in.adityabionova.aditya_bionova_mobile` (build.gradle.kts:36,46). `minSdk/targetSdk/compileSdk` = Flutter defaults (build.gradle.kts:37,47-48), not pinned explicitly. No iOS project.
- 12 test files, **40 `test`/`testWidgets` cases** (claim of 40 is accurate by count).

### Verified working (by reading the code)
| Claim (TASKS.md:66-107) | Status | Evidence |
|---|---|---|
| AES-256-GCM sealed store, fresh random 12-byte nonce per write, `HMS1` AAD, 128-bit tag | TRUE | `lib/store/local_store.dart:175-193` (`Random.secure()` nonce, `GCMBlockCipher(AESEngine())`, AAD = magic) |
| Tamper / wrong-key detected and raised | TRUE at store level | `local_store.dart:143-149` (but see D3: swallowed in `main.dart`) |
| Atomic writes (tmp + rename), serialized write chain | TRUE | `local_store.dart:165-169, 200-202` |
| AES key generated with `Random.secure`, stored in Keystore-backed `flutter_secure_storage`, never in file | TRUE | `lib/store/platform_stores.dart:49-64` |
| Tokens in secure storage | TRUE | `platform_stores.dart:24-39`, wired in `main.dart:127` |
| Client UUID per op sent as `Idempotency-Key` | TRUE (mobile side) | `lib/sync/engine.dart:113-118`; but server ignores it on 2 of 4 endpoints (D2) |
| Dedupe keys collapse double taps | TRUE (with bugs, D10/D11) | `lib/sync/outbox.dart:115-143` |
| `$ref:` id map with deferral; `$ref` never pushed | TRUE in engine | `lib/sync/idmap.dart:45-67`, `engine.dart:98-104`; but UI can bypass it (D6) |
| Conflict queue, keep/discard UI, no LWW | Partly | `engine.dart:156-180`, `lib/screens/sync_tab.dart:168-200`; see D8/D9 |
| Restart recovery (outbox, directory, idmap, drafts persisted & restored) | TRUE for data; FALSE for usability (D4) | `main.dart:62-106` |
| Signed release config, keys git-ignored | TRUE | `android/app/build.gradle.kts:28-75`, `android/.gitignore` (`key.properties`, `**/*.keystore`, `**/*.jks`) |
| Signing online-only, gated on server id | TRUE | `lib/screens/rx_tab.dart:167-179, 372-377` |
| 401 stops the run; 5xx/network → failed, retryable | TRUE | `engine.dart:80-96, 119-126, 139-154, 182-186` |

### Defects

| # | Sev | Location | Finding |
|---|---|---|---|
| D1 | **Critical** | `android/app/src/main/AndroidManifest.xml:1-45` | **No `<uses-permission android:name="android.permission.INTERNET"/>` in the main manifest.** It exists only in `src/debug` and `src/profile` manifests (Flutter template). None of `http`, `flutter_secure_storage`, `path_provider` merge INTERNET in. A **release APK cannot reach the API at all** — login, sync, directory refresh all fail. Tests use a fake transport so they cannot catch this. |
| D2 | **High** | API `apps/api/app/routers/prescriptions.py:163-170`, `routers/billing.py:111-118` | Mobile pushes `POST /prescriptions` and `POST /billing/invoices` with `Idempotency-Key`, but these endpoints **do not read the header** (only patients, opd_queue, ipd, expenses, payments, inventory do). A response lost after commit (very common on flaky rural networks) marks the op `failed`; retry creates a **duplicate invoice / duplicate prescription**. Contradicts TASKS.md:78-80 "no double invoice" and `billing_tab.dart:3-6` "can never charge the patient twice". |
| D3 | **High** | `lib/main.dart:123-135` | `_deviceGraph` wraps store open in `catch (_) { return AppGraph(baseUrl) }` → any decryption/tamper/corrupt-header/Keystore error silently falls back to an **in-memory store**. The user sees an empty app, new offline work is never persisted (lost on kill), no warning shown. Contradicts the store's own "never silently dropped" contract and test `encrypted_store_test.dart:99`. Triggered deterministically by D5. |
| D4 | **High** | `lib/main.dart:152`, `lib/screens/login_screen.dart:42-63` | App **always starts at `LoginScreen`**, which requires a successful network `POST /auth/login`. Stored tokens are never checked on launch. After any restart while offline (airplane mode, no signal), the user **cannot reach the outbox, queue, registration, or Rx** — "restart recovery" is data-only. `restart_recovery_test.dart:36-46` masks this by injecting a token and bypassing the UI. |
| D5 | **High** | `AndroidManifest.xml:2-5` (no `android:allowBackup`/`dataExtractionRules`) | Auto Backup defaults on. `hms_offline.json` (app docs dir) is backed up, but the Keystore key is not → on restore/new phone `SecureKeyProvider` (platform_stores.dart:51-63) generates a **new key**, the file fails GCM auth, and D3 silently puts the app in memory-only mode **on every launch forever** (stale file never removed). flutter_secure_storage docs explicitly recommend disabling backup. |
| D6 | **High** | `lib/screens/queue_tab.dart:56` (`replacePatients(items)`), `queue_tab.dart:76-79`, `rx_tab.dart:69-73`, `billing_tab.dart:48-52` | Any successful directory refresh **replaces the patient list wholesale, dropping locally registered (`local: true`) patients not yet synced**. If a local patient is still selected, `_patientRef` finds no entry and returns the **raw device UUID** instead of `$ref:` — the op is pushed with a bogus `patient_id` (exactly what idmap.dart:10-13 says must never happen). Refresh runs automatically in `QueueTab.initState`. |
| D7 | **High** | `lib/auth/session.dart:41-56`, `lib/api/client.dart:*`, `lib/screens/home_screen.dart:57-66` | **No refresh-token flow**: refresh token is stored but never read; access TTL is 1800 s (`apps/api/app/config.py:31`). Any offline period >30 min → first sync is 401 → stop. Sign-out only clears tokens: **outbox, patient directory (PHI) and drafts remain** and are pushed under the **next user's** token on a shared device (wrong attribution/audit trail, PHI exposure across users). |
| D8 | Medium | `lib/sync/outbox.dart:174-188`, `outbox.dart:68` | `resolveConflict(keepLocal: true)` doc says "re-queue with the server's current version as the new base" but `baseVersion` is `final` and never updated; payload is immutable and re-sent with the **same Idempotency-Key**. For the duplicate-patient 409 the API supports `allow_duplicates` (`apps/api/app/schemas.py:194`) but mobile never sets it → "Keep local" loops into the same 409 forever. |
| D9 | Medium | `outbox.dart:178-188`, `engine.dart:98-104` | Discarding a conflicted *creating* op (e.g. registration) leaves every dependent `$ref` op **pending/deferred forever** ("waiting N"), with no UI to discard them (they aren't `conflicted`). |
| D10 | Medium | `billing_tab.dart:76-77` | Invoice dedupe key = patient + description + UTC day; ignores quantity/price/item type. A second, legitimately different line with the same description is silently swallowed as "Identical invoice". |
| D11 | Medium | `rx_tab.dart:137-138` | Rx dedupe key = patient + drug ids (no dose/frequency/duration/date). A corrected dose while the first op is open is rejected as "Identical draft"; same regimen on a later day is blocked until the first op drains. |
| D12 | Medium | `queue_tab.dart:90`, `register_tab.dart:78`, `billing_tab.dart:75` | "Today" computed in **UTC**; in IST, 00:00-05:29 belongs to the previous day → per-day dedupe wrong for early-morning (emergency) work. |
| D13 | Medium | `lib/api/transport.dart:69-77` | No request timeout on `http.Client.send`; a half-open connection hangs `SyncEngine.sync()` indefinitely and leaves the Sync button stuck at "Syncing…". |
| D14 | Medium | `engine.dart:80`, `outbox.dart:106-107, 162-173` | No automatic retry/backoff/connectivity trigger: failed ops are only retried after a manual "Retry failed" tap, and `attempts` is never used. Ops left `inFlight` (persisted if an enqueue fires mid-sync, then app killed) are **never re-queued**: `pending` and `retryOpen` both ignore `inFlight`. |
| D15 | Medium | `engine.dart:168-180` | All 4xx except 401/409/412 parked as permanent "policy" conflicts — includes **408 and 429** (should be retryable) and 403 (permission, should prompt re-login/role change). `serverState: res.body` is the error body, not server state. |
| D16 | Medium | `rx_tab.dart:54-67` | Drug catalog is fetched only by the manual Rx "Refresh" button (not on init/login). A doctor who never pressed it has no catalog offline → cannot write any Rx. Same for directory: `listPatients(limit=100)` (`client.dart:103-104`) caches only the first 100 patients. |
| D17 | Medium | `rx_tab.dart:329-370` | Draft whose op was discarded shows **"Synced"** (op == null and not signed) — false sync state on a clinical document. Lookup key `'rx:$localRef'` (line 329) never matches the real key format. |
| D18 | Low | `outbox.dart:102, 204-212` | Op ids / idempotency keys / localRefs use non-cryptographic `Random()`; UUID collision risk across devices is low but `Random.secure()` should be used for server idempotency keys (keys are scoped per org on the server). |
| D19 | Low | `main.dart:91-92`, `outbox.dart:100` | `onChanged` is `void Function()`; `_persistOutbox` returns a Future that is dropped → disk-full/IO errors become unhandled async errors and are silently lost. |
| D20 | Low | `main.dart:119-122` | Default `API_BASE` is cleartext `http://10.0.2.2:8000`; no `network_security_config`, no certificate pinning, no build-time guard that release builds use https. (Cleartext is blocked by default on targetSdk ≥28, which turns a misconfigured release into a silent total failure.) |
| D21 | Low | `register_tab.dart:48-58, 67-75` | Same name + empty phone always "duplicate prevented" with no override path, despite the message offering "register anyway". |
| D22 | Low | `local_store.dart:175-176` | `keys.key()` hits secure storage on every write (no caching); first-launch key generation has no lock (safe today only because writes are chained). |
| D23 | Low | `sync_tab.dart:71` | Label "applied: N in flight" is misleading; the "Syncing…" chip is never visible (no rebuild during a run). |
| D24 | Low | `AndroidManifest.xml:3` | `android:label="aditya_bionova_mobile"` (package name shown as app name); no `FLAG_SECURE` (PHI visible in recents/screenshots); no app lock / inactivity timeout. |
| D25 | Low | `build.gradle.kts:66-75` | Release silently falls back to the debug key; TASKS.md:97 says the build "says so" — there is no Gradle warning/failure. No explicit R8/`proguardFiles` (Flutter defaults apply), no `--obfuscate --split-debug-info` documented. |

### Doc claims false / stale
- TASKS.md:78-80, README.md:14, `billing_tab.dart:3-6`: "a replay can never double-apply / no double invoice" — false for invoices and prescriptions (D2).
- `engine.dart:15-18`, `README` conflict row: `X-Base-Version` "so the API can refuse stale writes" — **the API never reads `X-Base-Version`** (no occurrence in `apps/api`); every op sends `0`. 409/412 versionMismatch path is effectively dead except duplicate-patient 409.
- TASKS.md:90-93 / README.md:19 "restart recovery" — UI requires online login after restart (D4).
- TASKS.md:71-75 "no PHI readable on lost device" — true at rest, but D7 (left behind after sign-out) and D3/D5 degrade it.
- `session.dart:3-7` says Keystore wiring "lands with the Android toolchain" — stale; it is wired (`main.dart:127`).
- `main.dart:114-117` "nothing is silently lost" — false (D3).
- `outbox.dart:174-177` "re-queue with the server's current version as the new base" — not implemented (D8).
- TASKS.md:97 "falls back to the debug key and says so" — no message (D25).
- README.md:4 (root) "trilingual UI (English / मराठी / हिंदी)" — mobile is English-only, hard-coded strings, no `flutter_localizations`/ARB.

### Missing (mobile)
- INTERNET permission in release (D1); refresh-token handling; offline app unlock (cached session / PIN / biometric).
- Background sync (WorkManager), connectivity listener, automatic retry with backoff + jitter, request timeouts.
- i18n (mr/hi), accessibility review, app name/branding.
- Modules: pharmacy, lab, IPD, encounter/vitals, payments, appointments, patient search beyond first 100 — none on mobile. No push notifications (FCM), no crash reporting/analytics (Crashlytics/Sentry), no remote config / forced-update, no Play Store metadata.
- Device QA (acknowledged in TASKS.md:103-105); no integration_test/ or emulator tests; mobile **not in CI**.
- iOS project absent (fine if Android-only is the scope).

---

## Part 2 — Infra / deployment / CI

### Verified working
- Compose: Postgres healthcheck + `depends_on: condition: service_healthy` for API (`infra/docker/docker-compose.yml:17-22, 35-37`).
- `JWT_SECRET` required in compose via `${JWT_SECRET:?…}` (compose:30).
- Separate non-owner `hms_app` runtime role vs owner migration role (compose:28-29, `postgres-init/01-roles.sh:7-15`, `apps/api/alembic/env.py:1,29,40`) — good RLS posture.
- Web image is multi-stage (`web.Dockerfile:2,9`); `.env`, `*.pem`, `*.key`, `secrets/` git-ignored (`.gitignore:7-13`); Android keystores ignored.
- CI runs ruff, full pytest against real Postgres 16 incl. RLS, web typecheck+build, and an OpenAPI drift check (`.github/workflows/ci.yml`).

### Defects
| # | Sev | Location | Finding |
|---|---|---|---|
| I1 | **High** | `apps/web/next.config.mjs:2-14`, `web.Dockerfile:7`, compose:44 | `rewrites()` destination is built from `API_ORIGIN` at **`next build`** time (serialized into the routes manifest). The build stage has no `API_ORIGIN`, so the image bakes `http://127.0.0.1:8000`; the runtime `API_ORIGIN=http://api:8000` in compose is likely ignored → web container proxies to itself and every API call fails. Pass it as a build ARG (or use a runtime proxy). DEPLOYMENT.md:44 admits the stack was never run. |
| I2 | **High** | `api.Dockerfile:1-19`, `web.Dockerfile:9-14` | Both containers **run as root** (no `USER`), no `HEALTHCHECK`, no read-only FS / cap drop in compose. |
| I3 | **High** | repo root (no `.dockerignore` anywhere) + `api.Dockerfile:13`, `web.Dockerfile:6` | `COPY apps/api/ .` copies any local `apps/api/.env` (read by pydantic `env_file=".env"`, `config.py:16`), `.coverage`, `.pytest_cache`, tests into the image → **secrets can be baked into images**. `COPY apps/web/ .` copies the host `node_modules` (present in the workspace) over the `npm ci` result → wrong-platform native binaries (musl vs glibc, `@next/swc`). |
| I4 | **High** | `apps/api/app/config.py:28,35-40` | `jwt_secret` default `"insecure-dev-only-secret-change-me"` passes the ≥16-char validator; nothing refuses to start with it when `ENVIRONMENT=production`. Any non-compose deployment that forgets `JWT_SECRET` runs with a public signing key (token forgery across tenants). |
| I5 | Medium | `.env.example:15-16`, `DEPLOYMENT.md:25` | Documented `JWT_ACCESS_TTL_SECONDS` / `JWT_REFRESH_TTL_SECONDS` **do not map** to settings fields (`access_token_ttl_seconds` → env `ACCESS_TOKEN_TTL_SECONDS`); with `extra="ignore"` they are silently ignored. |
| I6 | Medium | compose:12-13, 33-34, 45-46; `api.Dockerfile:19` | Postgres `5432`, API `8000`, web `3000` published on **all host interfaces**; default password `change_me` for both DB roles; `ENVIRONMENT: development` hard-coded in the "staging" stack. DEPLOYMENT.md:57 says "API binds loopback only" — contradicted. |
| I7 | Medium | `api.Dockerfile:19` | `alembic upgrade head` on every container start (racy with >1 replica; DEPLOYMENT.md:62-63 says migrations should be a separate step). Single uvicorn worker, no `--proxy-headers`/`--forwarded-allow-ips` (client IPs for audit/rate limiting will be the proxy's). `sh -c` as PID 1 + `npm run start` as PID 1 → poor SIGTERM handling. |
| I8 | Medium | `api.Dockerfile:2,11`, `web.Dockerfile:2,9`, compose:7, `apps/api/requirements.txt` | Floating tags (`python:3.12-slim`, `node:22-alpine`, `postgres:16-alpine`), no digests; Python deps are **ranges with no lock/hashes** (`fastapi>=0.115,<1.0` …) so builds are not reproducible and LICENSES.md's exact versions can't be guaranteed. Web runtime image ships full `node_modules` incl. devDeps and source (no `output: "standalone"`). |
| I9 | Medium | `apps/api/app/routers/health.py:10-18` | `/health` does not touch the DB — useless as a readiness probe. |
| I10 | Low | `postgres-init/01-roles.sh:11`, `scripts/setup_local_db.sh:23,25` | Password interpolated into SQL literal unescaped (breaks/injects on `'`). init script only runs on an empty volume; doesn't grant privileges (relies on migrations). |
| I11 | Low | `scripts/generate-contracts.sh:5-6` | Falls back to system `python3` silently; fine. |

### CI gaps (`.github/workflows/ci.yml`)
- **No Flutter job** (`flutter analyze`/`flutter test` never run in CI — the 40 tests are unverified by automation).
- No security scanning: no CodeQL/SAST, no `pip-audit`/`npm audit`/Dependabot, no secret scanning step (gitleaks), no container image scan (Trivy), no SBOM generation (LICENSES.md:70-71 says per-release, unchecked ⬜).
- No Docker build job → Dockerfiles/compose never built (I1/I3 would be caught).
- No E2E (Playwright ignored in `.gitignore:39` but not present), no web unit tests (package.json has no `test` script).
- ruff limited to `F,E`; no mypy; no coverage gate.
- Actions pinned by tag (`@v4/@v5`), not SHA; no `permissions:` block (default token scope); no `concurrency`; triggers only on `push: main` and `pull_request` (no tags/release workflow, no scheduled dependency scan, no deploy pipeline, no APK build/sign job).

### Missing (infra/ops)
- Reverse proxy / TLS termination (nginx/Caddy/Traefik) — only described in prose (DEPLOYMENT.md:57-58), no config in repo; no HSTS/security headers config.
- Backups: only manual `pg_dump` snippet against `hms_dev` (DEPLOYMENT.md:70-76); no scheduled job, no encryption, no off-site, no PITR/WAL archiving, no restore drill automation.
- Monitoring/logging: explicitly M7 backlog (DEPLOYMENT.md:81-86) — no structured logs, metrics, alerting, error tracking.
- No staging/prod compose or k8s/Helm/IaC; no secret-manager integration; no resource limits; no log rotation.
- LICENSES.md omits the **Dart/Flutter/Android** dependency tree (pointycastle MIT, flutter_secure_storage BSD-3, http/path_provider BSD-3, Flutter engine/AndroidX).
- DEPLOYMENT.md has no mobile release/distribution section (keystore custody, Play signing, versioning, API_BASE per environment).

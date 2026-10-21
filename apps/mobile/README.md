# Aditya BioNova Smart HMS — mobile app (M4, hardened in M7.0)

Offline-first Android app for doctors and field staff, sharing the same
FastAPI backend as the web app. One binary serves both roles: the **Staff
app** (register → queue → billing) and the **Doctor app** (queue → Fast Rx),
switched by the role the server reports on `GET /auth/me`.

## What "offline-first" means here

| Concern | Implementation |
| --- | --- |
| Local storage | One AES-256-GCM sealed file (`EncryptedFileStore`) holding named sections; the AES key lives in the Android Keystore (`flutter_secure_storage`), never in the file |
| Session | Keystore-backed token store (`SecureTokenStore`) holding the token pair and the signed-in user's profile. A 401 triggers ONE refresh-token rotation (`POST /auth/refresh`, single-flight, new pair persisted) before the user is asked to sign in again; the outbox is never touched by an expiry |
| Sign-in | `POST /auth/login`; an MFA account answers `mfa_required` → 6-digit TOTP or recovery code → `POST /auth/mfa/verify`. 429 shows "Try again in N minutes" from `Retry-After` |
| Offline start + app lock | After the first online sign-in the user sets a 4–8 digit PIN (stored only as a salted PBKDF2-HMAC-SHA256 hash in the Keystore-backed store). With a stored session the app opens at the PIN lock and reaches Home **with no network**; the PIN is asked again after 5 min in the background. 5 wrong PINs erase the PIN and the stored session (online sign-in required; queued work kept) |
| Store cannot be unlocked | Fail closed: a recovery screen explains it and offers "Try again" or "Reset local data (unsynced items will be lost)" with an explicit confirmation. There is no memory-only fallback |
| Sign-out | Warns when unsynced changes exist and needs explicit confirmation; then revokes the server session (best effort) and wipes outbox, directory cache, id map, Rx drafts, tokens, profile and PIN |
| Per-user ops | Every op records the user who created it; the engine never pushes an op under another user's session (parked as a "created by another user" conflict, released when that user signs in again) |
| Mutations | Every change is an `OutboxOp` with a client-generated UUID used as the server `Idempotency-Key` — a replay can never double-apply |
| Duplicate prevention | One open op per `dedupeKey` (same patient into today's queue twice stays ONE op; invoice keys include line type, quantity and price; Rx keys include the whole regimen; "today" is the device-local day), plus the server's idempotency store as the backstop |
| Retries | 20 s request timeout; network errors, 408, 429 and 5xx keep the op as "not sent yet" with exponential backoff + jitter (2 s … 15 min, `Retry-After` honoured) and an automatic retry timer; resume / unlock / sign-in trigger a sync. Ops interrupted mid-push by a crash are re-queued at start-up. The `Idempotency-Key` never changes across retries |
| Offline-created entities | A patient registered offline gets a device id; later ops refer to it as `$ref:<local>` and the sync engine swaps in the server id before pushing. A reference that has not synced yet DEFERS the dependent op instead of pushing a bogus id. Directory refreshes merge (never replace) so unsynced registrations stay in every picker, labelled "pending sync"; a raw device id is never sent as `patient_id` |
| Conflicts | 409/412 and other 4xx (not 408/429) → parked as `conflicted`, resolved by a human. A duplicate-patient 409 offers "register anyway" (re-sent with `allow_duplicates: true` under a new key, after confirmation). Discarding a registration also discards the ops that depend on it, after a warning; a discarded Rx draft shows "Discarded — not sent". **No last-write-wins on clinical data.** |
| Explicit sync states | Saved on device · Pending sync / Syncing… / Synced / Conflict — shown per queued item in the Sync centre |
| Restart recovery | Outbox, directory cache, id map and Rx drafts are persisted on every change; `AppGraph.open()` restores them at start-up |
| Signing a prescription | Online-only on purpose: the API's blocking allergy check and the `prescription.sign` permission are server-side. An offline draft can never become a signed prescription |

## Languages, Rural Clinic mode, server features

| Concern | Implementation |
| --- | --- |
| UI languages | English, मराठी, हिंदी via `flutter gen-l10n` (`l10n.yaml`, `lib/l10n/app_{en,mr,hi}.arb`, generated `app_localizations*.dart`). Screens use `context.l10n`. Default = device language (English if unsupported); picker on the login and home screens, stored in the local store's `prefs` section (kept across sign-out). Drug names, doses, frequency codes (OD/BD/TDS…), UHIDs and server error details are never translated. `test/l10n_test.dart` enforces identical keys / placeholders and no empty values |
| Rural Clinic mode | Home ⋮ menu toggle, persisted. ≥ 56 dp touch targets, text ≥ 1.25×, four-step navigation Register → Queue → Fast Rx → Bill (Sync centre in the app bar with a pending badge), one-tap frequency / duration chips on Fast Rx. Same tab widgets, outbox and sync engine — no fork |
| Server features | `GET /auth/me` `features: [key]` + `edition`. Queue ← `opd_queue`, Rx ← `consultation` (and the prescribing role), Billing ← `billing`, dispense quantity ← `pharmacy`; without `mobile_offline` only the Sync centre remains, with a banner. **No `features` field = everything enabled** (older servers). The last reported set is stored with the profile so an offline start honours it |

## Layout

```
lib/
  main.dart              app entry, lifecycle (lock / sync on resume), start routing
  app_graph.dart         AppGraph (session + store + outbox + engine + lock)
  boot.dart              open the sealed store or fail closed (recovery)
  api/                   transport (ApiTransport, timeouts) + HmsClient (MFA, refresh)
  auth/session.dart      TokenStore abstraction + session profile
  auth/app_lock.dart     PIN lock (PBKDF2 hash, inactivity, lockout)
  auth/features.dart     server feature keys / edition (`/auth/me`)
  settings/app_settings.dart  language + Rural Clinic mode (persisted)
  l10n/                  ARB catalogues (en, mr, hi) + generated code
  store/local_store.dart LocalStore, MemoryLocalStore, EncryptedFileStore (AES-GCM)
  store/platform_stores.dart  SecureTokenStore, SecureKeyProvider (Keystore)
  data/directory.dart    cached patients / branches / drug catalog
  data/rx_drafts.dart    prescription drafts written on this device
  sync/outbox.dart       offline queue (dedupe, statuses, serialize/restore)
  sync/idmap.dart        local → server id substitution
  sync/engine.dart       push, classify, refresh-on-401, park conflicts, persist
  sync/scheduler.dart    automatic retry timer + resume trigger
  sync/conflict.dart     conflict model (no silent resolution)
  screens/               login/MFA, PIN, recovery, shell + Queue / Register /
                         Rx / Billing / Sync tabs
test/                    flutter test: outbox, engine, refresh/retry, id map,
                         encrypted store, recovery, app lock, sign-out
                         isolation, pickers/dedupe, conflicts, Android
                         manifest guards, and the offline workflow slices
```

## Running

```bash
flutter pub get
flutter analyze
flutter test

# against a local API (the Android emulator reaches the host via 10.0.2.2;
# cleartext HTTP is allowed in DEBUG builds only)
flutter run --dart-define=API_BASE=http://10.0.2.2:8000

# release builds are HTTPS-only (network security config + a start-up check)
flutter build apk --release --dart-define=API_BASE=https://api.example.in
```

Android manifest: `INTERNET` is declared for release, backup / device
transfer are disabled (`allowBackup=false` + exclude-everything rules — the
Keystore-sealed store cannot be decrypted on another device), and cleartext
traffic is refused outside debug builds.

Full Android build steps, signing-key management and the device QA
checklist: [`docs/ANDROID_BUILD.md`](../../docs/ANDROID_BUILD.md).

## Release signing (keys never committed)

`android/app/build.gradle.kts` reads `android/key.properties`; that file and
any `*.keystore` / `*.jks` are excluded by `android/.gitignore`, so key
material cannot enter the repository. Without the file the release build
falls back to the debug key — fine for local testing, not distributable.

One-time setup on the release machine:

```bash
keytool -genkeypair -v -keystore ~/keys/aditya-bionova-release.jks \
    -keyalg RSA -keysize 2048 -validity 10000 -alias bionova

cat > android/key.properties <<'EOF'
storeFile=/absolute/path/to/aditya-bionova-release.jks
storePassword=…
keyAlias=bionova
keyPassword=…
EOF

flutter build apk --release
```

## Not yet done (labelled, not claimed)

- No Android SDK was available (`dl.google.com` is blocked by the build
  container's egress policy, see `docs/ANDROID_BUILD.md`): the release
  APK, the manifest merge and the network security config have NOT been
  built or run on a device; they are covered by static tests only.
- The mr / hi translations have not yet been reviewed by native-speaking
  clinic staff; the Android launcher label stays "Aditya BioNova HMS".
- MFA enrolment, password change and session management are web-only; the
  app only completes an MFA sign-in.
- On-device/emulator runs: airplane-mode matrix, restart recovery and
  duplicate prevention have been proven in the Dart test harness against a
  fake transport, **not** yet on entry-level physical hardware (M4 device QA).
- Notifications, vitals/device capture and the encounter workspace are not
  in the app yet; they ride on the same outbox/engine and are listed in
  `TASKS.md`.

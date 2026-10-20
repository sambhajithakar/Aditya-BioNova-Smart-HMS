# Android build — Aditya BioNova Smart HMS mobile app

Status on 2026-10-20: **no APK has been built yet.** The Dart side is
verified (`flutter analyze` clean, `flutter test` 173 passing — offline
sync v2, see `MOBILE_OFFLINE_SYNC.md`), but the
release APK, the manifest merge and the network-security config have only
been checked by static tests. The app has **not** run on an emulator or a
physical device.

## 1. Why the demo APK was not built (exact blocker)

The build was attempted in the development container on 2026-10-20:

| Step | Result |
| --- | --- |
| Flutter SDK 3.47.7 (`/var/tmp/flutter-dl/flutter`) | present; `flutter pub get`, `analyze`, `test`, `gen-l10n` work |
| JDK | present: OpenJDK 21.0.12 (AGP 9.1 needs JDK 17+, so no Temurin download was needed) |
| Find the command-line tools file name | `https://developer.android.com/studio` reachable → current file is `commandlinetools-linux-15859902_latest.zip` |
| Download it from `https://dl.google.com/android/repository/…` | **refused: the egress proxy answered `403` to `CONNECT dl.google.com:443`** (policy denial) |
| Repository XML `https://dl.google.com/android/repository/repository2-3.xml` and `dl-ssl.google.com` | **same 403** |
| `https://api.adoptium.net` (Temurin JDK) | **403** (not needed, JDK 21 already installed) |
| `maven.google.com`, `repo1.maven.org`, `services.gradle.org`, `plugins.gradle.org` | reachable (Gradle / AGP / Kotlin artefacts would resolve) |
| `flutter build apk --release` | fails immediately: `[!] No Android SDK found. Try setting the ANDROID_HOME environment variable.` |

`sdkmanager`, the Android platform (`platforms;android-36`), build-tools
and `platform-tools` are only distributed from `dl.google.com`, so with that
host blocked there is no Android SDK, no `aapt`/`apksigner`, and no APK. The
blocked host was not routed around. Consequently **no demo keystore was
generated** and `android/key.properties` was never created — there was
nothing to sign.

To finish this step, run the build on a machine (or CI runner) that can
reach `dl.google.com`, following §2.

## 2. Reproducible build steps

Versions pinned by the repository:

| Component | Version / source |
| --- | --- |
| Flutter | 3.47.7 stable (framework abaf9c5237, engine deb287481e) |
| Dart | 3.13.5 (`environment: sdk: ^3.13.5` in `pubspec.yaml`) |
| Android Gradle Plugin | 9.1.0 (`android/settings.gradle.kts`) |
| Kotlin Gradle plugin | 2.4.0 |
| Gradle | 9.3.1 (`android/gradle/wrapper/gradle-wrapper.properties`) |
| compileSdk / targetSdk | 36 (Flutter defaults, `flutter.compileSdkVersion`) |
| minSdk | 24 = Android 7.0 (Flutter default; `mobile_scanner` needs ≥ 23, `printing` ≥ 21) |
| NDK | 28.2.13676358 (Flutter default) |
| JDK | 17 or newer (bytecode target 17) |
| Native plugins | `flutter_secure_storage` 11.x, `path_provider` 2.1.x, `mobile_scanner` 7.4.2 (CameraX + Google ML Kit barcode, bundled model), `printing` 5.15.1 — exact versions in `pubspec.lock` |

All values above are read from the repository: `minSdk`, `targetSdk` and
`compileSdk` are `flutter.minSdkVersion` / `flutter.targetSdkVersion` /
`flutter.compileSdkVersion` in `android/app/build.gradle.kts`, whose values
come from the pinned Flutter SDK
(`packages/flutter_tools/gradle/src/main/kotlin/FlutterExtension.kt`:
compileSdk 36, minSdk 24, targetSdk 36, NDK 28.2.13676358).

```bash
# 1. JDK 17+ on PATH (java -version), e.g. Temurin 17.
# 2. Android command-line tools (file name from developer.android.com/studio)
export ANDROID_HOME=$HOME/android-sdk
mkdir -p "$ANDROID_HOME/cmdline-tools"
curl -fLo /tmp/clt.zip \
  https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip
sha256sum /tmp/clt.zip   # compare with the checksum on developer.android.com
unzip -q /tmp/clt.zip -d "$ANDROID_HOME/cmdline-tools"
mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0" \
           "ndk;28.2.13676358"
flutter config --android-sdk "$ANDROID_HOME"
flutter doctor -v          # Android toolchain must be ✓

# 3. Build (from apps/mobile)
cd apps/mobile
flutter pub get            # also regenerates lib/l10n/app_localizations*.dart
flutter analyze
flutter test
flutter build apk --release \
  --dart-define=API_BASE=https://api.<your-domain> \
  --build-name=1.0.0 --build-number=1
# output: build/app/outputs/flutter-apk/app-release.apk
```

A release build refuses to start against a non-HTTPS `API_BASE` (start-up
check in `lib/boot.dart`, plus the release network-security config).

Record for every build that leaves the machine:

```bash
APK=build/app/outputs/flutter-apk/app-release.apk
ls -l "$APK"; sha256sum "$APK"
BT=$ANDROID_HOME/build-tools/36.0.0
$BT/aapt dump badging "$APK" | grep -E "package:|sdkVersion|targetSdkVersion|uses-permission"
$BT/apksigner verify --verbose --print-certs "$APK"
```

Expected from the manifest: package = the `applicationId` in
`android/app/build.gradle.kts`, `minSdkVersion 24`, `targetSdkVersion 36`,
permissions `INTERNET` and `CAMERA` (merged by `mobile_scanner` for the
check-in QR / medicine barcode scanner; the camera opens only on the scan
screen) plus whatever the Flutter / `flutter_secure_storage` /
`path_provider` / `printing` plugins merge — check the badging output,
nothing location/contacts/storage should appear — and `allowBackup=false`.
APK size: the bundled ML Kit barcode model adds roughly 2–3 MB per ABI;
build per-ABI APKs for low-cost phones:
`flutter build apk --release --split-per-abi --dart-define=API_BASE=…`.

### Demo signing (local only)

For a throw-away demo build, create the key **outside the repository** and
point `android/key.properties` at it (that file, `*.jks` and `*.keystore`
are git-ignored — verify with
`git check-ignore -v android/key.properties`):

```bash
mkdir -p /var/tmp/hms-demo-signing && chmod 700 /var/tmp/hms-demo-signing
PW=$(openssl rand -base64 24)
keytool -genkeypair -noprompt -keystore /var/tmp/hms-demo-signing/demo.jks \
  -storetype PKCS12 -alias demo -keyalg RSA -keysize 3072 -validity 365 \
  -dname "CN=HMS Demo (not for distribution)" -storepass "$PW" -keypass "$PW"
cat > android/key.properties <<EOF
storeFile=/var/tmp/hms-demo-signing/demo.jks
storePassword=$PW
keyAlias=demo
keyPassword=$PW
EOF
chmod 600 android/key.properties
git status --short   # key.properties must NOT be listed
```

A demo-signed APK is for internal testing only — it can never be updated
by a Play-distributed build and must not be given to clinics.

## 3. Managing the real release key

* **Never** commit a keystore, `key.properties` or a password. The repo
  enforces this with `android/.gitignore` (`key.properties`,
  `**/*.keystore`, `**/*.jks`) and a gitleaks scan in CI; run
  `git status` before every commit anyway.
* **Use Play App Signing (recommended).** Google holds the app-signing key
  in its HSM; the team keeps only an *upload key*. A lost or leaked upload
  key can be reset through Play Console; a lost app-signing key without
  Play App Signing means the app can never be updated.
* Generate the upload key on a trusted machine (RSA 3072+ / 25-year
  validity), store the `.jks` and its passwords in the organisation's
  secret manager (e.g. a vault or the CI provider's encrypted secrets),
  never on shared drives or in chat. Keep an offline encrypted backup.
* CI signing: inject the keystore as a base64 secret, write it and
  `key.properties` into the runner's temp directory at build time, delete
  both after the build; restrict the secret to protected release branches
  / tags and to named maintainers.
* Record the upload-key certificate SHA-256 fingerprint in the release
  checklist; `apksigner verify --print-certs` on every release candidate
  must match it (or Play's app-signing certificate for Play-delivered
  APKs).
* Rotate the upload key if a maintainer with access leaves or a machine is
  compromised (Play Console → App integrity → request upload key reset).
* Without `key.properties` the Gradle config falls back to the **debug**
  key: such an APK is for local testing only.

## 4. Device QA checklist (not yet done — no devices available)

Nothing below has been executed. The behaviour is covered by Dart tests
against a fake transport only. Run on real hardware before any pilot and
record device model, Android version, build sha256 and result per row.

**Device matrix:** Android 8.0/8.1 (API 26/27 — note minSdk is 24, so 7.x
also installs), 9, 10, 11, 12, 13, 14, 15; at least one entry-level
device with 2 GB RAM or less (Android Go if possible), one mid-range
Samsung (One UI) and one Xiaomi/Realme/Vivo (aggressive battery
management), one small 5" screen and one tablet.

1. **Install / first run** — installs from the signed APK, launches, no
   crash; `adb shell dumpsys package in.adityabionova.aditya_bionova_mobile`
   shows only the expected permissions; `allowBackup=false`.
2. **HTTPS only** — release build against an `http://` API refuses to
   start with the explanatory screen; against HTTPS signs in.
3. **Sign-in + MFA** — password, TOTP and recovery code; 429 shows
   "try again in N minutes" in the chosen language.
4. **PIN lock** — set PIN on first sign-in; cold start with no network →
   PIN → Home; 5 min in background → PIN again; 5 wrong PINs → online
   sign-in, queued work kept; PIN survives a reboot.
5. **Airplane-mode visit** — airplane mode ON; register a patient, add
   them to today's queue, write a Fast Rx draft, raise an invoice; every
   item shows "Saved on device · Pending sync"; airplane mode OFF → items
   sync automatically within the retry window, no duplicates on the
   server; Rx can be signed only after sync.
6. **Restart recovery** — with pending items: force-stop the app, swipe it
   away, reboot the phone, kill it mid-sync (toggle network during
   "Syncing…"); after restart every item is still listed and syncs exactly
   once (server shows one row per item; Idempotency-Key unchanged).
7. **Duplicate matrix** — double-tap each save button; repeat the same
   queue entry / invoice / Rx; register the same name+phone twice offline
   and once on another device → server 409 → "Register anyway" / Discard
   flow; discard a registration with dependants (warning lists them).
8. **Session expiry** — revoke the session on the server while offline
   work exists → banner, work kept, syncs after signing in as the same
   user; signing in as a different user never sends the first user's ops.
9. **Sign-out** — with unsynced items shows the red warning; after
   confirming, patient list, drafts and PIN are gone (re-open the app).
10. **Store recovery** — clear the Keystore (Settings → Security → clear
    credentials, or restore app data onto another phone) → recovery screen,
    "Try again" / confirmed reset; no silent empty store.
11. **Low-RAM / process death** — with "Don't keep activities" on and on
    the ≤2 GB device: switch to camera/WhatsApp and back during data
    entry; the app returns to the PIN lock or the same tab and nothing
    already saved is lost; cold-start time < 4 s on the entry-level device.
12. **Battery optimisation** — on Xiaomi/Samsung with default battery
    settings, leave items pending, lock the phone for 30 min, reconnect;
    note whether sync waits for the app to be opened (background sync is
    not implemented yet — expected: syncs on next resume/unlock).
13. **Languages** — device language मराठी / हिंदी → app follows it;
    picker on login and home switches instantly and persists across
    restart; every screen fits without clipped text at the largest system
    font size; drug names, doses, frequency codes and UHIDs stay in Latin
    script; Devanagari renders correctly (no tofu boxes) on Android 8.
14. **Rural Clinic mode** — toggle in the menu; buttons/chips ≥ 56 dp
    (check with Developer options → Show layout bounds); larger text; only
    Register → Queue → Fast Rx → Bill tabs with Sync in the app bar;
    frequency/day chips fill the fields; setting persists across restart.
15. **Feature gating** — against a server whose `/auth/me` omits
    `billing` / `consultation` / `opd_queue` / `pharmacy` / `mobile_offline`
    the matching tab or field disappears; an older server without
    `features` shows everything.
16. **Accessibility** — TalkBack reads every button in all three
    languages; colour contrast of state chips; landscape on a tablet.
17. **Device revocation** — with unsynced items, revoke this device's
    session from the web (sessions list → revoke, or suspend the member);
    the app returns to sign-in with "This device was signed out by an
    administrator", the patient list is empty after re-opening; signing in
    as the SAME user brings the items back and they sync once (server shows
    one row each); a different user sees only the sealed count.
18. **Scanner** — camera permission prompt appears only on the scan
    screen; QR check-in (server with `qr_checkin`) and a GS1 DataMatrix on
    a medicine strip (batch + expiry shown) on the entry-level device;
    "Type the code" fallback works when the camera cannot focus.
19. **PDF** — Draft PDF opens the share sheet and shows the red
    "DRAFT - not valid until signed online" watermark; a signed Rx and a
    receipt print from server data only when online.
20. **Role interfaces** — sign in as doctor, receptionist, owner and
    pharmacist; each gets its own tab set; the Overview shows today's
    collections online and "Needs connection" offline.

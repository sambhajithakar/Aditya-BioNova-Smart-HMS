# Licences & Software Bill of Materials (SBOM)

Product licence: proprietary — owned by the Aditya BioNova company; this
repository's source is delivered to and controlled by the customer.
Third-party components below remain under their own terms.

**Policy:** permissive licences preferred; **no AGPL components** (see the
Bahmni note). Verify again before each release: `pip-licenses` /
`npm ls --all` (commands at the bottom).

Last full review: **2026-10-21 (M8.1)**. Every package in the three lock
files was checked against its installed metadata or LICENSE file.

## Python — API runtime (exact versions pinned in `apps/api/requirements.lock`, 2026-10-20)

| Package | Version | Licence | Commercial use |
|---|---|---|---|
| fastapi | 0.151.0 | MIT | ✅ |
| starlette | 1.9.0 | BSD-3-Clause | ✅ |
| uvicorn | 0.54.0 | BSD-3-Clause | ✅ |
| sqlalchemy | 2.1.5 | MIT | ✅ |
| alembic | 1.20.0 | MIT | ✅ |
| psycopg2-binary | 2.9.13 | **LGPL w/ exceptions** | ✅ dynamically linked, unmodified — compliant; re-evaluate only if statically bundling |
| pyjwt | 2.15.1 | MIT | ✅ |
| pydantic / pydantic-core | 2.14.1 / 2.50.1 | MIT | ✅ |
| pydantic-settings | 2.16.0 | MIT | ✅ |
| email-validator | 2.3.0 | Unlicense (public domain) | ✅ |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause (dual) | ✅ (MFA secret encryption) |
| cffi / pycparser (cryptography) | 2.1.1 / 3.11 | MIT-0 / BSD-3-Clause | ✅ |
| opentelemetry-api / annotated-doc (fastapi) | 1.45.1 / 0.0.5 | Apache-2.0 / MIT | ✅ |
| dnspython (email-validator) | 2.9.0 | ISC | ✅ |
| python-dotenv / pyyaml (pydantic-settings, uvicorn) | 1.2.4 / 6.0.3 | BSD-3-Clause / MIT | ✅ |
| certifi (transitive, dev/test via httpx) | 2026.10.19 | MPL-2.0 | ✅ unmodified; file-level copyleft only |
| typing-extensions | 4.16.0 | PSF-2.0 | ✅ |
| annotated-types / typing-inspection (pydantic) | 0.8.0 / 0.4.4 | MIT / MIT | ✅ |
| anyio / h11 (starlette, uvicorn) | 4.15.1 / 0.16.0 | MIT / MIT | ✅ |
| click / idna | 8.5.0 / 3.20 | BSD-3-Clause / BSD-3-Clause | ✅ |
| Mako / MarkupSafe (alembic) | 1.4.3 / 3.0.4 | MIT / BSD-3-Clause | ✅ |
| httptools (uvicorn[standard]) | 0.9.0 | MIT | ✅ |
| uvloop (uvicorn[standard]) | 0.23.0 | MIT **and** Apache-2.0 (dual-licensed; both permissive) | ✅ |
| watchfiles / websockets (uvicorn[standard]) | 1.3.0 / 17.3 | MIT / BSD-3-Clause | ✅ |

## Python — development only

| Package | Version | Licence |
|---|---|---|
| pytest | 9.1.1 | MIT |
| ↳ iniconfig / pluggy / packaging / pygments | 2.3.1 / 1.7.0 / 26.3 / 2.21.0 | MIT / MIT / Apache-2.0 OR BSD-2-Clause / BSD-2-Clause |
| httpx / httpcore (FastAPI TestClient) | 0.28.1 / 1.0.9 | BSD-3-Clause / BSD-3-Clause |
| certifi (httpx) | 2026.10.19 | MPL-2.0 (unmodified; file-level copyleft only) |
| ruff | 0.17.1 | MIT |
| pip-tools (lock generation, not installed in images) | 7.6.2 | BSD-3-Clause |

Dev/test versions are pinned in `apps/api/requirements-dev.lock`; both
lock files carry sha256 hashes and are regenerated with
`scripts/lock-api-deps.sh`.

## Node — web runtime (from `apps/web/package-lock.json`)

What `npm ci --omit=dev` installs in the web image:

| Package | Version | Licence |
|---|---|---|
| next | 15.5.27 | MIT |
| react / react-dom / scheduler | 19.3.0 / 19.3.0 / 0.28.0 | MIT |
| @next/env / styled-jsx / client-only / nanoid | 15.5.27 / 5.1.6 / 0.0.1 / 3.3.19 | MIT |
| @next/swc-linux-x64-musl (prebuilt compiler binary, optional dependency of next) | 15.5.27 | MIT |
| @swc/helpers / detect-libc | 0.5.15 / 2.1.2 | Apache-2.0 |
| postcss / source-map-js | 8.5.28 / 1.2.2 | MIT / BSD-3-Clause |
| picocolors / semver | 1.1.1 / 7.8.5 | ISC |
| tslib | 2.8.1 | 0BSD |
| caniuse-lite | **1.0.30001814** | CC-BY-4.0 (browser-support data; attribution retained in the package) |

**Not shipped (M8.1):**
- **sharp / libvips.** `sharp` 0.35.5 (Apache-2.0) is an optional dependency
  of next. It brings prebuilt **libvips binaries under LGPL-3.0-or-later**
  (`@img/sharp-libvips-*` 1.3.4).
  - The app uses no `next/image`, and `next.config.mjs` sets
    `images: { unoptimized: true }`.
  - The web Dockerfile deletes `node_modules/sharp` and `node_modules/@img`,
    and the build fails if any libvips binary remains.
  - `next start` was verified to serve the app without them.
  - They remain on developer machines only, through `npm ci`.
- **Playwright.** `@playwright/test` / `playwright` / `playwright-core`
  1.56.1 (Apache-2.0) is a devDependency and an optional peer of next. It is
  removed from the runtime image together with sharp.

### Web — development and test only (not shipped)

416 packages from `npm ci`, all under permissive or weak file-level licences:

| Licence | Packages |
|---|---|
| MIT | 353 |
| Apache-2.0 | 22 |
| ISC | 13 |
| MPL-2.0 | 13 (lightningcss and its platform binaries, used by vitest via vite; axe-core, used by eslint-plugin-jsx-a11y) |
| BSD-2-Clause | 9 |
| BSD-3-Clause | 2 |
| MIT-0, BlueOak-1.0.0, Python-2.0 (argparse), CC0-1.0 | 1 each |

No GPL or AGPL licence is present. Direct dev tools:
- typescript 5.9.3 (Apache-2.0)
- eslint 9.37.0 (MIT)
- vitest 5.0.3 (MIT)
- @testing-library (MIT)
- jsdom 26.1.0 (MIT)
- @playwright/test 1.56.1 (Apache-2.0)

## Dart / Flutter — Android app (exact versions in `apps/mobile/pubspec.lock`, verified from each package's LICENSE file and pub.dev licence tags, 2026-10-20)

| Package | Version | Licence | Use |
|---|---|---|---|
| Flutter SDK / Dart SDK | 3.47.7 / 3.13.5 | BSD-3-Clause | framework |
| http | 1.6.0 | BSD-3-Clause | API transport |
| intl / flutter_localizations | 0.20.3 / SDK | BSD-3-Clause | en / mr / hi |
| pointycastle | 4.0.0 | MIT | AES-256-GCM store, PBKDF2 PIN |
| flutter_secure_storage | 11.2.0 | BSD-3-Clause | Android Keystore |
| path_provider | 2.1.6 | BSD-3-Clause | store location |
| cupertino_icons | 1.0.9 | MIT | icons |
| **mobile_scanner** (new, M8) | 7.4.2 | BSD-3-Clause | QR check-in / medicine barcode scanner |
| ↳ Google ML Kit barcode scanning (Android native, pulled by mobile_scanner) | 17.3.0 | Google ML Kit Terms of Service (free, proprietary; on-device, no data sent) | ✅ commercial use permitted; keep attribution; re-check terms before release |
| **pdf** (new, M8) | 3.13.1 | Apache-2.0 | Rx draft / signed Rx / receipt PDFs |
| **printing** (new, M8) | 5.15.1 | Apache-2.0 | Android share / print sheet |
| ↳ pdf_widget_wrapper / barcode | 1.0.4 / 2.2.9 | Apache-2.0 | transitive |
| ↳ archive / image / bidi / xml / petitparser / posix | 4.5.2 / 4.12.0 / 2.0.13 / 7.0.1 / 7.0.2 / 6.5.2 | MIT | transitive |
| ↳ path_parsing / qr | 1.1.0 / 3.0.2 | MIT / BSD-3-Clause | transitive |
| ↳ yaml | 3.1.4 | MIT | transitive |
| ↳ jni / jni_flutter / jni_util / ffi / objective_c / win32 (platform channels used by plugins) | 1.1.0 / 1.0.4+1 / 1.0.0 / 2.2.0 / 9.5.0 / 6.4.0 | BSD-3-Clause | transitive |
| ↳ crypto / convert / typed_data / collection / async / meta / path / web / http_parser / logging / characters / vector_math | — | BSD-3-Clause (Dart team) | transitive |
| ↳ flutter_secure_storage_* / path_provider_* / plugin_platform_interface / platform / xdg_directories | — | BSD-3-Clause | platform implementations |
| ↳ material_color_utilities / clock | 0.13.0 / 1.1.3 | Apache-2.0 | transitive |
| ↳ hooks / code_assets / record_use / pub_semver / package_config / args | — | BSD-3-Clause | build hooks (build time) |
| fake_async / flutter_lints / lints / leak_tracker* / test_api / matcher / vm_service (dev only) | — | Apache-2.0 / BSD-3-Clause | tests / lints |

**Fonts and icons bundled in the APK**

| Asset | Licence | Note |
|---|---|---|
| MaterialIcons-Regular.otf (Flutter `uses-material-design: true`) | **CC-BY-4.0** (per Flutter's bundled `MaterialIcons_LICENSE.txt`) | Attribution required. It is listed in the in-app licence screen. |
| CupertinoIcons (cupertino_icons 1.0.9) | MIT | |
| Text font | — | The Android system font is used; no Roboto file is bundled by the app. |

**In-app notices (M8.1).**
- The Android app has a *Settings → Open-source licences* screen (Flutter
  `showLicensePage`). It lists every package's LICENSE, which the Flutter
  build collects into `NOTICES`, plus an explicit Google ML Kit attribution.
- The web app serves the same information at `/licenses`.

Re-check: `cd apps/mobile && flutter pub deps --style=compact` and read
`~/.pub-cache/hosted/pub.dev/<pkg>-<ver>/LICENSE` for every new package.

## System / infrastructure
- PostgreSQL 16 (database): PostgreSQL Licence ✅
- Docker images (`postgres:16.15-alpine`, `python:3.12.15-slim`, `node:22.23.3-alpine`, pinned by digest): upstream licences ✅
- CI tooling (not shipped): gitleaks (MIT), hadolint (GPL-3.0, run as a separate binary in CI only), pip-audit (Apache-2.0)

## Competitor-research provenance
No competitor source code, graphics or interface designs were copied.
Competitor study limited to publicly documented features (see
REQUIREMENTS.md and the source PDFs).

## Open-source note re: Bahmni (research finding)
Bahmni is a mixed-licence system (AGPL-3.0 / MPL-2.0 / MIT / LGPL across
components, with an in-progress licence migration — bahmni.org/license).
It is used **only as a workflow benchmark**. Copying any Bahmni/OpenMRS
code into this product is prohibited without a dedicated legal review; AGPL
components must never enter this dependency tree.

## Obligations checklist
- ✅ Keep copyright notices and licence texts of dependencies (auto-collected
  on release with the commands below).
- ✅ Deliver source of *our* product to the customer (this repository).
- 🟡 LGPL psycopg2: keep it dynamically linked (default pip install); do not
  patch it.
- ✅ In-app licence notices: Android *Open-source licences* screen; web `/licenses` (M8.1).
- ✅ LGPL libvips (sharp) kept out of the shipped web image (M8.1).
- ⬜ Per release: run the collectors, archive `pip-licenses --format=json` and
  `npm ls --all` output into `docs/compliance/`.

```bash
# release-time SBOM commands
.venv/bin/pip install pip-licenses && .venv/bin/pip-licenses --format=markdown
cd apps/web && npm ls --all --json > ../../docs/compliance/npm-sbom.json
```

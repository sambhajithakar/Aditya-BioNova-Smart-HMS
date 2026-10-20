# Device compatibility — web app (`apps/web`)

Status: **emulated testing only.** Every result below comes from Chromium
(Playwright 1.56, Chromium build 1194) with device emulation, CDP CPU
throttling and in-browser network shaping on one Linux development machine.
**No real phone, tablet, netbook, printer or non-Chromium browser was used.**
Emulation approximates screen size, touch input, a slower main thread and a
slow link. It does not reproduce a real device's GPU, memory pressure,
thermal throttling, OS font set, radio behaviour or vendor browser quirks.

Performance numbers are in [`PERFORMANCE_BENCHMARKS.md`](PERFORMANCE_BENCHMARKS.md).

## 1. What changed for devices

| Area | Phones (< 768 px) | Laptops / desktops |
|---|---|---|
| Navigation | Bottom bar with **Home + the role's 3 most-used modules + More**. *More* is a native `<dialog>` sheet with every other module, the language switch, *Log out* and the printer test page. Both are built only from the permission- and edition-gated nav list (`visibleNav`), so gating is unchanged. | Unchanged scrolling top nav. |
| Patient search | Search icon in the header: one tap opens Patients with the search box focused. | Header search box (`/` or `Ctrl/⌘+K`). The term is handed to the Patients page **in memory**, never in the URL or Web Storage. |
| Touch targets | Bottom bar items ≥ 64 × 44 px; page buttons ≥ 44 px; More-sheet links ≥ 48 px. | — |
| Primary actions | `.sticky-actions` keeps the action row above the bottom bar (used on patient registration). | — |
| Density | — | Tables are denser on fine-pointer screens ≥ 1024 px; pages widen to 1320 px on ≥ 1440 px screens; compact header on short screens (1024 × 600). |
| Keyboard | — | `/`, `Ctrl/⌘+K` search · `g` then `d p a q c b f l i r` → Dashboard, Patients, Appointments, Queue, Consultation, Billing, Pharmacy, Lab, IPD, Reports · `n` focuses the page's create form · `?` help dialog · `Esc` closes. Single-key shortcuts are ignored while typing in a field. A "Skip to main content" link is the first Tab stop. |
| Connectivity | Banner states *Reconnecting…* and *Offline*, plus a short *Back online*. | Same. |
| PWA | Installable (manifest, icons, standalone). | Same. |

Role → bottom-bar modules (`src/lib/device-nav.ts`); anything the member is not
permitted to use or whose module is not in the plan is skipped:

| Role | Bottom bar after Home |
|---|---|
| doctor | Queue, Consultation, Patients |
| nurse | Queue, IPD, Patients |
| receptionist | Patients, Appointments, Queue |
| pharmacist | Pharmacy, Inventory, Patients |
| lab_technician | Laboratory, Patients, Queue |
| billing | Billing, Patients, Reports |
| owner / admin | Patients, Queue, Billing |

## 2. Offline: the decision

**The web app does not do offline writes.** Payments, refunds and prescription
signing are finalised by the server: an Rx is only signed, and a payment only
taken, once the API has accepted it. Queueing those in the browser would mean:

* storing patient data in browser storage (forbidden by our PHI rule), and
* risking a duplicate charge or a "signed" prescription that the server never
  recorded.

So when the shell decides the app is **offline** (`navigator.onLine` false, or
3 consecutive failed requests / health probes), those buttons are disabled and a
trilingual note explains why (`NeedsConnection`). Reading the page that is
already open keeps working. Offline capture with an encrypted outbox is the
**Android app's** job (`apps/mobile`).

Connectivity detection (`src/lib/connectivity.ts`):

* `navigator.onLine` events (immediate *Offline*; *Online* is confirmed by a probe);
* the API client reports network-level failures and 502–504 gateway errors, and
  any other HTTP response as "reachable";
* `GET /api/v1/health` (liveness, unauthenticated, no patient data) every 60 s
  while healthy and visible, every 5 s while in trouble.

When the API is unreachable, the shell does not sign the member out. It stays on
the page and retries `/auth/me` when the connection returns. Before this change,
a token refresh that failed only because the network was down ended the session.
Real 401/403 responses still sign out as before.

## 3. Service worker and the patient-data rule

`public/sw.js` is about 150 lines, hand-written, with no dependencies. What it
caches and what it never caches:

| Request | Strategy | Cached? |
|---|---|---|
| `/api/**` (incl. `/api/session/*`) | not intercepted (browser default, network-only) | **never** |
| page navigations (HTML) | network; on network failure → `/offline.html` | **never** (pages are per-user and carry a per-request CSP nonce) |
| `/_next/static/**` (content-hashed JS/CSS) | cache-first | yes, `hms-static-<build>` |
| `/offline.html`, manifest, icons | pre-cached on install | yes, `hms-shell-<build>` |
| RSC payloads, POST/PUT, cross-origin | not intercepted | never |

* **Versioning:** the shell registers `/sw.js?v=<build id>` (`NEXT_PUBLIC_BUILD_ID`,
  set at build time from `GIT_SHA` or a timestamp). A new build installs a new
  worker that **waits**. A toast says "A new version is available — Reload", and
  only that click activates it (`SKIP_WAITING`). On activation every other `hms-*`
  cache is deleted.
* **Logout** also deletes every cache that is not the current build's static or
  shell cache. This is defence in depth, since no cache should ever hold user data.
* **CSP:** the existing nonce CSP already allows `worker-src 'self' blob:` and
  `manifest-src 'self'`. The worker, manifest, icons and offline page are
  excluded from the auth middleware (they hold no user data). `next.config.mjs`
  gives `/sw.js` `Cache-Control: no-cache` and a CSP. `/offline.html` gets a
  **script-free** CSP (`default-src 'none'; style-src 'unsafe-inline'`). The E2E
  specs record CSP violations and page errors on every page they visit and assert
  there are none.
* Registered only in production builds and secure contexts (HTTPS or
  `http://localhost`). The app works without it.

Verified by E2E (`e2e/device.spec.ts`): the worker controls the page; after
visiting Patients and Billing, Cache Storage holds only `/_next/static/**`,
icons, the manifest and `/offline.html`, with **zero `/api/` entries** and no
app HTML; Web Storage holds no token or patient data; a navigation with the
network cut is served `/offline.html` by the worker; logout leaves only
`hms-static-*` / `hms-shell-*` caches.

> Test-harness note: in this Chromium build, Playwright's `setOffline`, `route()`
> and CDP network emulation do **not** reach the service worker's own `fetch()`.
> The offline-fallback test therefore makes `fetch()` reject inside the worker
> (which is what a dropped connection does) and restores it afterwards.

## 4. Emulated device matrix (what was actually run)

| Profile | Viewport | Input | CPU | Network | Covered by |
|---|---|---|---|---|---|
| Entry Android phone | 360 × 640, DPR 2 | touch (`hasTouch`, `isMobile`) | 4× slowdown | Slow 3G (2 s RTT, 50 kB/s) and Fast 3G (563 ms, 180 kB/s) | `perf.spec.ts`; `device.spec.ts` (layout and touch, unthrottled) |
| Phone layout, other width | 390 × 844 | mouse | 1× | local | `smoke.spec.ts` (existing overflow check) |
| Laptop | 1366 × 768 | mouse + keyboard | 1× and 4× | local, Fast 3G | `perf.spec.ts`, `device.spec.ts` (keyboard) |
| Desktop | 1280 × 720 (Playwright "Desktop Chrome") | mouse + keyboard | 1× | local | all existing E2E specs |
| Tablet | 800 × 1280 | touch | 1× | local | `device.spec.ts`: top nav, no overflow on 5 pages, screenshots. It gets the **desktop** top nav because 800 ≥ 768. |
| Netbook | 1024 × 600 | mouse | 1× | local | `device.spec.ts`: top nav, compact header, no overflow on 5 pages, screenshots |
| Keyboard only | 1366 × 768 | keyboard | 1× | local | `device.spec.ts`: skip link, shortcuts, dialog focus and Esc |

Per-profile checks in `device.spec.ts`:

* **360 × 640 touch:** bottom bar visible and top nav hidden; every bar item at
  least 44 × 44 px; the search tap lands on Patients with the box focused; the More
  sheet opens, `Esc` closes it, and its links navigate and close it; **no horizontal
  overflow on 9 main pages in each of English, मराठी and हिंदी** (27 screenshots).
* **1366 × 768 keyboard:** the skip link is the first Tab stop and moves focus to
  the content; `/` focuses search; typing `g p` *inside* the search box does not
  navigate; Enter hands the term to Patients; `g q` and `g p` navigate; `n`
  focuses the registration form; `Ctrl+K` works; `?` opens the dialog and `Esc`
  closes it.
* **Accessibility (basic, no extra dependency):** on 8 main pages every visible
  input, select, textarea, button and link has an accessible name. This found and
  fixed the unnamed invoice line-item fields on Billing. Colour contrast of the
  design tokens (text and button pairs) is unit-tested against WCAG AA 4.5:1;
  all 10 pairs pass. Touch-target sizes are listed above.

## 5. Print

| Layout | How | Verified |
|---|---|---|
| A4 (default) | `@page { size: A4; margin: 14mm }` | Chromium PDF MediaBox 595 × 842 pt (`device.spec.ts`) |
| A5 | `@page { size: A5; margin: 10mm }`, tighter type | MediaBox 420 × 595 pt |
| 80 mm thermal roll (**receipts only**) | `@page { size: 80mm <measured>mm }`, 72 mm content width | MediaBox width 226.8 pt (80 mm), length < 600 pt, exactly one page |

* A paper picker (screen only) sits on `/print/rx/[id]` (A4 / A5) and on
  receipts (`?type=receipt`, A4 / A5 / 80 mm); `?paper=` in the URL selects it.
* `size: 80mm auto` is **not valid CSS**: Chromium silently printed Letter. The
  roll length is therefore measured from the rendered receipt (+10 % +12 mm),
  re-measured on resize and `beforeprint`, with a 297 mm fallback.
* **`/print/test`**, the printer test page: corner alignment marks, a 50 mm
  ruler, Latin, digit, ₹ and Devanagari glyphs, and a sample receipt with
  **synthetic data**, in all three paper sizes. It is linked from the More sheet
  and the `?` dialog.
* The prescription request waterfall was shortened: the patient and encounter
  are now fetched in parallel.
* **Not tested: physical printers.** No thermal or laser printer was available.
  Each clinic should print `/print/test` once per printer, using 100 % / "Actual
  size" and the driver's roll or continuous paper setting.

## 6. Screenshots

`npx playwright test e2e/device.spec.ts` writes to
`apps/web/test-results/device-shots/` (git-ignored, not committed):
`360-{en,mr,hi}_{dashboard,patients,queue,consultation,billing,pharmacy,lab,ipd,settings_security}.png`
`{tablet-800x1280,netbook-1024x600,laptop-1366x768}_{dashboard,patients,billing,consultation,ipd}.png`
and `print-test-{a4,a5,80mm}.png`.

## 7. Defects found by these tests (all fixed)

| Found by | Defect | Fix |
|---|---|---|
| Throttled phone benchmark (seeded data) | At 360 px a `nowrap` table's min-content width widened the page. Mobile Chrome then grew the layout viewport (to about 440 px) and the fixed bottom bar slid partly off-screen ("More" missing, taps blocked). The existing 390 px overflow check could not see this, because in mobile emulation `clientWidth` grows along with the content. | Grid and row children may shrink (`min-width: 0`), so tables scroll inside their card. The overflow check now compares against the device width, and the phone test seeds real patient rows. |
| Tablet / netbook sweep | The Billing invoice line table was about 1,440 px wide on **800–1366 px** screens, because inputs kept their ~20-character intrinsic width. | Form controls in table cells fill the cell (selects keep a readable minimum). |
| Named-controls check | Invoice line-item fields had no accessible names (visual column headers only). | `aria-label` per field, e.g. "Qty 1", from the same translated strings. |
| Offline test | A page opened while the API was unreachable sent the member to `/login`, since a failed refresh looked like an auth failure. | Unreachable ≠ unauthenticated: the page stays, the banner explains, and `/auth/me` is retried when the connection returns. |
| PDF print check | `@page { size: 80mm auto }` is invalid CSS and Chromium printed Letter. | Explicit, measured roll length. |

Pre-existing, environment-dependent: with `E2E_BASE_URL=http://127.0.0.1:…`
the existing smoke test's second tab (`/print/rx/…`) is redirected to `/login`
(SameSite=Strict cookies plus an IP origin). With `http://localhost:…`, as CI
uses, it passes. This happens on the baseline commit too and was not changed.

## 8. What was NOT tested

* Real hardware of any kind: entry Android phones, tablets, the 1024 × 600
  netbook, a real 4 GB RAM laptop, thermal or laser printers.
* Browsers other than Chromium: Firefox, Safari / iOS WebKit, Samsung Internet,
  old Android System WebView (< 90), and Edge or Chrome on Windows with real
  Windows fonts. Devanagari rendering depends on the OS font
  (Noto Sans Devanagari, Nirmala UI, Mangal, Kohinoor). The app no longer names
  a webfont it never shipped ("Inter") and uses the system stack.
* Screen readers (NVDA, TalkBack, VoiceOver): only the accessible-name and focus
  checks above were automated.
* PWA install prompts and standalone-window behaviour on real Android or desktop;
  iOS "Add to Home Screen".
* Real radio conditions: packet loss, captive portals, a link that flaps every
  few seconds.

## 9. Recommendations

1. Run `/print/test` on each clinic's printers during onboarding and record the
   driver settings that worked.
2. Smoke-test on one real entry Android phone (Chrome and the OEM browser) and
   one Windows 10 laptop with Edge before a rural rollout. Use the commands in
   `PERFORMANCE_BENCHMARKS.md` with remote debugging.
3. Add Firefox and WebKit Playwright projects to CI (layout, keyboard and print
   specs) once the browsers are available in CI.
4. Adopt an automated axe-core audit if a dependency is acceptable. The current
   checks are deliberately lightweight.

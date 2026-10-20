# Performance benchmarks — web app (`apps/web`)

**Emulated, not real hardware.** All numbers come from Playwright-driven
Chromium (build 1194) on one Linux development machine, with Chrome DevTools
Protocol CPU throttling (`Emulation.setCPUThrottlingRate`) and in-browser
network shaping (`Network.emulateNetworkConditions`). "4× CPU" means four times
slower than *this* machine, not a specific phone. Network profiles are the
DevTools presets: **Fast 3G** (563 ms RTT, 180 kB/s down) and **Slow 3G**
(2 s RTT, 50 kB/s down). The HTTP cache is disabled and the service worker is
blocked in every run, so every run is a cold load. Each figure is the
**median of 3 runs**. See [`DEVICE_COMPATIBILITY.md`](DEVICE_COMPATIBILITY.md)
for what was not tested.

## 1. How to reproduce

```bash
# live stack: API (FastAPI + PostgreSQL, seeded with scripts/seed_demo.py) and
# a production build of the web app (`npm run build && npx next start`)
cd apps/web
E2E_PERF=1 PERF_LABEL=after PERF_RUNS=3 \
E2E_BASE_URL=http://localhost:3120 E2E_API_URL=http://127.0.0.1:8120 \
E2E_CHROMIUM=/path/to/chromium \
  npx playwright test e2e/perf.spec.ts           # → test-results/perf/after.json
node scripts/perf-compare.mjs before.json after.json   # Markdown tables
```

* `e2e/perf.spec.ts` is **excluded from the default E2E run** (it takes about
  9 minutes). `playwright.config.ts` only includes it when `E2E_PERF=1`.
* Account: the synthetic seeded demo hospital owner
  (`owner@demo-hospital.example.com`, Hospital Advanced edition). Override with
  `PERF_EMAIL` / `PERF_PASSWORD`.
* **Baseline**: commit `ec79286` (tip of `claude/pensive-albattani-n0zcba`
  before this work), exported with `git archive`, built the same way and served
  on a second port. **Both builds were measured with the identical, final
  `perf.spec.ts`, back to back, against the same API and database.**

### Metrics

| Metric | Definition |
|---|---|
| Login FCP / LCP / load | `PerformanceObserver` paint + navigation timing on a cold `/login` |
| JS transferred | encoded bytes of `Script` responses (CDP `Network.loadingFinished`) |
| Sign in → dashboard | click *Sign in* → dashboard `<h1>` "Welcome…" visible |
| **Nav → X: data loaded** | click the module link → URL changed, heading visible, no "Loading…", **and the page's last `/api/v1` response** (no API request in flight for 1.5 s). This is the comparable "page is usable" time. |
| Total blocking time | sum of long-task time over 50 ms (`longtask` observer) over the whole session |
| JS heap | CDP `Runtime.getHeapUsage` after `HeapProfiler.collectGarbage`, at the end of the 8-module tour |

> Why "data loaded" and not "heading visible": the first comparison used only
> heading + no "Loading…". The baseline renders a page's heading *before even
> requesting its data* (the shell first waited for `/auth/me`), while the new
> build loads data in parallel and shows "Loading…" until it arrives. The
> heading-only metric therefore reported the new build as slower on
> Consultation, Pharmacy, Lab and IPD, while a request trace showed the
> baseline's data arriving later. Both columns are kept in the raw JSON
> (`navXMs` and `dataXMs`).

## 2. Results (baseline `ec79286` → this branch)

Module tour = Patients, Queue, Consultation, Billing, Pharmacy, Lab, IPD,
Reports, via the shell's links (on phones, modules outside the bottom bar go
through the More sheet, which is opened *before* the timer starts).

### Summary

| Profile | All 8 navigations, data loaded | Prefetched modules (Queue, Billing) | Sign in → dashboard | Login FCP | Login JS |
|---|---|---|---|---|---|
| Desktop 1366×768, no throttling | 2825 → **2338 ms (−17 %)** | 400 → 330 ms | 932 → 938 ms | 148 → 128 ms | 138.5 → 143.0 kB |
| Laptop 1366×768, 4× CPU, Fast 3G | 21 855 → **16 756 ms (−23 %)** | 2765 → 987 ms (−64 %) | 3041 → 3061 ms | 1312 → 1328 ms | same |
| Phone 360×640, 4× CPU, Fast 3G | 22 023 → **16 896 ms (−23 %)** | 2773 → 992 ms (−64 %) | 3091 → 3087 ms | 1340 → 1368 ms | same |
| Phone 360×640, 4× CPU, Slow 3G | 72 936 → **51 686 ms (−29 %)** | 8810 → 2407 ms (−73 %) | 9043 → 9096 ms | 4428 → 4552 ms | same |

Time to the page heading for the prefetched modules: ~2.0 s → **0.25 s** on
Fast 3G, and ~8.8 s → **0.2 s** on Slow 3G.

### Honest negatives

* **Login JS +4.5 kB** (138.5 → 143.0 kB, about +3 %): the device strings in
  three languages (+2.1 kB gzip in the shared i18n chunk), the connectivity
  and PWA helpers imported by the API client, and the small always-loaded shell
  parts. Login FCP/LCP and sign-in time are within run-to-run noise (±3 %).
* **The sign-in step transfers more JS (7.8 → 12.9–27.8 kB).** This is
  intentional: the lazily loaded device chrome chunk plus idle prefetch of the
  role's primary modules. That spending is what makes those modules open in
  ~0.25 s afterwards. It is skipped when the browser sends `Save-Data`.
* **IPD +7–8 % on Fast 3G (≈ +200 ms)** and Lab / IPD **+3 %** on Slow 3G.
  These are non-prefetched modules, where the change is within about one run's
  noise.
* **Total blocking time** is higher on two throttled profiles (laptop Fast 3G
  174 → 231 ms, phone Slow 3G 168 → 297 ms) and lower on the others. The extra
  main-thread work is pages rendering immediately (cached member) plus the
  prefetched route code being parsed during idle time.
* **JS heap +0.3–0.4 MB** after the module tour (4.7–4.8 → 5.0–5.1 MB).

### Build output (`next build`, First Load JS)

| Route | Before | After |
|---|---:|---:|
| shared by all | 103 kB | 103 kB |
| `/login` | 132 kB | 136 kB |
| `/dashboard` | 136 kB | 142 kB |
| `/patients` | 136 kB | 143 kB |
| `/queue` | 137 kB | 144 kB |
| `/consultation` | 140 kB | 146 kB |
| `/billing` | 139 kB | 145 kB |
| `/pharmacy` | 138 kB | 145 kB |
| `/lab` | 139 kB | 145 kB |
| `/ipd` | 139 kB | 146 kB |
| `/print/rx/[id]` | 108 kB | 110 kB |
| `/print/test` (new) | — | 131 kB |

The per-route *page* chunks got **smaller** (e.g. `/billing` 5.86 → 4.31 kB,
`/dashboard` 2.72 → 1.08 kB). The shell code used to be duplicated in every
page chunk and is now one shared chunk that is downloaded once and then cached.
The +6–7 kB "First Load" on app routes is that shared shell chunk (connectivity
banner, quick search, cached-member logic) plus the device strings. The bottom
bar, More sheet, keyboard shortcuts and update toast are in a separate **lazily
loaded** chunk (`next/dynamic`, after `/auth/me`), and the shortcuts dialog
loads only when `?` is pressed.

## 3. What was optimised (and why)

Measured first: a request trace of one module navigation under Fast 3G with
the cache disabled showed **four sequential round trips** in the baseline:
route payload → page chunk → `/auth/me` (every page mounts its own `<AppShell>`)
→ the page's data.

| Change | Effect |
|---|---|
| **Member cached in memory** for the page lifetime (`AppShell`): pages render at once; `/auth/me` re-validated only when older than 30 s, when a page reports a change, or when the connection returns. Never stored in Web Storage, cleared on logout and auth failure. | −1 round trip per navigation |
| **Idle prefetch of Home + the role's 3 primary modules** (`router.prefetch` in `requestIdleCallback`, once per 4 min, skipped on `Save-Data`) | −2 round trips for the most-used modules |
| **No blanket `<Link>` viewport prefetch** of the ~20 nav links and dashboard tiles. The trace showed them saturating Chrome's 6 connections per host and delaying the page's own requests. | removed a regression the member cache would otherwise have caused |
| **Member object identity kept** when the re-validated `/auth/me` is unchanged | every page's data had been fetched **twice** (found in the trace and fixed) |
| **Debounced patient search** (250 ms) with out-of-order response protection | one request per pause instead of one per keystroke; stale results can no longer overwrite newer ones |
| **Prescription print**: patient and encounter fetched in parallel | −1 round trip on `/print/rx/[id]` |
| **Lazy device chrome / shortcuts dialog** (`next/dynamic`) | keeps the always-loaded shell small |
| **System font stack**: the unused `"Inter"` webfont reference was dropped (no webfont was ever downloaded) | no font request; Devanagari uses OS fonts |
| **A login-page prefetch of the dashboard was tried and reverted**: it ran through the middleware before the session cookie existed and cached the redirect back to `/login` (caught by the E2E suite) | — |

Pagination: the list endpoints the pages call already pass `limit`
(`/patients?limit=20|100`, `/lab/orders?limit=100`,
`/pharmacy/stock/batches?limit=100`, `/encounters?…&limit=20`, …). The only
unbounded lists are small reference lists (`/branches`, `/ipd/wards`,
`/ipd/beds`, `/members`, `/plans`). No API change was made.

## 4. Measured but NOT done: per-language i18n bundles

Every page ships one i18n chunk with all three languages: **25.4 kB gzip
(101 kB raw); Marathi + Hindi strings are 14.3 kB gzip of it (56 %)**,
measured by stripping the Devanagari string literals and re-compressing.
Loading only the active language would save about 14 kB gzip on every cold load
for English users (≈ 0.3 s on Slow 3G) and about 7 kB for Marathi or Hindi users.

It was **deferred** because it means restructuring the 1,100-line shared
`src/lib/i18n.ts` into per-language modules with an async loader. Parallel
workstreams edit that file, so the merge-conflict risk was judged too high for
this branch. Suggested plan for the integrator, after merging: split
`coreDictionaries` / `saas` / `ai` / `device` into `i18n/{en,mr,hi}.ts`, keep
`en` static, `import()` `mr`/`hi` in `LangProvider` (the UI already shows
English until `LangProvider` has read the saved language on mount), and keep
the key-parity tests.

## 5. Raw results

The JSON for the final comparison is produced by the commands above (not
committed, being machine-specific). Full tables from
`node scripts/perf-compare.mjs`:

<details><summary>All metrics, all profiles (data-loaded variant)</summary>

#### desktop-1366x768-nothrottle

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Login: JS transferred (bytes) | 138506 | 142998 | +3 % |
| Login: FCP (ms) | 148 | 128 | -14 % |
| Login: load event (ms) | 173 | 173.7 | +0 % |
| Sign in → dashboard heading (ms) | 932 | 938 | +1 % |
| Sign-in step: JS transferred (bytes) | 7808 | 27755 | +255 % |
| Nav → Patients: data loaded (ms) | 176 | 110 | -38 % |
| Nav → Queue: data loaded (ms) | 400 | 332 | -17 % |
| Nav → Consultation: data loaded (ms) | 402 | 345 | -14 % |
| Nav → Billing: data loaded (ms) | 400 | 330 | -18 % |
| Nav → Pharmacy: data loaded (ms) | 401 | 349 | -13 % |
| Nav → Lab: data loaded (ms) | 403 | 352 | -13 % |
| Nav → IPD: data loaded (ms) | 405 | 357 | -12 % |
| Nav → Reports: data loaded (ms) | 193 | 132 | -32 % |
| All 8 navigations, data loaded (ms) | 2825 | 2338 | -17 % |
| Total blocking time (ms) | 5 | 0 | — |
| JS heap after GC (MB) | 4.7 | 5 | +6 % |

#### laptop-1366x768-cpu4x-fast3g

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Login: JS transferred (bytes) | 138506 | 142998 | +3 % |
| Login: FCP (ms) | 1312 | 1328 | +1 % |
| Login: load event (ms) | 2198 | 2257.7 | +3 % |
| Sign in → dashboard heading (ms) | 3041 | 3061 | +1 % |
| Sign-in step: JS transferred (bytes) | 7808 | 16615 | +113 % |
| Nav → Patients: data loaded (ms) | 2505 | 2131 | -15 % |
| Nav → Queue: data loaded (ms) | 2765 | 987 | -64 % |
| Nav → Consultation: data loaded (ms) | 2760 | 2435 | -12 % |
| Nav → Billing: data loaded (ms) | 2753 | 1013 | -63 % |
| Nav → Pharmacy: data loaded (ms) | 3094 | 3013 | -3 % |
| Nav → Lab: data loaded (ms) | 2771 | 2231 | -19 % |
| Nav → IPD: data loaded (ms) | 2746 | 2931 | +7 % |
| Nav → Reports: data loaded (ms) | 2459 | 2043 | -17 % |
| All 8 navigations, data loaded (ms) | 21855 | 16756 | -23 % |
| Total blocking time (ms) | 174 | 231 | +33 % |
| JS heap after GC (MB) | 4.7 | 5.1 | +9 % |

#### phone-360x640-cpu4x-fast3g

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Login: JS transferred (bytes) | 138506 | 142998 | +3 % |
| Login: FCP (ms) | 1340 | 1368 | +2 % |
| Login: load event (ms) | 2243.2 | 2246.7 | +0 % |
| Sign in → dashboard heading (ms) | 3091 | 3087 | -0 % |
| Sign-in step: JS transferred (bytes) | 7808 | 16615 | +113 % |
| Nav → Patients: data loaded (ms) | 2504 | 2088 | -17 % |
| Nav → Queue: data loaded (ms) | 2773 | 992 | -64 % |
| Nav → Consultation: data loaded (ms) | 2762 | 2435 | -12 % |
| Nav → Billing: data loaded (ms) | 2752 | 983 | -64 % |
| Nav → Pharmacy: data loaded (ms) | 3134 | 3022 | -4 % |
| Nav → Lab: data loaded (ms) | 2798 | 2227 | -20 % |
| Nav → IPD: data loaded (ms) | 2791 | 3027 | +8 % |
| Nav → Reports: data loaded (ms) | 2496 | 2123 | -15 % |
| All 8 navigations, data loaded (ms) | 22023 | 16896 | -23 % |
| Total blocking time (ms) | 224 | 214 | -4 % |
| JS heap after GC (MB) | 4.8 | 5.1 | +6 % |

#### phone-360x640-cpu4x-slow3g

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Login: JS transferred (bytes) | 138506 | 142998 | +3 % |
| Login: FCP (ms) | 4428 | 4552 | +3 % |
| Login: load event (ms) | 7115.1 | 7231.4 | +2 % |
| Sign in → dashboard heading (ms) | 9043 | 9096 | +1 % |
| Sign-in step: JS transferred (bytes) | 7808 | 12986 | +66 % |
| Nav → Patients: data loaded (ms) | 9659 | 6379 | -34 % |
| Nav → Queue: data loaded (ms) | 8810 | 2407 | -73 % |
| Nav → Consultation: data loaded (ms) | 8840 | 6963 | -21 % |
| Nav → Billing: data loaded (ms) | 8801 | 2454 | -72 % |
| Nav → Pharmacy: data loaded (ms) | 10867 | 9057 | -17 % |
| Nav → Lab: data loaded (ms) | 8838 | 9105 | +3 % |
| Nav → IPD: data loaded (ms) | 8815 | 9046 | +3 % |
| Nav → Reports: data loaded (ms) | 8365 | 6320 | -24 % |
| All 8 navigations, data loaded (ms) | 72936 | 51686 | -29 % |
| Total blocking time (ms) | 168 | 297 | +77 % |
| JS heap after GC (MB) | 4.8 | 5.1 | +6 % |

</details>

## 6. Recommendations

1. Split the i18n bundle per language (§4): about −14 kB gzip per cold load.
2. Move `<AppShell>` into a route-group `layout.tsx` so it is not remounted on
   every navigation. That would remove the member cache entirely and is the
   structural fix for the remaining per-navigation work. It touches every page
   file, so it is best done as its own change.
3. Reduce the second wave of requests on Consultation, Pharmacy, Lab and IPD
   (pickers loading `patients?limit=100` alongside the page data). A
   server-side search picker would let these pages skip the 100-row list.
4. Re-run this benchmark on a real entry-level Android phone (Chrome remote
   debugging) and a real 4 GB Windows laptop before quoting numbers externally.

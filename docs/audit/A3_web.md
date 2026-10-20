# Web frontend audit — apps/web (Next.js)

Scope: everything under `apps/web/src` (14 pages, `components/AppShell.tsx`, `lib/api.ts`, `lib/auth.ts`, `lib/i18n.ts`, `globals.css`), plus `package.json`, `next.config.mjs`, `tsconfig.json` and `infra/docker/web.Dockerfile`. I cross-checked every API path, query parameter and request body against `packages/contracts/openapi.json` and the backend routers. The audit was static and read-only: I did not run a build or open a browser. Paths below are relative to `apps/web/src` unless noted.

Size: about 5,400 lines of TSX/TS across 14 route files. The biggest pages are `ipd` (765 lines), `lab` (725), `consultation` (583), `pharmacy` (578) and `billing` (562). Each is a single client component holding 15–30 `useState` hooks.

---

## 1. Verified working (by reading the code)

- **API paths and request bodies match the contract.** All 70-odd call sites hit endpoints in `openapi.json`. The request bodies send only fields allowed by the `additionalProperties:false` schemas (PatientIn, AppointmentIn, QueueJoinIn, PrescriptionIn/RxItemIn, InvoiceIn, PaymentIn, DispenseIn, ReceiveStockIn, AdmissionIn, TransferIn, DischargeIn, NursingRecordIn, InventoryItemIn/MovementIn, ExpenseIn, WardIn, BedIn, LabOrderIn, ImportResultsIn, AmendResultIn). The one query-parameter mismatch is listed under D3.
- **Same-origin API proxy.** `next.config.mjs` rewrites `/api/v1/*` to `API_ORIGIN`, so the browser needs no CORS.
- **Typed client.** `lib/api.ts` keeps hand-written types that line up with the OpenAPI `*Out` schemas (money fields are `number` in both). `ApiError` carries the status and the server's `detail`.
- **Duplicate-aware patient registration.** A 409 shows the matching candidates and asks for explicit confirmation (`app/patients/page.tsx:71-79, 243-252`).
- **Allergy gate on signing a prescription.** Server warnings are fetched before signing, and a blocking warning needs an acknowledgement checkbox (`app/consultation/page.tsx:176-188, 514-551`).
- **i18n key parity.** The EN, MR and HI dictionaries each define the same 214 keys, and no key is used that isn't defined. 16 keys are defined but unused (`m1Notice`, `addItem`, `draftRx`, `issueInvoice`, `refund`, `verified`, `released`, …).
- **Trilingual print labels.** The print view renders EN/MR/HI labels side by side and uses the browser's print-to-PDF (`app/print/rx/[id]/page.tsx:18-51`).
- **Basic accessibility.** Most form controls have `<label htmlFor>`, errors use `role="alert"`, there is a `:focus-visible` outline (`globals.css:36`), the language buttons are 40 px or larger with `aria-pressed`, and the nav has `aria-label`.
- **Dependencies are current.** The lockfile pins next 15.5.27, react/react-dom 19.3.0 and typescript 5.9.3. None of these is in a known-vulnerable range (CVE-2025-29927 middleware bypass affects <15.2.3; the RSC/"React2Shell" CVE-2025-55182 line is fixed well before 15.5.27). The app has only 3 runtime dependencies, so the supply-chain surface is small.
- **TypeScript is `strict: true`.** CI runs `npm run typecheck` and `npm run build` (`.github/workflows/ci.yml:51-69`).

---

## 2. Defects

Severity: **C** = critical (patient safety, data integrity or security), **H** = high, **M** = medium, **L** = low.

### Security / auth

| # | Sev | Where | Defect |
|---|---|---|---|
| S1 | H | `lib/auth.ts:20-29` | The access token **and the refresh token** are kept in `localStorage`. Any XSS (or a malicious npm dependency or browser extension) can steal a long-lived refresh token and mint sessions for PHI access. This is acknowledged as an "M1 trade-off" in `SECURITY_CHECKLIST.md:37`, but it is still unfixed after M6. |
| S2 | H | `lib/api.ts:22-26`; nothing calls `/auth/refresh` | **There is no refresh handling.** The access token lives 1800 s (`apps/api/app/config.py:31`). On the first 401 the client wipes the tokens and the shell redirects to `/login`, so staff are logged out every 30 minutes and lose any half-filled form (Rx, invoice, discharge summary). The refresh token is stored but never used, and there is no single-flight refresh or retry. |
| S3 | H | `components/AppShell.tsx:39-45`, every page | **Route protection exists only in the browser.** There is no `middleware.ts` and no server-side check. `AppShell` renders `children` before `/auth/me` resolves, so each page mounts and fires its data requests unauthenticated, then redirects. Pages don't distinguish 401 from other errors (they show "Could not load…"). Data is protected by the API, but the UX leaks the page layout and produces a burst of 401s. |
| S4 | H | `next.config.mjs` (no `headers()`), `app/layout.tsx` | **No CSP and no security headers** for the web origin: no Content-Security-Policy, X-Frame-Options/frame-ancestors (the clickjackable billing and Rx-sign screens), Referrer-Policy, Permissions-Policy or HSTS, and `poweredByHeader` is left on. Combined with S1, the lack of a CSP removes the main defence against token theft. |
| S5 | M | entire UI | **The UI ignores RBAC.** `me.permissions` is only printed on the dashboard (`app/dashboard/page.tsx:133`). The nav (`AppShell.tsx:8-21`) and every action button (sign Rx, void invoice, verify/release lab result, discharge, void expense) are shown to every role, and users only find out from a 403 after clicking. |
| S6 | M | `infra/docker/web.Dockerfile` | The container runs as **root**. There is **no `.dockerignore`** at the repo root, so `COPY apps/web/ .` copies the host's `node_modules`, `.next` and any `apps/web/.env*` into the image, overwriting the `npm ci` result. The runtime image ships the full build tree with devDependencies (no `output:"standalone"`), and there is no HEALTHCHECK. |
| S7 | M | `next.config.mjs:2-13`, `infra/docker/docker-compose.yml:43-44` | `API_ORIGIN` is set only as a **runtime** environment variable in compose. Rewrites are compiled into the routes manifest at `next build`, so the image probably proxies to the default `http://127.0.0.1:8000` inside the web container, and the API would be unreachable. This needs a `docker compose up` to confirm; the fix is a build `ARG`. |
| S8 | L | `app/consultation/page.tsx:557,569`, `app/billing/page.tsx:527` | `target="_blank"` links have no `rel="noopener"`. These are same-origin links, so the risk is minor. |

### Clinical / functional correctness

| # | Sev | Where | Defect |
|---|---|---|---|
| D1 | **C** | `app/consultation/page.tsx:428-432, 452-457` | **The doctor cannot set dose, frequency or duration.** Every drug added is hard-coded to `"1 tablet"`, `"TDS"`, 5 days, and the table cells are read-only text. Every signed prescription says "1 tablet TDS × 5 days" whatever the drug (syrups, insulin, once-daily drugs). Route, quantity and instructions are never sent either. This is a patient-safety bug in a "signed, immutable" Rx. |
| D2 | **C** | `app/print/rx/[id]/page.tsx:77-78, 243` | The printed Rx looks up drug names from `/prescriptions/drugs?limit=200`, which returns active drugs only and at most 200. If a drug is deactivated or falls outside the first 200, **the printed prescription shows "—" for the medicine name**. The print also has **no prescriber name, qualification or registration number, and no clinic name or address**: it prints the hard-coded product name (`:193`) and `prescriber_user_id` is discarded (`:274`). Those are required on Indian prescriptions (NMC / Drugs & Cosmetics Rules). |
| D3 | H | `app/consultation/page.tsx:68, 79-86, 220` | The page sends `/encounters?status=open`, but the API parameter is **`enc_status`** (`apps/api/app/routers/encounters.py:166`), so the filter is ignored. The workspace always opens the **most recent encounter of any status**, and the "Start consultation" form only shows when `!open`. Once the newest encounter is completed, the doctor is stuck on a frozen encounter and cannot start a new one. Nothing is scoped to the doctor either, so two doctors see the same encounter. |
| D4 | H | `app/consultation/page.tsx:61-95, 454` | Every keystroke in the drug search reloads patients, queue, encounters and drugs, and resets the open encounter. Names in the draft-items table are resolved from the *current search results*, so they go blank when the query changes. |
| D5 | H | `app/consultation/page.tsx:166-193` | Every "Sign" click creates a **new draft prescription** before the warnings check. Retrying after a blocking warning leaves orphan drafts. |
| D6 | H | `app/pharmacy/page.tsx:150, 178`; `app/ipd/page.tsx:178`; `app/expenses/page.tsx:104`; `app/queue/page.tsx:559` | **Idempotency keys are built from business data, not per attempt.** The server stores keys permanently and either replays the stored response or returns 409 (`apps/api/app/services/clinical.py:140-170`). Legitimate repeats are therefore silently dropped or rejected: a second partial dispense of an Rx with the same item count (`web-disp-{rx}-{n}`); a second delivery under the same batch number; re-admitting the same patient to the same bed; two expenses with the same category, amount and date; the same patient re-queued on the same day (the old token is returned). The UI shows success on a replay. |
| D7 | H | `app/billing/page.tsx:136-140` | Manual (cash/UPI/card) payments carry **no Idempotency-Key**, and no button is disabled while a request is in flight, so a double-click records two payments. The same missing busy-state applies to almost every action button in the app. |
| D8 | H | `app/billing/page.tsx` (header comment `:5` claims refunds) | **There is no refund UI**, even though `POST /billing/payments/{id}/refund` exists. There is also no UI for failing a sandbox payment (`/payments/{id}/fail`), viewing the ledger, or amending an Rx (`/prescriptions/{id}/amend`). |
| D9 | M | `app/appointments/page.tsx:30-31`, `app/queue/page.tsx:32`, `app/billing/page.tsx:62`, `app/consultation/page.tsx:65`, `app/lab/page.tsx:101`, `app/pharmacy/page.tsx:101`, `app/ipd/page.tsx:103` | Patient pickers are `<select>` lists of the first 50–100 patients (the API caps at 100, so `limit=200` silently returns 100). **Patients after the first 100 cannot be booked, queued, billed, admitted or given a lab order.** Rows for other patients show raw UUID fragments. There is no type-ahead patient search outside `/patients`. |
| D10 | M | `app/appointments/page.tsx:337` | The appointment time is built with a hard-coded `+05:30`, and the list renders with `toLocaleString()` in browser locale (`:455`). |
| D11 | M | `app/appointments/page.tsx:407` | The appointment **date** field is labelled `t("dob")` ("Date of birth"). |
| D12 | M | `app/queue/page.tsx:622` | The priority select is labelled `t("status")`. |
| D13 | M | `app/queue/page.tsx:28-37` | The "live" queue board has no polling, SSE or WebSocket; it only refreshes after the user acts. |
| D14 | M | `app/lab/page.tsx:200-204` | The amend request sends the *import form's* `iFlag`, not a flag chosen for the amendment. Text values are coerced with `Number()`, giving NaN, which serialises to null. `importableTests` (`:234`) lists the whole catalog, not just the tests on the order. |
| D15 | M | `app/billing/page.tsx:106`, `app/consultation/page.tsx:101` | The branch is always `branches[0]`; the user's `me.branch_id` is ignored. In multi-branch orgs, invoices and encounters land in the wrong branch. |
| D16 | M | `app/billing/page.tsx:168-170, 264-301` | The client preview ignores the discount. `Number("")` gives 0 and `Number("1.")` gives NaN shown in inputs. Money is handled as JS floats. The "Take payment (cash)" label (`:470`) ignores the selected method. Payment controls show for `paid` invoices (`:441`). |
| D17 | M | `app/patients/page.tsx:39-52, 107-111` | A search request fires on every keystroke with no debounce or AbortController, so out-of-order responses can show stale results. There is no edit/PATCH patient UI and no merge UI, although both APIs exist. There is no pagination. |
| D18 | M | `app/dashboard/page.tsx` (whole file) | The **dashboard is a stub**. It does not use `AppShell` and has its own 4-item nav (`:9-14`), so billing, lab, IPD and the other modules are unreachable from the landing page except by URL. The KPIs are hard-coded `"—"` (`:110-115`), and a developer "Module checklist" says M3 is not done (`:141-148`). It also duplicates the header and language switcher from AppShell. |
| D19 | M | `components/AppShell.tsx:22,49-55` and every page's `useEffect(() => setLang(getLang()))` | **Switching language doesn't translate the page body.** AppShell keeps its own `lang` state, and each page reads `getLang()` only once on mount. There is no context or store, so only the header and nav change until a full reload. |
| D20 | L | `components/AppShell.tsx:69-78` | The nav uses plain `<a href>` instead of `next/link`, so every navigation is a full page reload that re-fetches `/auth/me` and loses all state. |
| D21 | L | `app/print/rx/[id]/page.tsx` | There is no auth or AppShell. The receipt view has no Print button (only the Rx has one, `:278-285`). The A5 media query (`:316-318`) never fires as intended. Dates are forced to `en-IN`. The `amendments` line prints English only (`:268`). |
| D22 | L | `app/ipd/page.tsx:89-90` | `nurseId` is dead state. The nursing-record cache (`:166`) never invalidates for other users' entries. |
| D23 | L | `app/login/page.tsx:107-110`; `app/layout.tsx:6-7` | Developer text is shown to customers ("Register via `POST /api/v1/auth/register` (self-serve onboarding ships in M2)"; the meta description says "foundation build (M1). Synthetic data only."). Error strings are English-only (`:33-40`). |

### Styling / accessibility / responsiveness

| # | Sev | Where | Defect |
|---|---|---|---|
| U1 | H | `globals.css:130-137` | `button.ghost` has `color: var(--white)` with a transparent background. It was designed for the navy header but is used on **white cards** throughout: patient-name buttons (`patients:128-134`), queue Call/Start/Skip (`queue:669-676`), appointment Cancel, the invoice Receipt/Void buttons, drug "+" chips and row ✕ buttons. They render **white on white, invisible**, which fails WCAG 1.4.3 and breaks the main workflows visually. Needs a browser check, but the CSS is unambiguous. |
| U2 | M | `globals.css` | There are no styles for `table`, `select`, `div.field`, `input[type=date/time]`, or `input` without a `type` attribute (`input[type="text"]` doesn't match a missing attribute). Most inputs render with browser defaults. `.label` and `a.primary` are unstyled, so the billing "Print receipt" link looks like plain text. |
| U3 | M | `globals.css` (zero `@media` rules); `app/patients/page.tsx:100` | **The layout isn't responsive.** There are no breakpoints, and patients uses inline `gridTemplateColumns: "1fr 1fr"`, which never collapses. Wide tables (billing lines, lab, IPD) have no `overflow-x` wrapper and overflow on phones and tablets. |
| U4 | M | `app/layout.tsx:12` | `<html lang="en">` is fixed and is never updated to `mr` or `hi`, so screen readers mispronounce Devanagari and hyphenation is wrong. |
| U5 | L | many | Icon-only buttons (✕) have no `aria-label`. Tables have no `<caption>` or `scope`. Async notices aren't in `aria-live` regions. Status enums (`waiting`, `issued`, …) are shown raw in English. Vitals label "DBP" (`consultation:318`) and "BP" (`:350`) are hard-coded. |

### i18n completeness

- The dictionaries are complete, with the same keys in all three languages (see section 1).
- **About 70 hard-coded English strings bypass `t()`.** These are every `setError("…")` and `setNotice("…")`, empty-table messages ("No patients yet.", "Queue is empty.", "No invoices yet.", "All items healthy.", "No expenses booked in this period."), and labels such as `"Advice"` (`consultation:486`), `"Type"` (`billing:217`), `"— from"`/`"to"` (`reports:532,541`), the `"Print / Save as PDF"` button, gender and blood-group options, priority `normal`/`urgent`, and line-item types. Error text coming from the API is English.
- Stale notices: `m2Notice` on Patients (`patients:98`), `m3Notice` on Billing and Consultation, `m5Notice` on Pharmacy and Lab. These are milestone banners shown in production screens.
- `lib/i18n.ts:4-5` itself says "Minimal M1 dictionary … Full workflow translation is P0 for milestone M4". No native-speaker QA has been done (`TASKS.md:38`).

### Architecture / code quality

- **No component library and no shared components** apart from `AppShell`. The same patient `<select>`, `patientLabel`, `fail()`/error-banner, branch loading, `type Lang` declaration (copied into 11 files) and inline `style={{…}}` blocks are repeated in every page.
- **No form library and no client-side validation** (no zod or react-hook-form). Validation is ad-hoc `if (!x) setError("…")`, and vitals have no range checks in the client.
- **No data layer.** There's no React Query/SWR, no caching, no cancellation, and every action does a full `load()` that re-fetches 4–5 endpoints.
- **No `error.tsx`, `not-found.tsx` or `loading.tsx`** boundaries. Every page is `"use client"`, so nothing uses server rendering.
- **There are no tests of any kind.** No unit tests (Jest/Vitest), component tests or Playwright/E2E; no `test` script in `package.json`; no ESLint config or `lint` script, even though the code contains `eslint-disable` comments (`consultation:94`, `expenses`). The README's CI "lint" claim covers only the API.

---

## 3. Documentation claims that are false or stale

| Claim | Reality |
|---|---|
| `README.md:23` "Next.js 15 web portal (login/dashboard shell)" | Stale in the other direction: there are 12 modules now, but the dashboard is still a shell (D18). |
| `README.md:27` / `DEPLOYMENT.md:62` "CI (lint, …, web build)" | The web job has no lint and no tests (`ci.yml:51-69`). |
| `TASKS.md:13` and the dashboard "✅ … refresh rotation" | The backend supports it; **the web client never refreshes** (S2). |
| `TASKS.md:27-28` "/queue (live board …)" | No live updates (D13). |
| `TASKS.md:30` "i18n: full M2 workflow strings in EN/मराठी/हिंदी" | About 70 English strings are hard-coded; switching language doesn't re-render pages (D19). |
| `TASKS.md:53-56` "printable A4 trilingual Rx … full E2E acceptance chain tested"; "/billing (invoice → issue → payment → receipt)" | The E2E chain is API-only: Playwright is still unchecked (`TASKS.md:36,62`). The Rx print lacks prescriber and clinic identity and can drop drug names (D2). |
| `TASKS.md:55` "/consultation (vitals, diagnosis, safety-gated signing)" | It works only for the first encounter. The wrong filter parameter makes it stick to completed encounters (D3), and dose/frequency can't be edited (D1). |
| `billing/page.tsx:5` "take payments … refund" | No refund UI (D8). |
| `TASKS.md:15` "design system" | One 163-line CSS file with no table, select or responsive rules, and the ghost-button contrast bug (U1–U3). |
| `TASKS.md:134,165` "Live flow verified through the web origin" | This was API calls through the proxy, not UI automation; there are no tests in the repo. |
| `package.json:5` "web portals (reception, doctor, admin)" | There is no admin portal (see section 4). |
| `SECURITY_CHECKLIST.md:32` "security headers" | API only; the web origin sends none (S4). |
| `lib/auth.ts:6-9` "Milestone M4/M7 should move refresh tokens to httpOnly cookies" | Unchanged through M6. |

---

## 4. Missing entirely (commercial HMS expectations)

- **Admin / settings.** No organization profile, branch management (`/branches` POST unused), clinic letterhead or doctor registration details for prints, tariff or price master, drug catalog admin, lab test master, tax/GST settings, or invoice-number settings.
- **User and role management.** `/members` GET/POST and `/audit-events` exist in the API but have no UI. There is no invite flow, password reset, MFA, session list or role assignment.
- **SaaS commercial layer.** No signup or onboarding wizard (the login page tells users to POST to the API), and no plans, subscription, trial, usage metering, invoices for the SaaS tenant, or tenant export/offboarding.
- **Patient portal.** No patient login, appointment self-booking, viewing Rx or lab reports, or online payment.
- **Dashboards and analytics.** The dashboard KPIs are placeholders. There are no charts, trends, doctor-wise or department-wise revenue, OPD footfall, or CSV/Excel/PDF export. Reports are a single summary page.
- **Appointment calendar and scheduling.** There is only a flat list of 50 rows: no calendar or day/week view, provider schedules or slots, reschedule UI (PATCH supports `starts_at`), provider selection (`provider_user_id` is never sent), or SMS/WhatsApp reminders.
- **Patient record (EMR) view.** No longitudinal patient chart that brings encounters, Rx history, lab results, invoices and admissions together. There's no lab report print, no discharge summary print, and no IPD billing.
- **Audit-log viewer, notifications centre, global search, keyboard shortcuts for reception speed, and offline/PWA support for the web.**
- **Quality infrastructure.** No unit or E2E tests, linting, Storybook, error monitoring (Sentry), or analytics/telemetry.

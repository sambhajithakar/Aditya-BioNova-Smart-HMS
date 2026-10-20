/**
 * Performance benchmark (NOT part of the default E2E run — see
 * playwright.config.ts; run with E2E_PERF=1). Drives the LIVE stack in
 * Chromium with CDP CPU + network throttling and records, per emulated
 * device profile:
 *   - login page: FCP, LCP, DOMContentLoaded, JS bytes transferred
 *   - sign-in → dashboard heading visible (ms), JS bytes for that step
 *   - client-side navigation to each main module (ms to its heading)
 *   - total blocking time (sum of long-task time over 50 ms)
 *   - JS heap used after a forced GC at the end (CDP Runtime.getHeapUsage)
 * Results are printed and written to test-results/perf/<label>.json.
 *
 * Emulation is NOT real hardware: Chromium's CPU throttle slows the main
 * thread relative to this machine, and the network profile is applied in the
 * browser (latency + throughput), not on a real radio link.
 *
 *   E2E_PERF=1 PERF_LABEL=after npx playwright test e2e/perf.spec.ts
 * Account: the synthetic seeded demo hospital owner (scripts/seed_demo.py);
 * override with PERF_EMAIL / PERF_PASSWORD.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test, type CDPSession, type Page } from "@playwright/test";

const EMAIL = process.env.PERF_EMAIL || "owner@demo-hospital.example.com";
const PASSWORD = process.env.PERF_PASSWORD || "Demo-Sunrise-2026!";
const LABEL = process.env.PERF_LABEL || "run";
const RUNS = Number(process.env.PERF_RUNS || 3);

type Net = { latency: number; down: number; up: number } | null;
type Profile = {
  name: string;
  viewport: { width: number; height: number };
  cpu: number;
  net: Net;
  touch: boolean;
};

// Chrome DevTools presets ("Slow 3G" / "Fast 3G"), bytes per second.
const SLOW_3G: Net = { latency: 2000, down: 50_000, up: 50_000 };
const FAST_3G: Net = { latency: 563, down: 180_000, up: 84_375 };

const PROFILES: Profile[] = [
  { name: "desktop-1366x768-nothrottle", viewport: { width: 1366, height: 768 }, cpu: 1, net: null, touch: false },
  { name: "laptop-1366x768-cpu4x-fast3g", viewport: { width: 1366, height: 768 }, cpu: 4, net: FAST_3G, touch: false },
  { name: "phone-360x640-cpu4x-fast3g", viewport: { width: 360, height: 640 }, cpu: 4, net: FAST_3G, touch: true },
  { name: "phone-360x640-cpu4x-slow3g", viewport: { width: 360, height: 640 }, cpu: 4, net: SLOW_3G, touch: true },
];

const MODULES = ["/patients", "/queue", "/consultation", "/billing", "/pharmacy", "/lab", "/ipd", "/reports"];

async function installObservers(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __perf: { lcp: number; tbt: number } };
    w.__perf = { lcp: 0, tbt: 0 };
    try {
      new PerformanceObserver((l) => {
        for (const e of l.getEntries()) w.__perf.lcp = Math.max(w.__perf.lcp, e.startTime);
      }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver((l) => {
        for (const e of l.getEntries()) w.__perf.tbt += Math.max(0, e.duration - 50);
      }).observe({ type: "longtask", buffered: true });
    } catch {
      /* observer unsupported */
    }
  });
}

/** Sum encoded bytes of script responses seen by CDP while `fn` runs. */
async function jsBytesDuring(cdp: CDPSession, fn: () => Promise<void>): Promise<number> {
  const types = new Map<string, string>();
  let bytes = 0;
  const onResp = (e: { requestId: string; type: string }) => types.set(e.requestId, e.type);
  const onDone = (e: { requestId: string; encodedDataLength: number }) => {
    if (types.get(e.requestId) === "Script") bytes += e.encodedDataLength;
  };
  cdp.on("Network.responseReceived", onResp);
  cdp.on("Network.loadingFinished", onDone);
  try {
    await fn();
    await new Promise((r) => setTimeout(r, 300));
  } finally {
    cdp.off("Network.responseReceived", onResp);
    cdp.off("Network.loadingFinished", onDone);
  }
  return bytes;
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : NaN;
}

test.describe.configure({ mode: "serial" });
test.setTimeout(15 * 60_000);

const all: Record<string, unknown> = {};

for (const p of PROFILES) {
  test(`perf: ${p.name}`, async ({ browser }) => {
    const runs: Record<string, number>[] = [];
    for (let i = 0; i < RUNS; i++) {
      const context = await browser.newContext({
        viewport: p.viewport,
        hasTouch: p.touch,
        isMobile: p.touch,
        deviceScaleFactor: p.touch ? 2 : 1,
        serviceWorkers: "block", // cold load every run; SW benefits are measured separately
      });
      const page = await context.newPage();
      await installObservers(page);
      const cdp = await context.newCDPSession(page);
      await cdp.send("Network.enable");
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: p.cpu });
      if (p.net) {
        await cdp.send("Network.emulateNetworkConditions", {
          offline: false,
          latency: p.net.latency,
          downloadThroughput: p.net.down,
          uploadThroughput: p.net.up,
        });
      }
      const r: Record<string, number> = {};

      r.loginJsBytes = await jsBytesDuring(cdp, async () => {
        await page.goto("/login", { waitUntil: "load", timeout: 180_000 });
        await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible({ timeout: 120_000 });
      });
      const nav = await page.evaluate(() => {
        const n = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
        const fcp = performance.getEntriesByName("first-contentful-paint")[0];
        return { dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd, fcp: fcp ? fcp.startTime : NaN };
      });
      await page.waitForTimeout(200);
      r.loginFcp = nav.fcp;
      r.loginDcl = nav.dcl;
      r.loginLoad = nav.load;
      r.loginLcp = await page.evaluate(() => (window as unknown as { __perf: { lcp: number } }).__perf.lcp);

      await page.getByLabel("Email").fill(EMAIL);
      await page.getByLabel("Password").fill(PASSWORD);
      let t0 = 0;
      r.dashboardJsBytes = await jsBytesDuring(cdp, async () => {
        t0 = Date.now();
        await page.getByRole("button", { name: "Sign in" }).click();
        await expect(page.getByRole("heading", { level: 1 })).toContainText("Welcome", { timeout: 180_000 });
        r.signInToDashboardMs = Date.now() - t0;
      });

      // Client-side navigation through the main modules via the shell links.
      let navTotal = 0;
      for (const href of MODULES) {
        let link = page.locator(`a[href="${href}"]:visible`).first();
        if ((await link.count()) === 0) {
          // Phone shell: modules outside the bottom bar live in the "More" sheet
          // (opened before the timer starts so both shells time one tap).
          const more = page.getByTestId("nav-more");
          if ((await more.count()) === 0) continue;
          await more.click();
          link = page.locator(`a[href="${href}"]:visible`).first();
          if ((await link.count()) === 0) continue;
        }
        const s = Date.now();
        await link.click();
        await expect(page).toHaveURL(new RegExp(`${href}$`), { timeout: 120_000 });
        await expect(page.locator("main.page h1, main.page h2").first()).toBeVisible({ timeout: 120_000 });
        await expect(page.getByText("Loading…")).toHaveCount(0, { timeout: 120_000 });
        const ms = Date.now() - s;
        r[`nav${href.replace(/\W/g, "_")}Ms`] = ms;
        navTotal += ms;
      }
      r.navAllModulesMs = navTotal;
      r.tbtMs = await page.evaluate(() => (window as unknown as { __perf: { tbt: number } }).__perf.tbt);
      await cdp.send("HeapProfiler.collectGarbage");
      const heap = (await cdp.send("Runtime.getHeapUsage")) as { usedSize: number; totalSize: number };
      r.heapUsedMB = Math.round((heap.usedSize / 1048576) * 10) / 10;
      runs.push(r);
      await context.close();
    }
    const keys = Object.keys(runs[0]);
    const med: Record<string, number> = {};
    for (const k of keys) med[k] = Math.round(median(runs.map((x) => x[k] ?? NaN)) * 10) / 10;
    all[p.name] = { profile: p, runs, median: med };
    console.log(`\n[perf:${LABEL}] ${p.name} (median of ${RUNS})`);
    console.table(med);
    mkdirSync("test-results/perf", { recursive: true });
    writeFileSync(`test-results/perf/${LABEL}.json`, JSON.stringify(all, null, 2));
  });
}

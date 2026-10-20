/**
 * Device / responsive / PWA checks against the LIVE stack (synthetic data):
 *   - PWA: manifest + icons + worker headers; the worker registers and
 *     controls the page; Cache Storage never holds /api/** or app HTML;
 *     a navigation with the network cut shows the static offline page
 *   - phone 360×640 (touch): bottom bar + More sheet, ≥44 px targets,
 *     one-tap patient search, no horizontal overflow in EN / मराठी / हिंदी
 *     (screenshots → test-results/device-shots/)
 *   - desktop keyboard: skip link, / and Ctrl+K, g-chords, n, ? dialog,
 *     shortcuts ignored while typing
 *   - connectivity: offline banner; payment button disabled offline
 *   - print: @page sizes A4 / A5 / 80 mm verified through Chromium's PDF
 *   - basic accessibility: every visible form control has a name
 * Emulation is not real hardware (see docs/DEVICE_COMPATIBILITY.md).
 */
import { mkdirSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";
const SHOTS = "test-results/device-shots";

type Clinic = { email: string; password: string; token: string; name: string };

async function registerClinic(request: APIRequestContext, tag: string): Promise<Clinic> {
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `${tag}.${stamp}@device-demo.example.com`;
  const password = `E2e-Pass-${stamp}!`;
  const name = `Device ${tag} ${stamp}`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: name,
      organization_slug: `dev-${tag}-${stamp}`.slice(0, 60),
      full_name: `Dr Device ${stamp}`,
      email,
      password,
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const token = (await reg.json()).tokens.access_token as string;
  const br = await request.post(`${API}/api/v1/branches`, {
    data: { name: "Main OPD", code: `M${stamp}`.slice(0, 20) },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(br.status()).toBe(201);
  return { email, password, token, name };
}

async function signIn(page: Page, c: Clinic) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(c.email);
  await page.getByLabel("Password").fill(c.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

function watchCsp(page: Page, sink: string[]) {
  page.on("console", (m) => {
    const text = m.text();
    if (/Content[- ]Security[- ]Policy|Refused to (execute|load|apply|connect|create)/i.test(text)) sink.push(text);
  });
  page.on("pageerror", (e) => sink.push(`pageerror: ${e.message}`));
}

async function noHorizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

/** Visible inputs/selects/textareas/buttons without an accessible name. */
async function unnamedControls(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const bad: string[] = [];
    const visible = (el: Element) => (el as HTMLElement).offsetParent !== null;
    for (const el of Array.from(document.querySelectorAll("input, select, textarea, button, a[href]"))) {
      if (!visible(el)) continue;
      const h = el as HTMLInputElement;
      if (h.type === "hidden") continue;
      const labelled =
        (h.labels && h.labels.length > 0) ||
        el.getAttribute("aria-label") ||
        el.getAttribute("aria-labelledby") ||
        el.getAttribute("title") ||
        ((el.tagName === "BUTTON" || el.tagName === "A") && (el.textContent || "").trim()) ||
        (h.type === "checkbox" && el.closest("label"));
      if (!labelled) bad.push(`${el.tagName.toLowerCase()}#${el.id || "?"}.${el.className}`);
    }
    return bad;
  });
}

// ------------------------------------------------------------------- PWA ---
test("PWA: manifest, icons, worker headers and the static offline page", async ({ request }) => {
  const m = await request.get("/manifest.webmanifest");
  expect(m.status()).toBe(200);
  expect(m.headers()["content-type"]).toContain("application/manifest+json");
  const manifest = await m.json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.theme_color).toBe("#0b3a5d");
  expect(manifest.start_url).toBe("/dashboard");
  for (const icon of manifest.icons as { src: string }[]) {
    expect((await request.get(icon.src)).status(), icon.src).toBe(200);
  }
  const sw = await request.get("/sw.js?v=x");
  expect(sw.status()).toBe(200);
  expect(sw.headers()["cache-control"]).toContain("no-cache");
  const off = await request.get("/offline.html");
  expect(off.status()).toBe(200);
  expect(off.headers()["content-security-policy"]).toContain("default-src 'none'");
  expect(await off.text()).not.toMatch(/<script/i);
});

test("PWA: worker controls the app, never caches /api or pages, offline fallback", async ({
  page,
  context,
  request,
}) => {
  const csp: string[] = [];
  watchCsp(page, csp);
  const c = await registerClinic(request, "pwa");
  await signIn(page, c);
  // The worker registers once the shell has loaded; reload so it controls the page.
  await page.waitForFunction(async () => !!(await navigator.serviceWorker.getRegistration()), null, {
    timeout: 30_000,
  });
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);

  // Visit pages that call the API (patient list = patient data).
  await page.getByRole("link", { name: "Patients" }).first().click();
  await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
  await page.getByRole("link", { name: "Billing" }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  const cached = await page.evaluate(async () => {
    const out: string[] = [];
    for (const k of await caches.keys()) {
      for (const r of await (await caches.open(k)).keys()) out.push(`${k} ${new URL(r.url).pathname}`);
    }
    return out;
  });
  expect(cached.length).toBeGreaterThan(0);
  expect(cached.filter((u) => / \/api\//.test(u))).toEqual([]);
  const html = cached.filter((u) => !/ \/_next\/static\/| \/icons\/| \/manifest\.webmanifest$/.test(u));
  expect(html.map((u) => u.split(" ")[1])).toEqual(["/offline.html"]);
  // Nothing patient-related in Web Storage either.
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(storage).not.toMatch(/eyJ|access_token|refresh|patient|uhid/i);

  // Network cut: a page navigation gets the static offline page.
  // Playwright's setOffline / route / CDP network emulation do not reach the
  // service worker's own fetch() in this Chromium build, so the worker's
  // network is cut by making fetch() reject inside the worker (what a
  // dropped connection does), and restored afterwards.
  await context.setOffline(true);
  const worker = context.serviceWorkers()[0];
  await worker.evaluate(() => {
    const g = self as unknown as { fetch: typeof fetch; __realFetch?: typeof fetch };
    g.__realFetch = g.fetch;
    g.fetch = () => Promise.reject(new TypeError("Failed to fetch"));
  });
  const res = await page.goto("/reports").catch(() => null);
  expect(res?.fromServiceWorker()).toBe(true);
  await expect(page.getByTestId("offline-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "You are offline" })).toBeVisible();
  await worker.evaluate(() => {
    const g = self as unknown as { fetch: typeof fetch; __realFetch?: typeof fetch };
    if (g.__realFetch) g.fetch = g.__realFetch;
  });
  await context.setOffline(false);

  // Logout clears every cache that is not the current build's static cache.
  await page.goto("/dashboard");
  await page.getByTestId("logout").click();
  await expect(page).toHaveURL(/\/login/);
  const left = await page.evaluate(async () => caches.keys());
  expect(left.every((k) => /^hms-(static|shell)-/.test(k))).toBe(true);
  expect(csp, "CSP violations / page errors").toEqual([]);
});

// ----------------------------------------------------------------- phone ---
test.describe("phone 360×640 (touch)", () => {
  test.use({ viewport: { width: 360, height: 640 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });

  test("bottom bar, More sheet, one-tap search, 44 px targets, no overflow in 3 languages", async ({
    page,
    request,
  }) => {
    const csp: string[] = [];
    watchCsp(page, csp);
    mkdirSync(SHOTS, { recursive: true });
    const c = await registerClinic(request, "phone");
    await signIn(page, c);

    const bar = page.getByTestId("bottom-nav");
    await expect(bar).toBeVisible();
    await expect(page.locator(".layout-nav")).toBeHidden();
    for (const box of await bar.locator("a, button").evaluateAll((els) =>
      els.map((e) => e.getBoundingClientRect()).map((r) => ({ w: r.width, h: r.height })),
    )) {
      expect(box.h).toBeGreaterThanOrEqual(44);
      expect(box.w).toBeGreaterThanOrEqual(44);
    }

    // One tap to patient search, with the search box focused.
    await page.getByTestId("quick-search-phone").tap();
    await expect(page).toHaveURL(/\/patients$/);
    await expect(page.locator("#q")).toBeFocused();

    // More sheet: lists the rest of the (gated) modules; Esc closes it.
    await page.getByTestId("nav-more").tap();
    const sheet = page.getByTestId("more-sheet");
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("link", { name: "Reports" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await page.getByTestId("nav-more").tap();
    await sheet.getByRole("link", { name: "Reports" }).tap();
    await expect(page).toHaveURL(/\/reports$/);
    await expect(sheet).toBeHidden();

    const pages = ["/dashboard", "/patients", "/queue", "/consultation", "/billing", "/pharmacy", "/lab", "/ipd", "/settings/security"];
    const langs: [string, string][] = [
      ["en", "English"],
      ["mr", "मराठी"],
      ["hi", "हिंदी"],
    ];
    for (const [code, label] of langs) {
      await page.getByTestId("nav-more").tap();
      await page.getByTestId("more-sheet").getByRole("button", { name: label }).tap();
      await page.keyboard.press("Escape");
      await expect(page.locator("html")).toHaveAttribute("lang", code);
      for (const path of pages) {
        await page.goto(path);
        await expect(page.locator("main.page").first()).toBeVisible();
        await expect(page.getByTestId("bottom-nav")).toBeVisible();
        await page.waitForTimeout(300);
        const overflow = await noHorizontalOverflow(page);
        await page.screenshot({ path: `${SHOTS}/360-${code}${path.replace(/\//g, "_")}.png`, fullPage: false });
        expect(overflow, `horizontal overflow on ${path} (${code})`).toBeLessThanOrEqual(1);
      }
    }
    await page.getByTestId("nav-more").tap();
    await page.getByTestId("more-sheet").getByRole("button", { name: "English" }).tap();
    expect(csp, "CSP violations / page errors").toEqual([]);
  });
});

// --------------------------------------------------------------- desktop ---
test("desktop keyboard: skip link, search, g-chords, n, ? dialog; ignored while typing", async ({
  page,
  request,
}) => {
  const csp: string[] = [];
  watchCsp(page, csp);
  const c = await registerClinic(request, "kbd");
  await page.setViewportSize({ width: 1366, height: 768 });
  await signIn(page, c);
  await expect(page.getByTestId("bottom-nav")).toBeHidden();

  // Skip link is the first Tab stop and moves focus to the content.
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  await page.keyboard.press("/");
  await expect(page.getByTestId("quick-search")).toBeFocused();
  // Typing "g p" inside the search box must not navigate.
  await page.keyboard.type("g p");
  await page.waitForTimeout(300);
  await expect(page).toHaveURL(/\/dashboard(#main-content)?$/);
  await page.keyboard.press("Enter"); // submit → Patients with the term
  await expect(page).toHaveURL(/\/patients$/);
  await expect(page.locator("#q")).toHaveValue("g p");

  await page.locator("h2").first().click(); // leave the field
  await page.keyboard.press("g");
  await page.keyboard.press("q");
  await expect(page).toHaveURL(/\/queue$/);
  await page.keyboard.press("g");
  await page.keyboard.press("p");
  await expect(page).toHaveURL(/\/patients$/);
  await page.keyboard.press("n");
  await expect(page.locator("#full_name")).toBeFocused();
  await page.locator("h2").first().click();
  await page.keyboard.press("Control+k");
  await expect(page.getByTestId("quick-search")).toBeFocused();
  await page.locator("h2").first().click();

  await page.keyboard.press("?");
  const dialog = page.getByTestId("shortcuts-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Keyboard shortcuts" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // Basic accessibility: named controls on the main pages.
  for (const path of ["/dashboard", "/patients", "/queue", "/consultation", "/billing", "/pharmacy", "/lab", "/ipd"]) {
    await page.goto(path);
    await expect(page.locator("main.page").first()).toBeVisible();
    await page.waitForTimeout(300);
    expect(await unnamedControls(page), `unnamed controls on ${path}`).toEqual([]);
  }
  expect(csp, "CSP violations / page errors").toEqual([]);
});

// ---------------------------------------------------------- connectivity ---
test("offline: banner shows and server-finalised payment is disabled", async ({ page, context, request }) => {
  const c = await registerClinic(request, "conn");
  const auth = { Authorization: `Bearer ${c.token}` };
  const p = await request.post(`${API}/api/v1/patients`, {
    data: { full_name: "Test Offline Patient", gender: "female", phone: "9000000001" },
    headers: auth,
  });
  expect(p.status(), await p.text()).toBe(201);
  await signIn(page, c);
  await page.getByRole("link", { name: "Billing" }).first().click();
  const picker = page.locator("#bi-p-q");
  await picker.fill("Test Offline Patient");
  const option = page.locator("#bi-p option", { hasText: "Test Offline Patient" });
  await expect(option).toHaveCount(1);
  await page.locator("#bi-p").selectOption((await option.getAttribute("value"))!);
  const line = page.locator("table").first().locator("tbody tr").first();
  await line.locator("input").nth(0).fill("OPD consultation");
  await line.locator("input").nth(2).fill("300");
  await page.getByRole("button", { name: "New invoice" }).click();
  const row = page.locator("table").nth(1).locator("tbody tr").first();
  await row.getByRole("button", { name: "Issue" }).click();
  await expect(row).toContainText("issued");
  const pay = page.getByTestId("take-payment");
  await expect(pay).toBeEnabled();

  await context.setOffline(true);
  await expect(page.getByTestId("connectivity")).toHaveAttribute("data-status", "offline");
  await expect(pay).toBeDisabled();
  await expect(page.getByTestId("needs-connection")).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByTestId("connectivity")).toHaveAttribute("data-status", "online", { timeout: 20_000 });
  await expect(pay).toBeEnabled();
});

// ----------------------------------------------------------------- print ---
test("print: @page sizes A4 / A5 / 80 mm are what Chromium prints", async ({ page, request }) => {
  const c = await registerClinic(request, "print");
  await signIn(page, c);
  mkdirSync(SHOTS, { recursive: true });
  // PDF MediaBox in points: A4 595×842, A5 420×595, 80 mm roll = 226.8 pt
  // wide and only as long as the receipt (well under A4's 842 pt).
  const expected: Record<string, [number, number | null]> = { a4: [595, 842], a5: [420, 595], "80mm": [226.8, null] };
  for (const [paper, [w, h]] of Object.entries(expected)) {
    await page.goto(`/print/test?paper=${paper}`);
    await expect(page.getByTestId("printer-test")).toHaveAttribute("data-paper", paper);
    if (paper === "80mm") {
      // the roll length is measured from the rendered receipt (not the 297 mm fallback)
      await expect(page.getByTestId("printer-test")).not.toHaveAttribute("data-roll-mm", "297");
    }
    await page.emulateMedia({ media: "print" });
    await page.screenshot({ path: `${SHOTS}/print-test-${paper}.png`, fullPage: true });
    // (page.pdf honours the emulated media: keep "print" so @media print applies)
    const pdf = (await page.pdf({ preferCSSPageSize: true, printBackground: true })).toString("latin1");
    await page.emulateMedia({ media: null });
    const boxes = [...pdf.matchAll(/\/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]/g)];
    expect(boxes.length, `MediaBox for ${paper}`).toBeGreaterThan(0);
    const box = boxes[boxes.length - 1];
    expect(Math.abs(Number(box[1]) - w), `${paper} width ${box[1]}`).toBeLessThan(2);
    if (h) expect(Math.abs(Number(box[2]) - h), `${paper} height ${box[2]}`).toBeLessThan(2);
    else expect(Number(box[2]), "80 mm roll length").toBeLessThan(600);
    const pages = (pdf.match(/\/Type\s*\/Page[^s]/g) || []).length;
    expect(pages, `${paper} fits on one page`).toBe(1);
  }
});

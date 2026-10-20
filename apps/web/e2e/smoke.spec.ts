/**
 * Live end-to-end smoke: register clinic → login → register patient →
 * consultation → Rx with explicit dose → sign → print shows the dose →
 * invoice → issue → pay once (button disabled in flight) → logout.
 * Also asserts: no tokens in Web Storage, httpOnly refresh cookie, no CSP
 * violations, language switch re-renders the page body, 390px layout.
 */
import { expect, test, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";

function watchCsp(page: Page, sink: string[]) {
  page.on("console", (m) => {
    const text = m.text();
    if (/Content[- ]Security[- ]Policy|Refused to (execute|load|apply)/i.test(text)) sink.push(text);
  });
  page.on("pageerror", (e) => sink.push(`pageerror: ${e.message}`));
}

async function pickPatient(page: Page, id: string, name: string) {
  await page.locator(`#${id}-q`).fill(name);
  const option = page.locator(`#${id} option`, { hasText: name });
  await expect(option).toHaveCount(1);
  const value = await option.getAttribute("value");
  await page.locator(`#${id}`).selectOption(value!);
}

test("clinical + billing chain through the web UI", async ({ page, context, request }) => {
  const csp: string[] = [];
  watchCsp(page, csp);
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `owner.${stamp}@sunrise-demo.in`;
  const password = `E2e-Pass-${stamp}!`;
  const orgName = `Sunrise E2E ${stamp}`;
  const doctor = `Dr Meera Kulkarni ${stamp}`;

  // 1. Register a clinic (no signup UI yet) + its first branch via the API.
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: orgName,
      organization_slug: `sunrise-e2e-${stamp}`,
      full_name: doctor,
      email,
      password,
    },
  });
  expect(reg.status()).toBe(201);
  const ownerToken = (await reg.json()).tokens.access_token as string;
  const br = await request.post(`${API}/api/v1/branches`, {
    data: { name: "Kothrud OPD", code: `K${stamp}`.slice(0, 20) },
    headers: { Authorization: `Bearer ${ownerToken}` },
  });
  expect(br.status()).toBe(201);

  // 2. Protected route → /login; sign in through /api/session.
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(doctor);

  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(storage).not.toMatch(/eyJ|refresh|access_token/);
  const cookies = await context.cookies();
  const rt = cookies.find((c) => c.name === "hms_rt");
  expect(rt).toBeTruthy();
  expect(rt!.httpOnly).toBe(true);
  expect(rt!.sameSite).toBe("Strict");
  expect(rt!.path).toBe("/api/session");

  // 3. Register a patient.
  const patientName = `Asha Patil ${stamp}`;
  await page.getByRole("link", { name: "Patients" }).first().click();
  await expect(page).toHaveURL(/\/patients$/);
  await page.locator("#full_name").fill(patientName);
  await page.locator("#gender").selectOption("female");
  await page.locator("#phone").fill("9876543210");
  await page.getByRole("button", { name: "Register patient" }).click();
  await expect(page.locator(".notice")).toContainText(patientName);

  // Language switch re-renders the page body (not just the header).
  await page.getByRole("button", { name: "हिंदी" }).click();
  await expect(page.getByRole("button", { name: "रोगी पंजीकरण" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("button", { name: "Register patient" })).toBeVisible();

  // 4. Start a consultation.
  await page.getByRole("link", { name: "Consultation" }).first().click();
  await pickPatient(page, "cp", patientName);
  await page.locator("#cc").fill("Fever for 2 days");
  await page.getByRole("button", { name: "Start consultation" }).click();
  await expect(page.getByTestId("encounter-patient")).toContainText(patientName);

  // 5. Build the Rx — nothing is pre-filled; signing empty fields is refused.
  await page.locator("#drug-q").fill("Paracetamol");
  await page.getByRole("button", { name: /^\+ Paracetamol/ }).first().click();
  await expect(page.locator("#rx-0-dose")).toHaveValue("");
  await expect(page.locator("#rx-0-frequency")).toHaveValue("");
  await expect(page.locator("#rx-0-duration_days")).toHaveValue("");
  let rxPosts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/api/v1/prescriptions")) rxPosts += 1;
  });
  await page.getByRole("button", { name: "Sign prescription" }).click();
  await expect(page.locator("p.error")).toContainText("Complete dose, route, frequency and duration");
  expect(rxPosts).toBe(0);

  await page.locator("#rx-0-dose").fill("650 mg");
  await page.locator("#rx-0-route").selectOption("oral");
  await page.locator("#rx-0-frequency").fill("BD");
  await page.locator("#rx-0-duration_days").fill("3");
  await page.locator("#rx-0-quantity").fill("6 tablets");
  await page.locator("#rx-0-instructions").fill("After food");
  await page.getByRole("button", { name: "Sign prescription" }).click();
  const printLink = page.locator(".notice a", { hasText: "Print Rx" });
  await expect(printLink).toBeVisible();
  expect(rxPosts).toBe(1);
  const printHref = await printLink.getAttribute("href");

  // 6. Print view shows the explicit dose, prescriber and clinic.
  const print = await context.newPage();
  watchCsp(print, csp);
  await print.goto(printHref!);
  await expect(print.getByTestId("rx-print-dose")).toHaveText("650 mg");
  await expect(print.getByTestId("rx-print-item")).toContainText("Paracetamol");
  await expect(print.getByTestId("rx-print-item")).toContainText("BD");
  await expect(print.getByTestId("clinic-name")).toHaveText(orgName);
  await expect(print.getByTestId("clinic-branch")).toContainText("Kothrud OPD");
  await expect(print.getByTestId("prescriber")).toContainText(doctor);
  await print.close();

  // 7. Invoice → issue.
  await page.getByRole("link", { name: "Billing" }).first().click();
  await pickPatient(page, "bi-p", patientName);
  const line = page.locator("table").first().locator("tbody tr").first();
  await line.locator("input").nth(0).fill("OPD consultation");
  await line.locator("input").nth(2).fill("500");
  await page.getByRole("button", { name: "New invoice" }).click();
  const invRow = page.locator("table").nth(1).locator("tbody tr").first();
  await expect(invRow).toContainText("draft");
  await invRow.getByRole("button", { name: "Issue" }).click();
  await expect(invRow).toContainText("issued");

  // 8. Pay once: button disabled while in flight; a double click posts once
  //    with a per-attempt UUID Idempotency-Key.
  const payPosts: { key: string | null }[] = [];
  await page.route("**/api/v1/billing/invoices/*/payments", async (route) => {
    payPosts.push({ key: route.request().headers()["idempotency-key"] ?? null });
    await new Promise((r) => setTimeout(r, 800));
    await route.continue();
  });
  const pay = page.getByTestId("take-payment");
  await expect(page.locator("#pay-amt")).toHaveValue("500.00");
  await pay.evaluate((b: HTMLButtonElement) => {
    b.click();
    b.click();
  });
  await expect(pay).toBeDisabled();
  await expect(invRow).toContainText("paid");
  expect(payPosts).toHaveLength(1);
  expect(payPosts[0].key).toMatch(/^[0-9a-f-]{36}$/);
  await page.unroute("**/api/v1/billing/invoices/*/payments");

  // 9. 390px wide: no horizontal page scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/billing", "/consultation", "/settings/security"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
  }
  await page.setViewportSize({ width: 1280, height: 800 });

  // 10. Logout clears the session and protected pages redirect again.
  await page.goto("/dashboard");
  await page.getByTestId("logout").click();
  await expect(page).toHaveURL(/\/login/);
  expect((await context.cookies()).find((c) => c.name === "hms_rt")).toBeUndefined();
  await page.goto("/billing");
  await expect(page).toHaveURL(/\/login\?next=%2Fbilling$/);

  expect(csp, "CSP violations / page errors").toEqual([]);
});

test("security headers and blocked token endpoints on the web origin", async ({ request }) => {
  const res = await request.get("/login");
  const h = res.headers();
  expect(h["content-security-policy"]).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(h["x-content-type-options"]).toBe("nosniff");
  expect(h["referrer-policy"]).toBe("no-referrer");
  expect(h["permissions-policy"]).toContain("camera=()");
  expect(h["x-powered-by"]).toBeUndefined();
  const direct = await request.post("/api/v1/auth/login", { data: {} });
  expect(direct.status()).toBe(404);
});

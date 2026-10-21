/**
 * M7.2 live E2E: a clinic pays for its edition through the payment SIMULATOR
 * (development only — no money moves), gets a GST invoice, recovers from a
 * declined payment, and the vendor approves a refund in the billing console.
 * Needs E2E_PLATFORM_EMAIL / E2E_PLATFORM_PASSWORD (seeded demo super-admin).
 */
import { expect, test, type APIRequestContext } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";
const PLATFORM_EMAIL = process.env.E2E_PLATFORM_EMAIL;
const PLATFORM_PASSWORD = process.env.E2E_PLATFORM_PASSWORD;
const PLAN = "clinic_plus_ai";

test.skip(!PLATFORM_EMAIL || !PLATFORM_PASSWORD, "E2E_PLATFORM_EMAIL / E2E_PLATFORM_PASSWORD not set");

async function platformToken(request: APIRequestContext): Promise<string> {
  const r = await request.post(`${API}/api/v1/auth/login`, {
    data: { email: PLATFORM_EMAIL, password: PLATFORM_PASSWORD },
  });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()).tokens.access_token as string;
}

async function setPrice(request: APIRequestContext, monthly: number | null) {
  const token = await platformToken(request);
  const r = await request.patch(`${API}/api/v1/platform/plans/${PLAN}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { price_monthly_paise: monthly },
  });
  expect(r.status(), await r.text()).toBe(200);
}

test.afterAll(async ({ request }) => {
  await setPrice(request, null);
});

test("clinic pays for its edition, retries a decline, gets a GST invoice; vendor approves a refund", async ({
  page,
  request,
}) => {
  await setPrice(request, 149900);
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `bill.${stamp}@demo-clinic.example.com`;
  const password = `E2e-Pass-${stamp}!`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: `Billing E2E ${stamp}`,
      organization_slug: `bill-${stamp}`,
      full_name: `Dr Bill ${stamp}`,
      email,
      password,
      plan_code: PLAN,
    },
  });
  expect(reg.status()).toBe(201);

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.getByRole("navigation", { name: "Modules" }).getByRole("link", { name: "Billing & invoices" }).click();
  await expect(page).toHaveURL(/\/settings\/billing$/);
  await expect(page.getByTestId("billing-mode")).toContainText("no money moves");

  const row = page.getByTestId(`plan-${PLAN}`);
  await expect(row).toContainText("₹1,499");
  await expect(row).toContainText("₹1,768.82"); // 18% GST added by the server
  await row.getByRole("button", { name: "Simulate a declined payment" }).click();
  await expect(page.locator("p.notice[role=status]")).toContainText("Payment failed");
  const orders = page.getByTestId("orders");
  await expect(orders).toContainText("Payment failed");
  await orders.getByRole("button", { name: "Retry payment" }).click();
  await expect(page.locator("p.notice[role=status]")).toContainText("Payment received");
  await expect(orders).toContainText("Paid");

  const invoices = page.getByTestId("invoices");
  await expect(invoices).toContainText("BNS/");
  await invoices.getByRole("button", { name: /^BNS\// }).click();
  const view = page.getByTestId("invoice-view");
  await expect(view).toContainText("Tax invoice");
  await expect(view).toContainText("CGST 9%");
  await expect(view).toContainText("₹1,768.82");

  await page.getByRole("button", { name: "Request refund" }).click();
  const form = page.getByTestId("refund-form");
  await form.getByLabel("Refund amount (₹)").fill("100");
  await form.getByLabel("Reason").fill("E2E goodwill refund");
  await form.getByRole("button", { name: "Send refund request" }).click();
  await expect(page.locator("p.notice[role=status]")).toContainText("Refund request sent");
  await expect(page.getByText("Awaiting review")).toBeVisible();

  // vendor side: approve in the billing console
  await page.getByRole("button", { name: "Log out" }).click();
  await page.goto("/login");
  await page.getByLabel("Email").fill(PLATFORM_EMAIL!);
  await page.getByLabel("Password").fill(PLATFORM_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await page.goto("/platform/billing");
  const queue = page.getByTestId("refund-queue");
  const item = queue.getByRole("listitem").filter({ hasText: "E2E goodwill refund" });
  await item.getByRole("button", { name: "Approve" }).click();
  await expect(page.locator("p.notice[role=status]")).toContainText("Refunded");
  await page.getByRole("button", { name: "Reconcile payments" }).click();
  await expect(page.getByTestId("reconciliation")).toBeVisible();
});

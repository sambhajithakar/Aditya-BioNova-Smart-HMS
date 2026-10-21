/**
 * Live end-to-end checks of the M7.1 commercial SaaS UI against the real API
 * (nothing mocked; contract: m71_contract.md). Synthetic data only.
 *
 *   - owner edits the organization profile (client-side GSTIN / PIN checks)
 *   - branch create → edit → deactivate
 *   - subscription page shows the edition, usage meters and plan comparison
 *   - support ticket create → reply
 *   - feature gating: a rural_clinic tenant has no Pharmacy in the nav
 *   - MFA policy: a doctor under the policy is held on /settings/security
 *   - platform admin: login → tenants → open tenant → change plan
 *     (needs E2E_PLATFORM_EMAIL / E2E_PLATFORM_PASSWORD; skipped otherwise)
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";
const PLATFORM_EMAIL = process.env.E2E_PLATFORM_EMAIL;
const PLATFORM_PASSWORD = process.env.E2E_PLATFORM_PASSWORD;

type Clinic = { email: string; password: string; stamp: string; token: string; slug: string; name: string };

async function registerClinic(
  request: APIRequestContext,
  tag: string,
  plan_code?: string,
): Promise<Clinic> {
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `${tag}.${stamp}@demo-clinic.example.com`;
  const password = `E2e-Pass-${stamp}!`;
  const slug = `m71-${tag}-${stamp}`.slice(0, 60);
  const name = `M71 ${tag} ${stamp}`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: name,
      organization_slug: slug,
      full_name: `Dr ${tag} ${stamp}`,
      email,
      password,
      ...(plan_code ? { plan_code } : {}),
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const token = (await reg.json()).tokens.access_token as string;
  return { email, password, stamp, token, slug, name };
}

const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("owner edits the organization profile", async ({ page, request }) => {
  const owner = await registerClinic(request, "org");
  await signIn(page, owner.email, owner.password);
  await expect(page).toHaveURL(/\/dashboard$/);

  // onboarding checklist links to the profile page
  await expect(page.getByTestId("onboarding")).toBeVisible();
  await page.getByTestId("onboarding").getByRole("link", { name: "Complete the organization profile" }).click();
  await expect(page).toHaveURL(/\/settings\/organization/);

  await page.getByLabel("Legal name").fill(`Sunrise Clinic Pvt Ltd ${owner.stamp}`);
  await page.getByLabel("Address line 1").fill("12 Karve Road");
  await page.getByLabel("City").fill("Pune");
  await page.getByLabel("State").fill("Maharashtra");

  // client-side validation blocks a bad PIN code / GSTIN without a request
  await page.getByLabel("PIN code").fill("011038");
  await page.getByLabel("GSTIN").fill("27ABCDE1234F1X5");
  let patches = 0;
  page.on("request", (r) => {
    if (r.method() === "PATCH" && r.url().endsWith("/api/v1/organization")) patches += 1;
  });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  expect(patches).toBe(0);

  await page.getByLabel("PIN code").fill("411038");
  await page.getByLabel("GSTIN").fill("27abcde1234f1z5"); // normalised to upper case
  await page.getByLabel("Default language").selectOption("mr");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator("p.notice")).toContainText("Saved.");
  expect(patches).toBe(1);

  await page.reload();
  await expect(page.getByLabel("City")).toHaveValue("Pune");
  await expect(page.getByLabel("GSTIN")).toHaveValue("27ABCDE1234F1Z5");
  await expect(page.getByLabel("PIN code")).toHaveValue("411038");
  await expect(page.getByLabel("Default language")).toHaveValue("mr");
});

test("branch create, edit and deactivate", async ({ page, request }) => {
  const owner = await registerClinic(request, "branch");
  await signIn(page, owner.email, owner.password);
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/settings/branches");

  const code = `KTH${owner.stamp}`.slice(0, 20).toUpperCase();
  const create = page.locator("section", { has: page.getByRole("heading", { name: "New branch" }) });
  await create.getByLabel("Branch name").fill("Kothrud OPD");
  await create.getByLabel("Branch code").fill(code);
  await create.getByLabel("Phone").fill("02012345678");
  await create.getByRole("button", { name: "New branch" }).click();
  const row = page.getByTestId(`branch-${code}`);
  await expect(row).toContainText("Kothrud OPD");
  const status = row.locator(".tag");
  await expect(status).toHaveText("Active");

  await row.getByRole("button", { name: /^Edit/ }).click();
  const edit = page.locator("section", { has: page.getByRole("heading", { name: `Edit: ${code}` }) });
  await edit.getByLabel("Branch name").fill("Kothrud OPD & Day Care");
  await edit.getByLabel("Address").fill("Plot 7, Paud Road, Pune");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(row).toContainText("Kothrud OPD & Day Care");
  await expect(row).toContainText("Plot 7, Paud Road");

  await row.getByRole("button", { name: /^Deactivate/ }).click();
  await expect(status).toHaveText("Inactive");
  await row.getByRole("button", { name: /^Activate/ }).click();
  await expect(status).toHaveText("Active");
});

test("subscription page shows the plan, usage and plan comparison", async ({ page, request }) => {
  const owner = await registerClinic(request, "sub");
  const sub = await request.get(`${API}/api/v1/subscription`, { headers: auth(owner.token) });
  expect(sub.status()).toBe(200);
  const planName = (await sub.json()).plan.name as string;

  await signIn(page, owner.email, owner.password);
  await expect(page).toHaveURL(/\/dashboard$/);
  // a fresh signup is on a trial: the shell banner links to the subscription page
  await expect(page.getByTestId("subscription-banner")).toBeVisible();
  await page.getByTestId("subscription-banner").getByRole("link", { name: "View subscription" }).click();
  await expect(page).toHaveURL(/\/settings\/subscription$/);

  await expect(page.getByTestId("plan-name")).toHaveText(planName);
  await expect(page.getByTestId("effective-status")).toHaveText("Trial");
  await expect(page.getByTestId("trial-countdown")).toContainText(/days left in trial|Trial has ended/);
  const usage = page.getByTestId("usage");
  await expect(usage).toContainText("Users");
  await expect(usage).toContainText(/1 of \d+|Unlimited/);
  await expect(page.getByTestId("plan-comparison")).toContainText(planName);
  await expect(page.getByTestId("plan-comparison")).toContainText(/₹|Price on request/);
  await expect(page.getByTestId("payment-not-enabled")).toContainText("Online payment is not enabled yet");

  await page.getByLabel("Plan", { exact: true }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByText(/Request sent/)).toBeVisible();
});

test("support ticket create, then reply", async ({ page, request }) => {
  const owner = await registerClinic(request, "support");
  await signIn(page, owner.email, owner.password);
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/support");

  await expect(page.getByTestId("no-patient-data")).toContainText("Do not include patient information");
  const form = page.locator("section", { has: page.getByRole("heading", { name: "New ticket" }) });
  const subject = `Printer margin on A5 ${owner.stamp}`;
  await form.getByLabel("Subject").fill(subject);
  await form.getByLabel("Category").selectOption("technical");
  await form.getByLabel("Priority").selectOption("normal");
  await form.getByLabel("Message").fill("The A5 prescription print cuts off the footer.");
  await form.getByRole("button", { name: "New ticket" }).click();

  await expect(page.locator("p.notice")).toContainText("Ticket created");
  await expect(page.getByRole("heading", { name: new RegExp(subject) })).toBeVisible();
  const thread = page.getByTestId("ticket-thread");
  await expect(thread.locator("li")).toHaveCount(1);

  await page.getByLabel("Reply").fill("Seen on Chrome and Edge, A5 portrait.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(thread.locator("li")).toHaveCount(2);
  await expect(thread).toContainText("Seen on Chrome and Edge");

  await page.getByRole("button", { name: "Close ticket" }).click();
  await expect(page.getByTestId("ticket-status")).toHaveText("Closed");
});

test("feature-gated nav hides Pharmacy for a rural_clinic tenant", async ({ page, request }) => {
  const owner = await registerClinic(request, "rural", "rural_clinic");
  const me = await request.get(`${API}/api/v1/auth/me`, { headers: auth(owner.token) });
  expect((await me.json()).edition?.code).toBe("rural_clinic");

  await signIn(page, owner.email, owner.password);
  await expect(page).toHaveURL(/\/dashboard$/);
  const nav = page.getByRole("navigation", { name: "Modules" });
  await expect(nav.getByRole("link", { name: "Patients" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Pharmacy" })).toHaveCount(0);
  await expect(page.getByTestId("edition")).toBeVisible();

  // deep link: the page body says it is not in the plan and fires no pharmacy calls
  let pharmacyCalls = 0;
  page.on("request", (r) => {
    if (r.url().includes("/api/v1/pharmacy")) pharmacyCalls += 1;
  });
  await page.goto("/pharmacy");
  await expect(page.getByTestId("feature-not-in-plan")).toBeVisible();
  expect(pharmacyCalls).toBe(0);
});

test("a role under the MFA policy is redirected to /settings/security", async ({ page, request }) => {
  const owner = await registerClinic(request, "mfapol");
  const pol = await request.patch(`${API}/api/v1/organization`, {
    data: { mfa_required_roles: ["doctor"] },
    headers: auth(owner.token),
  });
  expect(pol.status(), await pol.text()).toBe(200);
  const doctorEmail = `doctor.${owner.stamp}@demo-clinic.example.com`;
  const doctorPassword = `Doctor-Pass-${owner.stamp}`;
  const mem = await request.post(`${API}/api/v1/members`, {
    data: {
      email: doctorEmail,
      full_name: `Dr Kavita Joshi ${owner.stamp}`,
      password: doctorPassword,
      role_key: "doctor",
    },
    headers: auth(owner.token),
  });
  expect(mem.status(), await mem.text()).toBe(201);

  await signIn(page, doctorEmail, doctorPassword);
  await expect(page).toHaveURL(/\/settings\/security\?mfa=required$/);
  await expect(page.getByTestId("mfa-required-banner")).toContainText("Two-step verification required");
  await expect(page.getByRole("button", { name: "Set up authenticator app" })).toBeVisible();
  // only the security page is offered while enrolment is pending
  const nav = page.getByRole("navigation", { name: "Modules" });
  await expect(nav.getByRole("link")).toHaveCount(1);

  await page.goto("/patients");
  await expect(page).toHaveURL(/\/settings\/security\?mfa=required$/);
});

test.describe("platform console", () => {
  test.skip(!PLATFORM_EMAIL || !PLATFORM_PASSWORD, "E2E_PLATFORM_EMAIL / E2E_PLATFORM_PASSWORD not set");

  test("platform admin: tenants list → open tenant → change plan", async ({ page, request }) => {
    const tenant = await registerClinic(request, "plat");

    await signIn(page, PLATFORM_EMAIL!, PLATFORM_PASSWORD!);
    await expect(page).not.toHaveURL(/\/login/);
    // the clinic header offers the console only to platform admins
    const link = page.getByTestId("platform-link");
    if (await link.isVisible().catch(() => false)) await link.click();
    else await page.goto("/platform");
    await expect(page).toHaveURL(/\/platform$/);
    await expect(page.getByTestId("platform-badge")).toBeVisible();
    await expect(page.getByTestId("platform-kpis")).toContainText("Monthly recurring revenue");
    await expect(page.getByTestId("mrr")).toContainText("₹");

    await page.getByLabel("Search").fill(tenant.stamp);
    await page.getByRole("button", { name: "Search" }).click();
    const table = page.getByTestId("tenants-table");
    await table.getByRole("link", { name: tenant.name }).click();
    await expect(page).toHaveURL(/\/platform\/tenants\/[^/]+$/);
    await expect(page.getByTestId("tenant-name")).toHaveText(tenant.name);

    await page.getByTestId("plan-select").selectOption("clinic_starter");
    await page.getByLabel("Subscription status").selectOption("active");
    await page.getByTestId("subscription-reason").fill("E2E: sales confirmed Clinic Starter");
    await page.getByRole("button", { name: "Save subscription" }).click();
    await expect(page.locator("p.notice")).toContainText("Saved.");
    await expect(page.getByTestId("plan-select")).toHaveValue("clinic_starter");
    await expect(page.getByTestId("tenant-events")).toContainText("clinic_starter");
    await expect(page.getByTestId("tenant-events")).toContainText("E2E: sales confirmed");

    // the tenant sees its new edition
    const me = await request.get(`${API}/api/v1/auth/me`, { headers: auth(tenant.token) });
    expect((await me.json()).edition?.code).toBe("clinic_starter");
  });
});

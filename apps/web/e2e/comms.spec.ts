/**
 * Communications v2 + follow-up worklist against the live API. Delivery is
 * the mock outbox only — the page must say so ("not sent").
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";

async function register(request: APIRequestContext) {
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `comms.${stamp}@demo-clinic.example.com`;
  const password = `E2e-Pass-${stamp}!`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: `Comms ${stamp}`,
      organization_slug: `comms-${stamp}`,
      full_name: `Dr Comms ${stamp}`,
      email,
      password,
      plan_code: "hospital_advanced",
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const token = (await reg.json()).tokens.access_token as string;
  return { email, password, headers: { Authorization: `Bearer ${token}` } };
}

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("communications page: mock banner, template preview guard, run reminders", async ({ page, request }) => {
  const { email, password } = await register(request);
  await signIn(page, email, password);
  await page.getByRole("navigation", { name: "Modules" }).getByRole("link", { name: "Communications" }).click();
  await expect(page).toHaveURL(/\/communications$/);
  await expect(page.getByTestId("mock-outbox-banner")).toContainText("not sent");

  await page.getByRole("button", { name: /Default appointment reminder \(sms, en\)/ }).click();
  const body = page.getByTestId("template-body");
  await body.fill("Hi {patient_first_name}, your {diagnosis}");
  await expect(page.getByTestId("template-preview")).toContainText("Hi Asha, your {diagnosis}");
  await expect(page.getByTestId("template-problems")).toContainText("Not allowed");
  await expect(page.getByRole("button", { name: "Save template", exact: true })).toBeDisabled();

  await page.getByTestId("run-reminders").click();
  await expect(page.getByTestId("run-result")).toContainText("not sent");
});

test("follow-up worklist: due today, complete", async ({ page, request }) => {
  const { email, password, headers } = await register(request);
  const patient = await request.post(`${API}/api/v1/patients`, {
    headers,
    data: { full_name: "Asha Demo", gender: "female", phone: "9000000001", allow_duplicates: true },
  });
  expect(patient.status(), await patient.text()).toBe(201);
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const fu = await request.post(`${API}/api/v1/follow-ups`, {
    headers,
    data: { patient_id: (await patient.json()).id, due_date: today, reason: "Review visit" },
  });
  expect(fu.status(), await fu.text()).toBe(201);

  await signIn(page, email, password);
  await page.goto("/follow-ups");
  const table = page.getByTestId("followup-table");
  await expect(table).toContainText("Asha Demo");
  await expect(table).toContainText("Review visit");
  await table.getByRole("button", { name: "Complete" }).click();
  await expect(table).toContainText("Nothing here.");
  await page.getByTestId("bucket-closed").click();
  await expect(table).toContainText("Completed");
});

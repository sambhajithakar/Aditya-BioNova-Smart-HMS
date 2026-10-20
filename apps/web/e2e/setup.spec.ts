/**
 * Live E2E (nothing mocked): Smart Setup Wizard happy path and QR check-in
 * by manual code entry. Synthetic clinics / patients only. Camera scanning
 * (BarcodeDetector) is not exercised — headless Chromium on Linux has no
 * camera; manual entry uses the same API path.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";

type Clinic = { email: string; password: string; token: string; branchId: string };

async function registerClinic(request: APIRequestContext, tag: string): Promise<Clinic> {
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `${tag}.${stamp}@demo-clinic.example.com`;
  const password = `E2e-Pass-${stamp}!`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: `Setup ${tag} ${stamp}`,
      organization_slug: `setup-${tag}-${stamp}`.slice(0, 60),
      full_name: `Dr ${tag} ${stamp}`,
      email,
      password,
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const token = (await reg.json()).tokens.access_token as string;
  const b = await request.post(`${API}/api/v1/branches`, {
    data: { name: "Main Clinic", code: "MAIN" },
    headers: auth(token),
  });
  expect(b.status(), await b.text()).toBe(201);
  return { email, password, token, branchId: (await b.json()).id };
}

const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("owner completes the Smart Setup Wizard", async ({ page, request }) => {
  const c = await registerClinic(request, "wiz");
  await signIn(page, c.email, c.password);

  await page.getByTestId("setup-card-link").click();
  await expect(page.getByTestId("setup-wizard")).toBeVisible();
  await expect(page.getByTestId("wizard-step-identity")).toBeVisible();

  await page.getByTestId("wiz-address_line1").fill("12 Synthetic Road");
  await page.getByTestId("wiz-city").fill("Pune");
  await page.getByTestId("wiz-phone").fill("9876543210");
  await page.getByTestId("wizard-save").click();

  await expect(page.getByTestId("wizard-step-branch")).toBeVisible();
  await page.getByTestId("wizard-skip").click(); // already has a branch
  await expect(page.getByTestId("wizard-step-staff")).toBeVisible();
  await page.getByTestId("wizard-skip").click();
  await expect(page.getByTestId("wizard-step-language")).toBeVisible();
  await page.getByTestId("wizard-save").click();

  // the pre-filled defaults are accepted as-is from here on
  for (const step of ["working_hours", "fees", "prescription", "billing", "printer", "schedule"]) {
    await expect(page.getByTestId(`wizard-step-${step}`)).toBeVisible();
    await page.getByTestId("wizard-save").click();
  }
  await expect(page.getByTestId("wizard-step-edition")).toBeVisible();
  await expect(page.getByTestId("wiz-edition")).toBeVisible();
  await page.getByTestId("wizard-save").click();
  await expect(page.getByTestId("wizard-progress")).toHaveAttribute("style", /width: 100%/);

  await page.getByTestId("wizard-finish").click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByTestId("setup-card")).toHaveCount(0);

  // everything really is stored server-side
  const w = await (await request.get(`${API}/api/v1/setup/wizard`, { headers: auth(c.token) })).json();
  expect(w.finished).toBe(true);
  const statuses = Object.fromEntries(w.steps.map((s: { key: string; status: string }) => [s.key, s.status]));
  expect(statuses.branch).toBe("skipped");
  expect(statuses.fees).toBe("done");
  const hours = await (
    await request.get(`${API}/api/v1/setup/branches/${c.branchId}/working-hours`, { headers: auth(c.token) })
  ).json();
  expect(hours.sessions).toHaveLength(6);
  const fees = await (await request.get(`${API}/api/v1/setup/fees`, { headers: auth(c.token) })).json();
  expect(Number(fees.default.consultation_fee)).toBe(300);
  const printers = await (await request.get(`${API}/api/v1/setup/printers`, { headers: auth(c.token) })).json();
  expect(printers).toHaveLength(1);

  // printer test page renders with the profile's paper
  await page.goto("/settings/printers");
  await expect(page.getByTestId("printers-honesty")).toBeVisible();
  await expect(page.getByTestId("printer-row")).toHaveCount(1);
  await page.goto(`/print/test?profile=${printers[0].id}`);
  await expect(page.getByTestId("printer-test-sheet")).toBeVisible();
  await expect(page.getByText("मराठी: रुग्णाचे नाव")).toBeVisible();
});

test("reception checks a patient in by typing the QR code", async ({ page, request }) => {
  const c = await registerClinic(request, "chk");
  const h = auth(c.token);
  const p = await request.post(`${API}/api/v1/patients`, {
    data: {
      full_name: "Synthetic E2E Patient",
      gender: "female",
      phone: `98${Date.now().toString().slice(-8)}`,
      date_of_birth: "1990-01-01T00:00:00Z",
      allow_duplicates: true,
    },
    headers: h,
  });
  expect(p.status(), await p.text()).toBe(201);
  const now = Date.now();
  const appt = await request.post(`${API}/api/v1/appointments`, {
    data: {
      patient_id: (await p.json()).id,
      branch_id: c.branchId,
      starts_at: new Date(now - 60_000).toISOString(),
      ends_at: new Date(now + 4 * 60_000).toISOString(),
    },
    headers: h,
  });
  expect(appt.status(), await appt.text()).toBe(201);
  const apptId = (await appt.json()).id as string;

  await signIn(page, c.email, c.password);
  await page.goto(`/checkin/qr?appointment=${apptId}`);
  await page.getByTestId("checkin-qr-create").click();
  await expect(page.getByTestId("checkin-qr")).toBeVisible();
  const code = (await page.getByTestId("checkin-qr-code").innerText()).trim();
  expect(code).toMatch(/^[A-Z2-7 ]{32}$/);
  // the printable slip carries no patient data
  await expect(page.getByTestId("checkin-qr-slip")).not.toContainText("Synthetic E2E Patient");

  await page.goto("/checkin");
  await page.getByTestId("checkin-code").fill(code.toLowerCase());
  await page.getByTestId("checkin-lookup").click();
  await expect(page.getByTestId("checkin-patient")).toHaveText("Synthetic E2E Patient");
  await page.getByTestId("checkin-confirm").click();
  await expect(page.getByTestId("checkin-token")).toHaveText("1");

  // second scan: idempotent
  await page.getByTestId("checkin-code").fill(code);
  await page.getByTestId("checkin-lookup").click();
  await expect(page.getByTestId("checkin-verified")).toContainText("1");
  await expect(page.getByTestId("checkin-confirm")).toHaveCount(0);
});

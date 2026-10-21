/**
 * Live E2E (nothing mocked), M8.2: a SIMULATED Bluetooth reading captured
 * through the API (as the Android app does) waits for review in the web
 * consultation, is accepted only after the patient confirmation, and lands
 * in the encounter's vitals; another is rejected with a reason. Synthetic
 * clinic, patient and device payloads only (packages/contracts vectors).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";
const VECTORS = Object.fromEntries(
  (
    JSON.parse(
      readFileSync(join(__dirname, "../../../packages/contracts/device_vectors.json"), "utf8"),
    ).vectors as { name: string; characteristic: string; hex: string }[]
  ).map((v) => [v.name, v]),
);

const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

async function clinic(request: APIRequestContext) {
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `md.${stamp}@demo-clinic.example.com`;
  const password = `E2e-Pass-${stamp}!`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: `Devices ${stamp}`,
      organization_slug: `devices-${stamp}`.slice(0, 60),
      full_name: `Dr Devices ${stamp}`,
      email,
      password,
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const token = (await reg.json()).tokens.access_token as string;
  const h = auth(token);
  const br = await request.post(`${API}/api/v1/branches`, { data: { name: "Main", code: "MAIN" }, headers: h });
  expect(br.status()).toBe(201);
  const p = await request.post(`${API}/api/v1/patients`, {
    data: {
      full_name: "Synthetic Device Patient",
      gender: "female",
      date_of_birth: "1975-03-03",
      phone: "9876500912",
      allow_duplicates: true,
    },
    headers: h,
  });
  expect(p.status(), await p.text()).toBe(201);
  const enc = await request.post(`${API}/api/v1/encounters`, {
    data: { patient_id: (await p.json()).id, branch_id: (await br.json()).id, chief_complaint: "Headache" },
    headers: h,
  });
  expect(enc.status(), await enc.text()).toBe(201);
  return { email, password, h, encounterId: (await enc.json()).id as string };
}

async function simDevice(request: APIRequestContext, h: Record<string, string>, kind: string, address: string) {
  const r = await request.post(`${API}/api/v1/devices`, {
    data: { kind, label: `Sim ${kind}`, ble_address: address, is_simulator: true },
    headers: h,
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()).id as string;
}

async function capture(
  request: APIRequestContext,
  h: Record<string, string>,
  deviceId: string,
  address: string,
  encounterId: string,
  vector: string,
) {
  const v = VECTORS[vector];
  const r = await request.post(`${API}/api/v1/device-readings`, {
    data: {
      capture_id: randomUUID(),
      device_id: deviceId,
      ble_address: address,
      encounter_id: encounterId,
      characteristic: v.characteristic,
      raw_hex: v.hex,
      source: "simulator",
      captured_at: new Date().toISOString(),
      app_version: "e2e",
    },
    headers: h,
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()).id as string;
}

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("device readings are reviewed by a clinician before they enter the vitals", async ({ page, request }) => {
  const c = await clinic(request);
  const bp = await simDevice(request, c.h, "bp_monitor", "SIM-0000B001");
  const ox = await simDevice(request, c.h, "pulse_oximeter", "SIM-0000A001");
  const r1 = await capture(request, c.h, bp, "SIM-0000B001", c.encounterId, "bp all fields");
  const r2 = await capture(request, c.h, ox, "SIM-0000A001", c.encounterId, "spot minimal");

  await signIn(page, c.email, c.password);
  await page.goto("/consultation");
  const panel = page.getByTestId("device-readings");
  await expect(panel).toBeVisible();
  await expect(panel.getByText("BP 133/85 mmHg · pulse 72/min")).toBeVisible();
  await expect(panel.getByTestId("reading-simulated").first()).toBeVisible();
  await expect(panel.getByText(/body_movement, irregular_pulse/)).toBeVisible();

  // accept needs the explicit patient confirmation
  await expect(page.getByTestId(`accept-${r1}`)).toBeDisabled();
  await page.getByTestId(`confirm-${r1}`).check();
  await page.getByTestId(`accept-${r1}`).click();
  await expect(page.getByText("Accepted into the vitals.")).toBeVisible();
  await expect(page.getByRole("cell", { name: "133/85" })).toBeVisible();

  // reject needs a reason
  await page.getByTestId(`reject-${r2}`).click();
  await expect(page.getByText("A reason of at least 3 characters is required.")).toBeVisible();
  await page.getByTestId(`reason-${r2}`).fill("probe slipped off the finger");
  await page.getByTestId(`reject-${r2}`).click();
  await expect(page.getByText("Reading rejected.")).toBeVisible();

  // server state: one vitals row, linked to the accepted reading only
  const enc = await (await request.get(`${API}/api/v1/encounters/${c.encounterId}`, { headers: c.h })).json();
  expect(enc.vitals).toHaveLength(1);
  expect(enc.vitals[0].device_reading_id).toBe(r1);
  const rej = await (await request.get(`${API}/api/v1/device-readings/${r2}`, { headers: c.h })).json();
  expect(rej.status).toBe("rejected");
  expect(rej.decision.surface).toBe("web");

  // the device register page states the validation status
  await page.goto("/settings/devices");
  await expect(page.getByTestId("md-not-validated")).toBeVisible();
  await expect(page.getByTestId("md-list").getByText("Sim bp_monitor")).toBeVisible();
});

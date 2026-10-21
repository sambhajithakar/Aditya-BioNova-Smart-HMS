/**
 * Live end-to-end checks of the M7.0 account-security flows against the real
 * API (nothing mocked): TOTP enrolment in /settings/security → sign-in with
 * the second factor; invitation e-mail (dev outbox) → /accept-invite; and
 * /forgot-password → /reset-password. Synthetic data only.
 */
import { createHmac } from "node:crypto";

import { expect, test, type APIRequestContext } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";

function base32Decode(input: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of input.replace(/=+$/, "").toUpperCase()) {
    bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits) — what an authenticator app shows. */
function totp(secret: string, atMs = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(atMs / 1000 / 30)));
  const digest = createHmac("sha1", base32Decode(secret)).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const code = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return String(code).padStart(6, "0");
}

async function registerClinic(request: APIRequestContext, tag: string) {
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `${tag}.${stamp}@demo-clinic.example.com`;
  const password = `E2e-Pass-${stamp}!`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: `Security E2E ${stamp}`,
      organization_slug: `sec-e2e-${stamp}`,
      full_name: `Dr ${tag} ${stamp}`,
      email,
      password,
    },
  });
  expect(reg.status()).toBe(201);
  const token = (await reg.json()).tokens.access_token as string;
  return { email, password, stamp, token };
}

async function outboxLink(request: APIRequestContext, to: string, marker: string) {
  const res = await request.get(`${API}/api/v1/dev/outbox?limit=100`);
  expect(res.status()).toBe(200);
  const rows = (await res.json()) as { to: string; body: string }[];
  const body = rows.find((r) => r.to === to && r.body.includes(marker))?.body;
  expect(body, `no ${marker} message for ${to}`).toBeTruthy();
  const url = body!.split(/\s+/).find((w) => w.includes(marker))!;
  return new URL(url).pathname + new URL(url).search;
}

test("enrol TOTP in settings, then sign in with the second factor", async ({ page, request }) => {
  const { email, password } = await registerClinic(request, "mfa");

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.goto("/settings/security");
  await page.getByRole("button", { name: "Set up authenticator app" }).click();
  const secret = (await page.getByTestId("totp-secret").innerText()).trim();
  await expect(page.getByTestId("otpauth-uri")).toContainText("otpauth://totp/");
  await page.getByLabel("Authenticator or recovery code").fill(totp(secret));
  await page.getByRole("button", { name: "Verify and turn on" }).click();
  const codes = page.getByTestId("recovery-codes").locator("li");
  await expect(codes).toHaveCount(10);

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Two-step verification" })).toBeVisible();

  // wrong code is refused, the next time-step's code is accepted
  await page.getByLabel("Authenticator or recovery code").fill("000000");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByLabel("Authenticator or recovery code").fill(totp(secret, Date.now() + 30_000));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("invite a staff member and join through /accept-invite", async ({ page, request }) => {
  const owner = await registerClinic(request, "owner");
  const invitee = `nurse.${owner.stamp}@demo-clinic.example.com`;
  const inv = await request.post(`${API}/api/v1/members/invitations`, {
    data: { email: invitee, role_key: "nurse" },
    headers: { Authorization: `Bearer ${owner.token}` },
  });
  expect(inv.status()).toBe(201);

  await page.goto(await outboxLink(request, invitee, "/accept-invite?token="));
  await page.getByLabel("Full name").fill(`Nurse Asha ${owner.stamp}`);
  await page.getByLabel("New password").fill(`Invitee-Pass-${owner.stamp}`);
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Nurse Asha");

  // the token is single use
  const members = await request.get(`${API}/api/v1/members`, {
    headers: { Authorization: `Bearer ${owner.token}` },
  });
  const rows = (await members.json()) as { email: string; role_key: string }[];
  expect(rows.find((m) => m.email === invitee)?.role_key).toBe("nurse");
});

test("forgot password → reset link → sign in with the new password", async ({ page, request }) => {
  const { email, stamp } = await registerClinic(request, "reset");

  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByText("If an account exists for that e-mail")).toBeVisible();

  await page.goto(await outboxLink(request, email, "/reset-password?token="));
  const fresh = `Reset-Pass-${stamp}!`;
  await page.getByLabel("New password", { exact: true }).fill(fresh);
  await page.getByLabel("Confirm new password").fill(fresh);
  await page.getByRole("button", { name: "Reset password" }).click();
  await expect(page.getByText("Your password has been reset.")).toBeVisible();

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(fresh);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("doctor records their council registration number for prescriptions", async ({
  page,
  request,
}) => {
  const { email, password, token } = await registerClinic(request, "regno");
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.goto("/settings/security");
  await page.getByLabel("Professional registration number").fill("MMC 2014/05/1234");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Profile saved.")).toBeVisible();

  const me = await request.get(`${API}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect((await me.json()).user.registration_number).toBe("MMC 2014/05/1234");
});

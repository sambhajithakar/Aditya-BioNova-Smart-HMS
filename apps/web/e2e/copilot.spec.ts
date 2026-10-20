/**
 * Business Copilot (AI-0) against the live API — mock inference only, so the
 * answer must be labelled rule-based and show how it was computed.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8100";

async function register(request: APIRequestContext, plan_code: string) {
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `copilot.${stamp}@demo-clinic.example.com`;
  const password = `E2e-Pass-${stamp}!`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    data: {
      organization_name: `Copilot ${stamp}`,
      organization_slug: `copilot-${stamp}`,
      full_name: `Dr Copilot ${stamp}`,
      email,
      password,
      plan_code,
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  return { email, password };
}

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("owner switches on the Copilot and asks in Marathi", async ({ page, request }) => {
  const { email, password } = await register(request, "clinic_plus_ai");
  await signIn(page, email, password);
  await page.getByRole("navigation", { name: "Modules" }).getByRole("link", { name: "Copilot" }).click();
  await expect(page).toHaveURL(/\/copilot$/);
  await expect(page.getByTestId("copilot-disabled")).toBeVisible();
  await page.getByRole("button", { name: "Switch on the Copilot" }).click();

  await page.getByLabel("Your question").fill("या महिन्यात किती वसुली झाली?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const answer = page.getByTestId("copilot-answer").first();
  await expect(answer).toContainText("₹0.00");
  await expect(answer.getByTestId("inference-label")).toHaveText("Rule-based (no AI model)");
  await answer.getByText("How this was computed").click();
  await expect(answer.getByTestId("how-computed")).toContainText("collections_total");
  await expect(answer.getByTestId("how-computed")).toContainText("this_month");

  await page.getByLabel("Your question").fill("Write me a poem");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByTestId("copilot-answer").first()).toContainText("Not answered");
});

test("the Copilot is not offered on an edition without it", async ({ page, request }) => {
  const { email, password } = await register(request, "rural_clinic");
  await signIn(page, email, password);
  await expect(page.getByRole("link", { name: "Copilot" })).toHaveCount(0); // nav and tiles
});

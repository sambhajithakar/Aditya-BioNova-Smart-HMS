import { defineConfig, devices } from "@playwright/test";

/**
 * E2E smoke against a LIVE local stack (web + API + PostgreSQL); nothing is
 * mocked. Configure with:
 *   E2E_BASE_URL   web origin            (default http://127.0.0.1:3100)
 *   E2E_API_URL    API origin for setup  (default http://127.0.0.1:8100)
 *   E2E_CHROMIUM   optional Chromium executable (pre-installed browsers)
 */
const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:3100";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: process.env.E2E_CHROMIUM
          ? { executablePath: process.env.E2E_CHROMIUM }
          : {},
      },
    },
  ],
});

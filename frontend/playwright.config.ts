import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.OAK_E2E_PORT ?? 8091);
const BASE_URL = `http://127.0.0.1:${PORT}`;

// The browser in the OAK development container lives in /opt/pw-browsers. Elsewhere Playwright
// uses its own download (`npx playwright install chromium`).
const executablePath = process.env.OAK_E2E_CHROMIUM;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASE_URL,
    locale: "nl-NL",
    timezoneId: "Europe/Amsterdam",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], launchOptions: executablePath ? { executablePath } : {} } },
  ],
  webServer: {
    command: "sh tests/e2e/server.sh",
    url: `${BASE_URL}/health/ready`,
    timeout: 120_000,
    reuseExistingServer: false,
    env: { OAK_E2E_PORT: String(PORT) },
  },
});

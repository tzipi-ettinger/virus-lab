// End-to-end: a real browser against the real server (the Docker image, or uvicorn
// with STATIC_DIR) and a real Postgres, with EXTRACTION_PROVIDER=fake. See README,
// "בדיקות קצה לקצה".
// Owner: shared

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  // One flow that builds on what it saved: no parallel workers on one database.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8000",
    locale: "he-IL",
    timezoneId: "Asia/Jerusalem",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      // E2E_CHANNEL=chrome uses the installed Chrome, where Playwright's own
      // browser can't be downloaded.
      use: { ...devices["Desktop Chrome"], channel: process.env.E2E_CHANNEL },
    },
  ],
});

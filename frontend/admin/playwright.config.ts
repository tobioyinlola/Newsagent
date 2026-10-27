import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  workers: 1,
  use: {
    baseURL: "http://localhost:5174",
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
    trace: "retain-on-failure",
  },
  webServer: [
    { command: "./e2e/start-api.sh", url: "http://localhost:8000/health", reuseExistingServer: false, timeout: 120_000 },
    { command: "pnpm dev", url: "http://localhost:5174", reuseExistingServer: false },
  ],
});

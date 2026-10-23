import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  workers: 1,
  use: {
    baseURL: "http://localhost:5173",
    launchOptions: {
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      // a fake camera and microphone, so the AI interview can be driven in a browser with no devices
      args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
    trace: "retain-on-failure",
  },
  webServer: [
    { command: "./e2e/start-api.sh", url: "http://localhost:8000/health", reuseExistingServer: false, timeout: 120_000 },
    { command: "VITE_INTERVIEW_FAST=1 pnpm dev --port 5173", url: "http://localhost:5173", reuseExistingServer: false },
  ],
});

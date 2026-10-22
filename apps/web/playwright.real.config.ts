import path from "node:path";
import { defineConfig } from "@playwright/test";

const media = path.resolve("e2e-real/.media");

// Real-stack run: real browser recording -> real ffmpeg processing -> real Remotion merge.
// Vendors (HeyGen, Whisper, email) stay mocked. Slow (a few minutes): run with `pnpm e2e:real`.
export default defineConfig({
  testDir: "e2e-real",
  timeout: 360_000,
  workers: 1,
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || undefined,
      args: [
        "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        `--use-file-for-fake-video-capture=${media}/face.mjpeg`, `--use-file-for-fake-audio-capture=${media}/speech.wav`,
      ],
    },
  },
  webServer: [
    { command: "./e2e-real/start-renderer.sh", url: "http://localhost:4000/health", reuseExistingServer: false, timeout: 180_000, stdout: "pipe", stderr: "pipe" },
    { command: "./e2e-real/start-stack.sh", url: "http://localhost:8000/health", reuseExistingServer: false, timeout: 180_000, stdout: "pipe", stderr: "pipe" },
    // the production build, so the "bytes before the camera starts" check measures what a phone really downloads
    { command: "pnpm build && pnpm preview --port 5173 --strictPort", url: "http://localhost:5173", reuseExistingServer: false, timeout: 120_000 },
  ],
});

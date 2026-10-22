import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { type APIRequestContext, type BrowserContext, type Page, devices, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
// Gate 2 is a 5-question interview: run with E2E_QUESTIONS=5. The default (2) keeps day-to-day runs shorter.
const QUESTIONS = ["What problem does Acme solve?", "Why are you building this now?", "Who are your first customers?", "What has surprised you so far?", "What should viewers do next?"].slice(0, Number(process.env.E2E_QUESTIONS || 2));
const DROP_AT = QUESTIONS.length > 2 ? 2 : QUESTIONS.length - 1; // the connection dies while answering this one
const bearer = (email: string) => ({ Authorization: `Bearer dev:${email}` });
const OPS = bearer("ops@example.com");
const OWNER_EMAIL = "owner@startup.example.com";
const OWNER = bearer(OWNER_EMAIL);

async function ok<T>(r: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(r.status(), await r.text()).toBeLessThan(300);
  return (await r.json()) as T;
}

async function setupProject(request: APIRequestContext): Promise<string> {
  for (const vendor of ["mock", "renderer", "transcription"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "100" } }));
  const inv = await ok<{ code: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: OWNER_EMAIL, workspace_name: "Acme Farms", credits: "50", spend_cap: "100" } }));
  await ok(await request.post(`${API}/v1/auth/redeem`, { headers: OWNER, data: { code: inv.code } }));
  const p = await ok<{ id: string }>(await request.post(`${API}/v1/projects`, { headers: OWNER, data: { brief_text: "Acme Farms helps farmers sell produce online across Ghana.", region: "GH", voice_accent: "ghanaian" } }));
  const script = await ok<{ ticker_lines: string[]; lower_thirds: unknown[] }>(await request.post(`${API}/v1/projects/${p.id}/script/generate`, { headers: OWNER }));
  await ok(await request.put(`${API}/v1/projects/${p.id}/script`, { headers: OWNER, data: {
    segments: [{ kind: "intro", text: "Tonight we feature Acme Farms." }, { kind: "body", text: "Acme connects farmers with buyers." }, { kind: "outro", text: "That was Acme Farms. Back to you." }],
    ticker_lines: script.ticker_lines, lower_thirds: script.lower_thirds,
    interview_questions: QUESTIONS } }));
  await ok(await request.post(`${API}/v1/projects/${p.id}/script/approve`, { headers: OWNER, data: { with_interview: true } }));
  return p.id;
}

async function waitState(request: APIRequestContext, id: string, state: string, ms = 120_000) {
  await expect.poll(async () => (await (await request.get(`${API}/v1/projects/${id}`, { headers: OWNER })).json()).state, { timeout: ms, intervals: [1000] }).toBe(state);
}

async function recordAnswer(page: Page, seconds: number, between?: () => Promise<void>) {
  await page.getByRole("button", { name: "I'm ready, start recording" }).click();
  await expect(page.getByRole("button", { name: "Stop recording" })).toBeVisible({ timeout: 15_000 });
  const half = (seconds * 1000) / 2;
  await page.waitForTimeout(half);
  await between?.();
  await page.waitForTimeout(half);
  await page.getByRole("button", { name: "Stop recording" }).click();
  await expect(page.getByRole("button", { name: "Keep this answer" })).toBeVisible();
}

function probe(file: string) {
  const out = execFileSync("ffprobe", ["-v", "error", "-show_entries", "stream=codec_type,width,height,duration:format=duration", "-of", "json", file], { encoding: "utf8" });
  return JSON.parse(out) as { streams: { codec_type: string; width?: number; height?: number }[]; format: { duration: string } };
}

test("founder records on a throttled 4G phone, survives a dropped connection, and the real merge renders", async ({ browser, request }) => {
  const id = await setupProject(request);
  await waitState(request, id, "awaiting_founder");

  // --- owner creates the private link in the UI
  const ownerCtx = await browser.newContext();
  await ownerCtx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${OWNER_EMAIL}`);
  const owner = await ownerCtx.newPage();
  await owner.goto(`/projects/${id}`);
  await expect(owner.getByRole("heading", { name: "Founder interview" })).toBeVisible();
  await owner.getByLabel("Founder's name").fill("Ada Obi");
  await owner.getByLabel("Title (shown on screen)").fill("CEO, Acme Farms");
  await owner.getByRole("button", { name: "Create link" }).click();
  const link = await owner.getByLabel("Founder link").inputValue();
  expect(link).toContain("/i/");

  // --- founder: emulated mid-range Android phone on throttled 4G
  const phone: BrowserContext = await browser.newContext({ ...devices["Pixel 5"], permissions: ["camera", "microphone"] });
  const page = await phone.newPage();
  // the production Content-Security-Policy is enforced by `vite preview`; any violation is a bug in the app or the policy
  const violations: string[] = [];
  page.on("console", (m) => { if (/Content Security Policy|violates the following/i.test(m.text())) violations.push(m.text().slice(0, 200)); });
  const cdp = await phone.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 60, downloadThroughput: (4 * 1024 * 1024) / 8, uploadThroughput: (1.5 * 1024 * 1024) / 8 });

  // transferred bytes before the camera starts must stay small (spec: under 1 MB)
  let bytes = 0;
  page.on("response", async (r) => { try { if (r.url().includes("localhost:5173")) bytes += (await r.body()).length; } catch { /* streamed */ } });

  const landing = await page.goto(link.replace(/^https?:\/\/[^/]+/, "http://localhost:5173"));
  const headers = landing!.headers();
  expect(headers["content-security-policy"], "CSP header must be present or the violation check proves nothing").toContain("default-src 'self'");
  expect(headers["permissions-policy"]).toContain("camera=(self)");
  await expect(page.getByRole("heading", { name: "How your recording will be used" })).toBeVisible();
  await expect(page.getByText("deleted 90 days after")).toBeVisible();
  const beforeCamera = bytes;
  expect(beforeCamera).toBeLessThan(1_000_000);
  console.log(`bytes before camera: ${beforeCamera}`);
  await page.getByLabel("I understand and agree to this.").check();
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByRole("button", { name: "Turn on camera and microphone" }).click();
  await expect(page.getByText("we can hear you ✓")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Connection: [\d.]+ Mbps/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Looks good, continue" }).click();

  for (const [i, text] of QUESTIONS.entries()) {
    await expect(page.getByRole("heading", { name: text })).toBeVisible({ timeout: 120_000 });
    if (i !== DROP_AT) {
      await recordAnswer(page, 5);
      await expect(page.getByText("Saved ✓")).toBeVisible({ timeout: 90_000 });
      await page.getByRole("button", { name: "Keep this answer" }).click();
      continue;
    }
    // the connection drops mid-recording and is still down when the founder stops
    await recordAnswer(page, 8, async () => { await phone.setOffline(true); });
    await expect(page.getByText("No connection. Your answer is safe on this device")).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Keep this answer" }).click();
    await expect(page.getByText("Waiting for your connection to come back…")).toBeVisible();
    await phone.setOffline(false); // reconnect: uploads must resume, not restart
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 60, downloadThroughput: (4 * 1024 * 1024) / 8, uploadThroughput: (1.5 * 1024 * 1024) / 8 });
  }

  // all answers processed for real (ffmpeg cleanup); then submit
  await expect(page.getByRole("heading", { name: "Your answers" })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Answered ✓")).toHaveCount(QUESTIONS.length);
  await page.getByRole("button", { name: "Submit my answers" }).click();
  await expect(page.getByText(/Thank you, Ada Obi/)).toBeVisible();

  // --- owner reviews, arranges and makes the final video
  await owner.reload();
  await expect(owner.getByRole("heading", { name: "Review the answers" })).toBeVisible({ timeout: 30_000 });
  await expect(owner.locator("video[aria-label^='Answer to question']")).toHaveCount(QUESTIONS.length);
  await owner.getByLabel("Layout").selectOption("split");
  await owner.getByLabel("Cut from start (s)").first().fill("0.5");
  await owner.getByRole("button", { name: "Make the final video" }).click();
  await expect(owner.getByRole("heading", { name: "Your video" })).toBeVisible({ timeout: 300_000 });

  expect(violations, "CSP violations on the founder page").toEqual([]);

  // --- the delivered file is a real, correctly-sized video with audio
  const dl = await ownerCtx.request.get(`${API}/v1/projects/${id}/downloads`, { headers: OWNER });
  const items = (await dl.json()).items as { type: string; format: string | null; url: string }[];
  const file = items.find((i) => i.type === "render" && i.format === "16x9")!;
  const buf = await (await request.get(file.url)).body();
  const tmp = path.join(os.tmpdir(), `e2e-final-${Date.now()}.mp4`);
  fs.writeFileSync(tmp, buf);
  const info = probe(tmp);
  expect(info.streams.find((s) => s.codec_type === "video")).toMatchObject({ width: 1920, height: 1080 });
  expect(info.streams.some((s) => s.codec_type === "audio")).toBe(true);
  expect(Number(info.format.duration)).toBeGreaterThan(4 * QUESTIONS.length); // anchor + questions + answers + outro
  console.log(`final video: ${info.format.duration}s, ${(buf.length / 1024).toFixed(0)} KB`);
  const vertical = items.find((i) => i.type === "render" && i.format === "9x16")!;
  expect(vertical).toBeTruthy();
  const costs = await (await request.get(`${API}/v1/projects/${id}/costs`, { headers: OWNER })).json();
  expect(costs.lines.map((l: { stage: string }) => l.stage)).toEqual(expect.arrayContaining(["anchor_render", "question_clips", "process_take", "merge_render"]));
});

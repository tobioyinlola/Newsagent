import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { type APIRequestContext, expect, test } from "@playwright/test";

// The guided flow on the real stack: real browser recording, real ffmpeg, real Remotion merge. Vendors stay mocked.
const API = "http://localhost:8000";
const SHOTS = process.env.SHOTS_DIR || "";
const bearer = (email: string) => ({ Authorization: `Bearer dev:${email}` });
const OPS = bearer("ops@example.com");
const OWNER_EMAIL = "grace@guidedco.example.com";

async function ok<T>(r: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(r.status(), await r.text()).toBeLessThan(300);
  return (await r.json()) as T;
}

test("guided flow, recorded for real, merged into the final video", async ({ browser, request }) => {
  for (const vendor of ["mock", "renderer", "transcription"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "100" } }));
  const inv = await ok<{ code: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: OWNER_EMAIL, workspace_name: "Guided Co", credits: "50", spend_cap: "100" } }));
  await ok(await request.post(`${API}/v1/auth/signup/start`, { data: { invite_code: inv.code, password: "correct horse battery" } }));
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: OWNER_EMAIL } })).json();
  await ok(await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: inv.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } }));

  const ctx = await browser.newContext({ permissions: ["camera", "microphone"], viewport: { width: 1280, height: 900 } });
  await ctx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${OWNER_EMAIL}`);
  const page = await ctx.newPage();
  const shot = async (name: string) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true }); };

  await page.goto("/projects/new");
  await page.getByRole("radio", { name: /Funding round/ }).click();
  await page.getByLabel("Tell us the key details").fill("Minicor, a San Francisco startup, raised a $3.8M seed round led by IA Ventures. It lets developers turn desktop workflows in old software into API endpoints, so AI tools can work with systems that have no modern API. The two co-founders, Saheed Akinbile and Faizaan Chishtie, met at university and applied to Y Combinator several times before they were accepted.");
  await page.getByLabel("Your name").fill("Saheed Akinbile");
  await page.getByLabel("Your role").fill("Co-founder and CTO, Minicor");
  await expect(page.getByRole("radio", { name: /\(default\)/ })).toBeVisible();
  await shot("1-details");
  await page.getByRole("button", { name: "Continue to the interview" }).click();

  await expect(page.getByRole("heading", { name: "Your AI interview" })).toBeVisible();
  await shot("2-interview-intro");
  await page.getByLabel("I understand and agree.").check();
  await page.getByRole("button", { name: "Get ready for the interview" }).click();
  await expect(page.getByText("✓ Your camera is on")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Start the interview" }).click();
  const room = page.getByRole("dialog", { name: "AI interview" });
  for (let q = 1; q <= 4; q++) {
    await expect(room.getByText("Your turn: answer now")).toBeVisible({ timeout: 30_000 });
    if (q === 2) await shot("3-interview-room");
    await page.waitForTimeout(5000);
    await room.getByRole("button", { name: "I’m done answering" }).click();
  }
  await expect(page.getByRole("heading", { name: "Review your interview" })).toBeVisible({ timeout: 120_000 });
  await shot("4-review-answers");
  await page.getByRole("button", { name: "Write my story" }).click();

  await expect(page.getByRole("heading", { name: "Your news story" })).toBeVisible({ timeout: 30_000 });
  const pics: { name: string; mimeType: string; buffer: Buffer }[] = [];
  for (const [i, color] of ["0x0f3f86", "0x1c8c5a"].entries()) {
    const f = path.join(os.tmpdir(), `pic-${Date.now()}-${i}.png`);
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", `color=c=${color}:s=1280x720`, "-vf", `drawtext=text='Product picture ${i + 1}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2`, "-frames:v", "1", f]);
    pics.push({ name: `picture-${i + 1}.png`, mimeType: "image/png", buffer: fs.readFileSync(f) });
  }
  await page.getByLabel("Choose pictures").setInputFiles(pics);
  await expect(page.getByAltText("Your picture")).toHaveCount(2, { timeout: 20_000 });
  const claims = page.getByRole("group", { name: "Confirm these claims are accurate" });
  if (await claims.count()) for (const box of await claims.getByRole("checkbox").all()) await box.check();
  await shot("5-story-review");
  await page.getByRole("button", { name: "Make my video" }).click();

  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 600_000 });
  await expect(page.getByRole("heading", { name: "Your announcement" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Social post" })).toBeVisible();
  await shot("6-ready");

  const pid = /projects\/([0-9a-f]+)/.exec(page.url())![1];
  const items = (await (await ctx.request.get(`${API}/v1/projects/${pid}/downloads`, { headers: bearer(OWNER_EMAIL) })).json()).items as { type: string; format: string | null; url: string }[];
  const file = items.find((i) => i.type === "render" && i.format === "16x9")!;
  const out = path.join(SHOTS || os.tmpdir(), "guided-final-16x9.mp4");
  fs.writeFileSync(out, await (await request.get(file.url)).body());
  const info = JSON.parse(execFileSync("ffprobe", ["-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", out], { encoding: "utf8" }));
  expect(info.streams.find((s: { codec_type: string }) => s.codec_type === "video")).toMatchObject({ width: 1920, height: 1080 });
  expect(info.streams.some((s: { codec_type: string }) => s.codec_type === "audio")).toBe(true);
  const costs = await (await request.get(`${API}/v1/projects/${pid}/costs`, { headers: bearer(OWNER_EMAIL) })).json();
  expect(costs.lines.map((l: { stage: string }) => l.stage)).toEqual(expect.arrayContaining(["anchor_render", "question_clips", "merge_render"]));
  fs.writeFileSync(path.join(SHOTS || os.tmpdir(), "story.json"), JSON.stringify(await (await request.get(`${API}/v1/projects/${pid}/story`, { headers: bearer(OWNER_EMAIL) })).json(), null, 2));
});

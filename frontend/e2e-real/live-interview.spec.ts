import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { type APIRequestContext, expect, test } from "@playwright/test";

// The AI interview on the real stack: real browser recording, real ffmpeg processing, real Remotion merge with the
// answers column. Vendors (HeyGen, Whisper, TTS, email) stay mocked; the interviewer speaks with the browser's voice.
const API = "http://localhost:8000";
const QUESTIONS = ["What problem does Acme solve?", "Why are you building this now?", "Who are your first customers?", "What has surprised you so far?"].slice(0, Number(process.env.E2E_QUESTIONS || 2));
const bearer = (email: string) => ({ Authorization: `Bearer dev:${email}` });
const OPS = bearer("ops@example.com");
const OWNER_EMAIL = "tobi@liveco.example.com";
const OWNER = bearer(OWNER_EMAIL);

async function ok<T>(r: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(r.status(), await r.text()).toBeLessThan(300);
  return (await r.json()) as T;
}

test("AI interview, recorded for real, merged with the answers column", async ({ browser, request }) => {
  for (const vendor of ["mock", "renderer", "transcription"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "100" } }));
  const inv = await ok<{ code: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: OWNER_EMAIL, workspace_name: "Live Co", credits: "50", spend_cap: "100" } }));
  await ok(await request.post(`${API}/v1/auth/signup/start`, { data: { invite_code: inv.code, password: "correct horse battery" } }));
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: OWNER_EMAIL } })).json();
  await ok(await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: inv.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } }));

  // the operator's presenter footage: real landscape clips with sound, checked by the real renderer
  for (const [role, seconds] of [["intro", 4], ["cutaway", 3], ["outro", 4]] as const) {
    const f = path.join(os.tmpdir(), `presenter-${role}-${Date.now()}.mp4`);
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", `smptebars=s=1920x1080:r=30:d=${seconds}`, "-f", "lavfi", "-i", `sine=frequency=500:d=${seconds}`, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", f]);
    const data = fs.readFileSync(f);
    const slot = await ok<{ id: string; upload_url: string }>(await request.post(`${API}/v1/admin/presenter-clips`, { headers: OPS, data: { title: `${role} clip`, role, content_type: "video/mp4", size_bytes: data.length, rights_confirmed: true } }));
    await ok(await request.put(slot.upload_url, { data, headers: { "content-type": "video/mp4" } }));
    const c = await ok<{ duration_s: number; width: number }>(await request.post(`${API}/v1/admin/presenter-clips/${slot.id}/confirm`, { headers: OPS }));
    expect(c.width).toBe(1920);
    expect(c.duration_s).toBeGreaterThan(seconds - 0.5);
  }

  const p = await ok<{ id: string }>(await request.post(`${API}/v1/projects`, { headers: OWNER, data: { brief_text: "Live Co helps farmers sell produce online across Ghana.", founder_name: "Tobi Oyinlola", founder_title: "CEO, Live Co" } }));
  const script = await ok<{ ticker_lines: string[]; lower_thirds: unknown[] }>(await request.post(`${API}/v1/projects/${p.id}/script/generate`, { headers: OWNER }));
  await ok(await request.put(`${API}/v1/projects/${p.id}/script`, { headers: OWNER, data: {
    segments: [{ kind: "intro", text: "Tonight we feature Live Co." }, { kind: "body", text: "Live Co connects farmers with buyers." }, { kind: "outro", text: "That was Live Co. Back to you." }],
    ticker_lines: script.ticker_lines, lower_thirds: script.lower_thirds, interview_questions: QUESTIONS } }));
  await ok(await request.post(`${API}/v1/projects/${p.id}/script/approve`, { headers: OWNER, data: { with_interview: true, interview_mode: "live" } }));

  // product footage: a real image uploaded to the brand kit and chosen for this video
  const png = path.join(os.tmpdir(), `product-${Date.now()}.png`);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x800", "-frames:v", "1", png]);
  const img = fs.readFileSync(png);
  const slotP = await ok<{ upload_url: string; key: string }>(await request.post(`${API}/v1/brand-kit/uploads`, { headers: OWNER, data: { kind: "product_image", content_type: "image/png", size_bytes: img.length } }));
  await ok(await request.put(slotP.upload_url, { data: img, headers: { "content-type": "image/png" } }));
  await ok(await request.post(`${API}/v1/brand-kit/uploads/confirm`, { headers: OWNER, data: { key: slotP.key } }));
  await ok(await request.put(`${API}/v1/projects/${p.id}/broll`, { headers: OWNER, data: { items: [{ key: slotP.key, caption: "The Acme app", seconds: 4 }] } }));

  const ctx = await browser.newContext({ permissions: ["camera", "microphone"], viewport: { width: 1280, height: 800 } });
  await ctx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${OWNER_EMAIL}`);
  const page = await ctx.newPage();
  const violations: string[] = [];
  page.on("console", (m) => { if (/Content Security Policy|violates the following/i.test(m.text())) violations.push(m.text().slice(0, 200)); });
  await page.goto(`/projects/${p.id}`);

  await expect(page.getByRole("heading", { name: "Your AI interview" })).toBeVisible();
  await page.getByLabel("I understand and agree.").check();
  await page.getByRole("button", { name: "Get ready for the interview" }).click();
  await expect(page.getByText("✓ Your camera is on")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Hi Tobi, welcome\./)).toBeVisible();
  await page.getByRole("button", { name: "Start the interview" }).click();

  const room = page.getByRole("dialog", { name: "AI interview" });
  for (let q = 1; q <= QUESTIONS.length; q++) {
    await expect(room.getByText("Your turn: answer now")).toBeVisible({ timeout: 30_000 });
    await expect(room.getByText(`Question ${q} of ${QUESTIONS.length}`)).toBeVisible();
    await page.waitForTimeout(5000); // real speech from the fake microphone, real video from the fake camera
    await room.getByRole("button", { name: "I’m done answering" }).click();
  }

  // every answer was really processed (ffmpeg), with a snapshot, and is ready to review
  await expect(page.getByRole("heading", { name: "Review your interview" })).toBeVisible({ timeout: 120_000 });
  await expect(page.locator("video[aria-label^='Your answer to question']")).toHaveCount(QUESTIONS.length);
  await expect(page.getByLabel("How your answers appear in the video")).toHaveValue("column");
  await page.getByRole("button", { name: "Make my video" }).click();
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 360_000 });
  expect(violations, "CSP violations on the interview").toEqual([]);

  // the delivered file: right size, has sound, and the answers column is really on screen during an answer
  const items = (await (await ctx.request.get(`${API}/v1/projects/${p.id}/downloads`, { headers: OWNER })).json()).items as { type: string; format: string | null; url: string }[];
  const file = items.find((i) => i.type === "render" && i.format === "16x9")!;
  const tmp = path.join(os.tmpdir(), `e2e-live-${Date.now()}.mp4`);
  fs.writeFileSync(tmp, await (await request.get(file.url)).body());
  const info = JSON.parse(execFileSync("ffprobe", ["-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", tmp], { encoding: "utf8" }));
  expect(info.streams.find((s: { codec_type: string }) => s.codec_type === "video")).toMatchObject({ width: 1920, height: 1080 });
  expect(info.streams.some((s: { codec_type: string }) => s.codec_type === "audio")).toBe(true);
  const pixel = (t: number, x: number, y: number): number[] => [...execFileSync("ffmpeg", ["-v", "error", "-ss", String(t), "-i", tmp, "-frames:v", "1", "-vf", `crop=1:1:${x}:${y},format=rgb24`, "-f", "rawvideo", "-"])];
  // frames around the clock: the opening shot (SMPTE bars, light grey at the left) plays first, and the founder's answer
  // is beside the brand column (Pastel Green border, dark panel) at some point after the AI presenter
  const duration = Number(info.format.duration);
  expect(duration, "intro 4 s + cutaway 3 s + sign-off 4 s + 4 s of product footage are on top of the presenter and the answers").toBeGreaterThan(34);
  const opening = pixel(1, 200, 300);
  expect(Math.min(...opening), `opening shot pixel ${opening}`).toBeGreaterThan(150);
  let column = false;
  for (let t = 5; t < duration - 4 && !column; t += 1) {
    const green = [1225, 1230, 1235, 1240].map((x) => pixel(t, x, 600)).find((px) => px[1] > 200 && px[0] > 150 && px[2] < 160);
    const panel = pixel(t, 1700, 1000);
    column = !!green && Math.max(...panel) < 80;
  }
  expect(column, "the answers column is on screen during an answer").toBe(true);
  const ending = pixel(duration - 1, 200, 300);
  expect(Math.min(...ending), `sign-off pixel ${ending}`).toBeGreaterThan(150);
  const costs = await (await request.get(`${API}/v1/projects/${p.id}/costs`, { headers: OWNER })).json();
  expect(costs.lines.map((l: { stage: string }) => l.stage)).toEqual(expect.arrayContaining(["anchor_render", "question_clips", "process_take", "merge_render"]));
});

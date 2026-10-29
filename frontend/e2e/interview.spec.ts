import { type APIRequestContext, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };
let n = 0;

async function ok<T>(r: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(r.status(), await r.text()).toBeLessThan(300);
  return (await r.json()) as T;
}

// an owner with a workspace, created through the real sign-up endpoints
async function owner(request: APIRequest) {
  for (const vendor of ["mock", "renderer", "transcription"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } }));
  const email = `ada${Date.now()}${n++}@startup.example.com`;
  const inv = await ok<{ code: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: "Acme Farms", credits: "25", spend_cap: "500" } }));
  await ok(await request.post(`${API}/v1/auth/signup/start`, { data: { invite_code: inv.code, password: "correct horse battery" } }));
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  const s = await ok<{ token: string }>(await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: inv.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } }));
  return s.token;
}
type APIRequest = APIRequestContext;

const BRIEF = "Acme Farms helps smallholder farmers sell their produce to verified buyers on their phones, with payment the same day. Today we are opening in Kumasi.";

async function toInterview(page: import("@playwright/test").Page, token: string) {
  await page.addInitScript((t) => { if (!sessionStorage.getItem("seeded")) { sessionStorage.setItem("seeded", "1"); localStorage.setItem("newsagent.token", t); } }, token);
  await page.goto("/ai-newsroom/new-classic");
  await expect(page.getByRole("group", { name: "Your presenter" })).toBeVisible();
  // only the default presenter can be picked today; the others are shown as coming soon
  await expect(page.getByRole("radio")).toHaveCount(1);
  await expect(page.getByRole("radio").first()).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("Coming soon").first()).toBeVisible();
  await page.getByLabel("Your name").fill("Ada Obi");
  await page.getByLabel("Your role").fill("CEO, Acme Farms");
  await page.getByLabel("Paste your announcement or news script").fill(BRIEF);
  await page.getByRole("button", { name: "Read it and write my script" }).click();
  await expect(page.getByRole("heading", { name: /Script \(version 1\)/ })).toBeVisible();
  // the interview is the default, with 4 questions written from the announcement
  await expect(page.getByLabel(/Interview me now/)).toBeChecked();
  await expect(page.getByLabel(/Interview question/)).toHaveCount(4);
  await page.getByRole("button", { name: "Approve and make my video" }).click();
  await expect(page.getByRole("heading", { name: "Your AI interview" })).toBeVisible();
}

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("AI interview: understands the announcement, interviews on camera, then makes the video", async ({ page, request }) => {
  test.setTimeout(150_000);
  const token = await owner(request);
  const auth = { Authorization: `Bearer ${token}` };
  // the owner has uploaded a product image to their brand kit
  const slot = await ok<{ upload_url: string; key: string }>(await request.post(`${API}/v1/brand-kit/uploads`, { headers: auth, data: { kind: "product_image", content_type: "image/png", size_bytes: PNG.length } }));
  await ok(await request.put(slot.upload_url, { data: PNG, headers: { "content-type": "image/png" } }));
  await ok(await request.post(`${API}/v1/brand-kit/uploads/confirm`, { headers: auth, data: { key: slot.key } }));
  await toInterview(page, token);

  // they choose it as product footage, with a caption
  const footage = page.getByRole("heading", { name: "Product footage (optional)" });
  await expect(footage).toBeVisible();
  await page.getByLabel("Show this image").check();
  await page.getByLabel("Caption (optional)").fill("The Acme app");
  await page.getByRole("button", { name: "Save product footage" }).click();
  await expect(page.getByText("Saved. 1 shot will be used.")).toBeVisible();
  await expect(page.getByText("AI-generated shots aren't set up")).toHaveCount(0); // demo mode has a stand-in maker

  // nothing paid has run yet, and the system shows what it understood
  await expect(page.getByText("What we understood from your announcement")).toBeVisible();
  await expect(page.getByText(/Acme Farms/).first()).toBeVisible();
  await expect(page.getByText("Your camera must be on.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Get ready for the interview" })).toBeDisabled(); // consent first
  await page.getByLabel("I understand and agree.").check();
  await page.getByRole("button", { name: "Get ready for the interview" }).click();

  // device check: camera showing, the interviewer greets by first name
  await expect(page.getByRole("heading", { name: "Check your camera and microphone" })).toBeVisible();
  await expect(page.getByText("✓ Your camera is on")).toBeVisible();
  await expect(page.getByText(/Hi Ada, welcome\./)).toBeVisible();
  await page.getByRole("button", { name: "Start the interview" }).click();

  // the room: four questions, each answered on camera
  const room = page.getByRole("dialog", { name: "AI interview" });
  await expect(room).toBeVisible();
  for (let q = 1; q <= 4; q++) {
    await expect(room.getByText("Your turn: answer now")).toBeVisible({ timeout: 20_000 });
    await expect(room.getByText(`Question ${q} of 4`)).toBeVisible();
    await expect(room.getByText(/Recording/)).toBeVisible();
    await page.waitForTimeout(1500); // speak for a moment (the fake microphone makes a tone)
    await room.getByRole("button", { name: "I’m done answering" }).click();
    if (q < 4) await expect(room.getByText("Your turn: answer now")).toBeHidden();
  }

  // answers are checked, then the owner reviews them on the dashboard
  await expect(page.getByRole("heading", { name: "Review your interview" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel(/Your answer to question/)).toHaveCount(4);
  await expect(page.getByLabel("How your answers appear in the video")).toHaveValue("full") // news-channel style: the founder full screen;
  await page.getByRole("button", { name: "Make my video" }).click();

  // the presenter is created and the interview is merged in, with no further clicks
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("link", { name: "Download" }).first()).toBeVisible();
  await expect(page.getByText("AI-generated anchor").first()).toBeVisible();

  // the finished video can be edited scene by scene; only what changed is made again
  await expect(page.getByRole("heading", { name: "Edit your video" })).toBeVisible();
  await page.getByLabel("How this answer appears").first().selectOption("full");
  await expect(page.getByText("You have changes waiting.")).toBeVisible();
  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "Apply changes" }).click();
  const projectId = /ai-newsroom\/([0-9a-f]+)/.exec(page.url())![1];
  await expect.poll(async () => {
    const st = (await (await request.get(`${API}/v1/projects/${projectId}`, { headers: auth })).json()).state;
    const types = st === "final_ready" ? ((await (await request.get(`${API}/v1/projects/${projectId}/scenes`, { headers: auth })).json()).scenes as { type: string }[]).map((x) => x.type) : [];
    return st === "final_ready" && types.includes("founder_fullscreen");
  }, { timeout: 60_000 }).toBe(true);
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible();
});

test("AI interview: the camera is required", async ({ page, request }) => {
  test.setTimeout(90_000);
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = (c) => (c && (c as MediaStreamConstraints).video ? Promise.reject(new DOMException("blocked", "NotAllowedError")) : original(c));
  });
  await toInterview(page, await owner(request));
  await page.getByLabel("I understand and agree.").check();
  await page.getByRole("button", { name: "Get ready for the interview" }).click();
  await expect(page.getByRole("alert")).toContainText("This interview needs your camera");
  await expect(page.getByRole("heading", { name: "Check your camera and microphone" })).toHaveCount(0); // cannot continue
  await expect(page.getByRole("button", { name: "Get ready for the interview" })).toBeEnabled();
});

test("AI interview: skipping makes the presenter-only video", async ({ page, request }) => {
  test.setTimeout(90_000);
  await toInterview(page, await owner(request));
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Skip the interview" }).click();
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 60_000 });
});

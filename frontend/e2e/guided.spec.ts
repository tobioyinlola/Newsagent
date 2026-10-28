import { type APIRequestContext, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };

async function ok<T>(r: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(r.status(), await r.text()).toBeLessThan(300);
  return (await r.json()) as T;
}

async function owner(request: APIRequestContext) {
  for (const vendor of ["mock", "renderer", "transcription"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } }));
  const email = `grace${Date.now()}@startup.example.com`;
  const inv = await ok<{ code: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: "Acme Farms", credits: "25", spend_cap: "500" } }));
  await ok(await request.post(`${API}/v1/auth/signup/start`, { data: { invite_code: inv.code, password: "correct horse battery" } }));
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  return (await ok<{ token: string }>(await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: inv.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } }))).token;
}

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("guided flow: details, AI interview, written story, pictures, video, announcement and social post", async ({ page, request }) => {
  test.setTimeout(180_000);
  const token = await owner(request);
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), token);

  // 1. details: the kind of announcement, the key facts, who is presenting (the default is already chosen), no brand kit
  await page.goto("/projects/new");
  await expect(page.getByRole("heading", { name: "Tell us about your announcement" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /\(default\)/ })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("radio", { name: /Funding round/ }).click();
  await page.getByLabel("Tell us the key details").fill("Acme Farms helps smallholder farmers sell produce to verified buyers on their phones. We raised a seed round to open in Kumasi.");
  await page.getByLabel("Your name").fill("Ada Obi");
  await page.getByLabel("Your role").fill("CEO, Acme Farms");
  await page.getByRole("button", { name: "Continue to the interview" }).click();

  // 2. the AI interview opens straight away, four questions on camera
  await expect(page.getByRole("heading", { name: "Your AI interview" })).toBeVisible();
  await page.getByLabel("I understand and agree.").check();
  await page.getByRole("button", { name: "Get ready for the interview" }).click();
  await expect(page.getByText("✓ Your camera is on")).toBeVisible();
  await page.getByRole("button", { name: "Start the interview" }).click();
  const room = page.getByRole("dialog", { name: "AI interview" });
  for (let q = 1; q <= 4; q++) {
    await expect(room.getByText("Your turn: answer now")).toBeVisible({ timeout: 20_000 });
    await expect(room.getByText(`Question ${q} of 4`)).toBeVisible();
    await page.waitForTimeout(1500);
    await room.getByRole("button", { name: "I’m done answering" }).click();
    if (q < 4) await expect(room.getByText("Your turn: answer now")).toBeHidden();
  }

  // 3. every answer is featured by default, then the story is written
  await expect(page.getByRole("heading", { name: "Review your interview" })).toBeVisible({ timeout: 60_000 });
  const boxes = page.getByLabel("Feature this answer in the video");
  await expect(boxes).toHaveCount(4);
  await expect(boxes.nth(0)).toBeChecked();
  await expect(boxes.nth(1)).toBeChecked();
  await expect(boxes.nth(3)).toBeChecked();
  await expect(boxes.nth(3)).toBeEnabled();
  await expect(page.getByRole("button", { name: "Skip the interview" })).toHaveCount(0);
  await page.getByRole("button", { name: "Write my story" }).click();

  // 4. review the story, add two pictures, approve
  await expect(page.getByRole("heading", { name: "Your news story" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "What your presenter says" })).toBeVisible();
  await expect(page.getByLabel("Outro")).toHaveValue("That was Cover Founder News. Thank you for watching.");
  await expect(page.getByLabel(/Interview question/)).toHaveCount(0); // the questions are fixed once the answers are recorded
  await expect(page.getByRole("button", { name: "Make my video" })).toBeDisabled(); // pictures first
  await page.getByLabel("Choose pictures").setInputFiles([{ name: "one.png", mimeType: "image/png", buffer: PNG }, { name: "two.png", mimeType: "image/png", buffer: PNG }]);
  await expect(page.getByAltText("Your picture")).toHaveCount(2, { timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Make my video" })).toBeEnabled();
  const claims = page.getByRole("group", { name: "Confirm these claims are accurate" });
  if (await claims.count()) for (const box of await claims.getByRole("checkbox").all()) await box.check();
  await page.getByRole("button", { name: "Make my video" }).click();

  // 5. the video, the written announcement and the separate social post
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("link", { name: "Download" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your announcement" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Social post" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy the social post" })).toBeVisible();
  await expect(page.getByText("AI-generated anchor").first()).toBeVisible();
});

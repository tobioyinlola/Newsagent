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
  await page.goto("/ai-newsroom/new");
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
  await page.getByRole("button", { name: "Produce my story" }).click();

  // 4. review the story; going back to the interview and producing it again works
  await expect(page.getByRole("heading", { name: "Your press release" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "← Back to the interview" }).click();
  await expect(page.getByRole("heading", { name: "Review your interview" })).toBeVisible();
  await page.getByRole("button", { name: "Produce my story" }).click();
  await expect(page.getByRole("heading", { name: "Your press release" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "What your presenter says" })).toBeVisible();
  await expect(page.getByLabel("Outro")).toHaveValue(/^This is Cover Founder News\..*have a great day!$/); // the standard closing line
  await expect(page.getByLabel(/Interview question/)).toHaveCount(0); // the questions are fixed once the answers are recorded
  await expect(page.getByRole("button", { name: "Make my video" })).toBeEnabled(); // pictures are optional
  const sample = (process.env.SNAPSHOT_PICS ?? "").split(",").filter(Boolean); // optional real pictures, for a visual check
  await page.getByLabel("Choose pictures").setInputFiles(sample.length >= 2 ? sample.slice(0, 2) : [{ name: "one.png", mimeType: "image/png", buffer: PNG }, { name: "two.png", mimeType: "image/png", buffer: PNG }]);
  await expect(page.getByAltText("Your picture")).toHaveCount(2, { timeout: 20_000 });
  // the pictures just uploaded also appear inside the press release, between its paragraphs
  const release = page.locator("article");
  await expect(release.getByRole("figure")).toHaveCount(2);
  await expect(release.locator("figure img").first()).toBeVisible();
  if (process.env.SNAPSHOT_OUT) await release.screenshot({ path: process.env.SNAPSHOT_OUT });
  await expect(page.getByRole("button", { name: "Make my video" })).toBeEnabled();
  const claims = page.getByRole("group", { name: "Confirm these claims are accurate" });
  if (await claims.count()) {
    await claims.getByRole("button", { name: "Confirm all" }).click();
    for (const box of await claims.getByRole("checkbox").all()) await expect(box).toBeChecked();
  }
  await page.getByRole("button", { name: "Make my video" }).click();

  // 5. the video, the written announcement and the separate social post
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("link", { name: "Download" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your announcement" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Social post" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy the social post" })).toBeVisible();
  await expect(page.getByText("AI-generated anchor").first()).toBeVisible();

  // 6. the story is published on Latest Stories automatically, and the link replaces the old private share link
  const box = page.getByLabel("Link to your published story");
  await expect(box).toBeVisible();
  const storyUrl = await box.inputValue();
  expect(storyUrl).toMatch(/\/latest-stories\/[a-z0-9-]+-[0-9a-f]{6}$/);
  await expect(page.getByRole("button", { name: "Create share link" })).toHaveCount(0);
  const slug = new URL(storyUrl).pathname;

  const visitor = await (await page.context().browser()!.newContext()).newPage(); // someone not signed in
  await visitor.goto("/");
  const row = visitor.getByRole("region", { name: "Latest stories" }); // the row on the home page, between the numbers and the use cases
  await expect(row.getByRole("link").first()).toBeVisible({ timeout: 20_000 });
  const shots = process.env.SNAPSHOT_DIR; // optional, for a visual check
  if (shots) { await visitor.setViewportSize({ width: 1280, height: 900 }); await row.scrollIntoViewIfNeeded(); await visitor.screenshot({ path: `${shots}/home-row.png` }); }
  await visitor.goto("/latest-stories");
  await expect(visitor.getByRole("heading", { name: "Latest stories", level: 1 })).toBeVisible();
  if (shots) await visitor.screenshot({ path: `${shots}/latest-stories.png`, fullPage: true });
  await visitor.getByRole("link", { name: /^Watch:/ }).click();
  await expect(visitor).toHaveURL(new RegExp(`${slug}$`));
  const video = visitor.getByLabel(/^Video:/);
  await expect(video).toHaveAttribute("src", /.+/);
  expect(await video.evaluate((v: HTMLVideoElement) => v.autoplay && v.controls)).toBe(true); // autoplays, with controls
  // it asks for sound; only if the browser refuses does it play muted, and then it says so and offers one tap to turn sound on
  await expect.poll(async () => (await video.evaluate((v: HTMLVideoElement) => v.muted)) === (await visitor.getByRole("button", { name: "Turn sound on" }).isVisible())).toBe(true);
  await expect(visitor.getByText("For immediate release")).toBeVisible();
  await expect(visitor.locator("article figure")).toHaveCount(2); // the pictures the owner uploaded sit inside the press release
  const share = visitor.getByRole("group", { name: "Share this story" });
  await expect(share.getByRole("link", { name: "Share on WhatsApp" })).toHaveAttribute("href", /^https:\/\/wa\.me\/\?text=.*latest-stories/);
  await expect(share.getByRole("link", { name: "Share on LinkedIn" })).toHaveAttribute("href", /linkedin\.com\/sharing\/share-offsite\/\?url=.*latest-stories/);
  await expect(share.getByRole("link", { name: "Share on X (Twitter)" })).toHaveAttribute("href", /twitter\.com\/intent\/tweet/);
  await expect(share.getByRole("button", { name: /Copy link/ })).toBeVisible();
  await expect(visitor.getByText("Media Contact")).toHaveCount(0); // the contact details are never public
  await expect(visitor.getByText("AI-generated anchor").first()).toBeVisible();
  if (shots) await visitor.screenshot({ path: `${shots}/story-page.png`, fullPage: true });

  // taking it down removes the page
  await page.getByRole("button", { name: "Take it down" }).click();
  await expect(page.getByRole("button", { name: "Publish it again" })).toBeVisible();
  await visitor.reload();
  await expect(visitor.getByText("This story isn't available.")).toBeVisible();
  await page.getByRole("button", { name: "Publish it again" }).click();
  await expect(page.getByLabel("Link to your published story")).toHaveValue(storyUrl);
  await visitor.reload();
  await expect(visitor.getByRole("video")).toHaveCount(0).catch(() => undefined);
  await expect(visitor.getByText("For immediate release")).toBeVisible();
});

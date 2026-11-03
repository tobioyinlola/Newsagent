import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };

// A video is optional when distributing: a business with no finished video can still send its own story to outlets.
test("a business with no video can write its own story, pay and submit a distribution request", async ({ page, request, browser }) => {
  const email = `novideo${Date.now()}@example.com`;
  const invited = await (await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: "No Video Co", credits: "250", spend_cap: "100" } })).json();
  await request.post(`${API}/v1/auth/signup/start`, { data: { invite_code: invited.code, password: "correct horse battery" } });
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  const signup = await (await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: invited.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } })).json();
  const headers = { Authorization: `Bearer ${signup.token}` };
  const balance = async () => Number((await (await request.get(`${API}/v1/billing/summary`, { headers })).json()).credit_balance);
  const before = await balance();

  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), signup.token);
  await page.goto("/distribution/request");
  // no videos and no stories yet, and the request can still be started
  await expect(page.getByRole("button", { name: "Start a distribution request" })).toBeEnabled();
  await page.getByRole("button", { name: "Start a distribution request" }).click();
  await page.getByRole("checkbox", { name: /^Tribune / }).check();
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Choose your video and announcement" })).toBeVisible();
  await expect(page.getByText("You don't have a finished video yet, so your story will be sent on its own.")).toBeVisible();
  await expect(page.getByLabel("Video (optional)")).toHaveValue("");
  await expect(page.getByRole("radio", { name: /Write or paste my own/ })).toBeChecked(); // no story to start from, so their own
  await page.getByLabel("Headline", { exact: true }).fill("No Video Co opens its first store");
  await page.getByLabel("Press announcement", { exact: true }).fill("No Video Co has opened its first store in Lagos, serving customers across the city.");
  await page.getByRole("button", { name: "Continue", exact: true }).click(); // no 'select a video' error

  await expect(page.getByRole("heading", { name: "Primary contact and company images" })).toBeVisible();
  await page.getByLabel("Contact name", { exact: true }).fill("Ada Obi");
  await page.getByLabel("Contact email", { exact: true }).fill(email);
  await page.getByLabel("Primary phone number", { exact: true }).fill("+2348031234567");
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Review your distribution request" })).toBeVisible();
  await expect(page.getByText("No video: the story only")).toBeVisible();
  await page.getByRole("button", { name: "Pay and submit" }).click();
  await expect(page.getByRole("dialog", { name: "Distribution submitted" })).toBeVisible();
  await page.getByRole("button", { name: "Done", exact: true }).click();

  // paid as usual, with no video attached
  expect(await balance()).toBeLessThan(before);
  const rows = (await (await request.get(`${API}/v1/distribution`, { headers })).json()) as { status: string; paid: boolean; data: { project_id: string | null } }[];
  expect(rows.some((r) => r.paid && r.status !== "draft" && !r.data?.project_id)).toBe(true);

  // the back office copes with a request that has no video
  const admin = await browser.newContext();
  const ap = await admin.newPage();
  await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await ap.goto("/admin/distribution");
  const row = ap.locator("details").filter({ has: ap.locator("summary").filter({ hasText: "No Video Co opens its first store" }) }).first();
  await row.locator("summary").click();
  await expect(row).toContainText("No Video Co has opened its first store");
  await row.getByRole("button", { name: "Load video, logo and pictures" }).click();
  await expect(row.getByRole("link", { name: "Download selected video" })).toHaveCount(0);
  await expect(row.getByRole("alert")).toHaveCount(0);
  await admin.close();
});

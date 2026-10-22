import { type APIRequestContext, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const bearer = (e: string) => ({ Authorization: `Bearer dev:${e}` });
const OPS = bearer("ops@example.com");

async function ok<T>(r: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(r.status(), await r.text()).toBeLessThan(300);
  return (await r.json()) as T;
}

let n = 0;
// each test gets its own owner so they never collide on the shared database
async function setup(request: APIRequestContext) {
  const OWNER_EMAIL = `pilot${Date.now()}${n++}@startup.example.com`;
  for (const vendor of ["mock", "renderer", "transcription"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } }));
  const OWNER = bearer(OWNER_EMAIL);
  const inv = await ok<{ code: string; workspace_id: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: OWNER_EMAIL, workspace_name: "Pilot Co", credits: "20", spend_cap: "500" } }));
  await ok(await request.post(`${API}/v1/auth/redeem`, { headers: OWNER, data: { code: inv.code } }));
  return { workspace: inv.workspace_id, email: OWNER_EMAIL, OWNER };
}

test("moderation holds risky content; the operator reviews it in the console; the owner continues", async ({ browser, request }) => {
  const { email: OWNER_EMAIL, OWNER } = await setup(request);
  const p = await ok<{ id: string }>(await request.post(`${API}/v1/projects`, { headers: OWNER, data: { brief_text: "Pilot Co sells solar lamps to market traders in Kumasi." } }));
  const sc = await ok<{ ticker_lines: string[]; lower_thirds: unknown[] }>(await request.post(`${API}/v1/projects/${p.id}/script/generate`, { headers: OWNER }));
  await ok(await request.put(`${API}/v1/projects/${p.id}/script`, { headers: OWNER, data: { segments: [{ kind: "intro", text: "Pilot Co lamps come with guaranteed returns for every trader." }], ticker_lines: sc.ticker_lines, lower_thirds: sc.lower_thirds, interview_questions: [] } }));

  const ownerCtx = await browser.newContext();
  await ownerCtx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${OWNER_EMAIL}`);
  const owner = await ownerCtx.newPage();
  await owner.goto(`/projects/${p.id}`);
  await owner.getByRole("button", { name: "Approve and make my video" }).click();
  await expect(owner.getByRole("alert")).toContainText("member of our team is checking");
  await owner.reload();
  await expect(owner.getByText("A member of our team is checking your script")).toBeVisible();

  // operator
  const opsCtx = await browser.newContext();
  await opsCtx.addInitScript((t) => localStorage.setItem("newsagent.token", t), "dev:ops@example.com");
  const ops = await opsCtx.newPage();
  await ops.goto("/admin");
  await ops.getByRole("tab", { name: "Review queue" }).click();
  await expect(ops.getByLabel("Content under review")).toContainText("guaranteed returns");
  await expect(ops.getByText("financial promises")).toBeVisible();
  await ops.getByLabel("Note to the owner").fill("Fine, but avoid return promises next time.");
  await ops.getByRole("button", { name: "Approve" }).click();
  await expect(ops.getByText("Nothing waiting.")).toBeVisible();

  // owner carries on
  await owner.getByRole("button", { name: "Approve and make my video" }).click();
  await expect(owner.getByRole("heading", { name: "Your video" })).toBeVisible({ timeout: 60_000 });
  await ops.getByRole("tab", { name: "Audit log" }).click();
  await expect(ops.getByRole("cell", { name: "moderation.approve" })).toBeVisible();
});

test("owner buys credits through checkout; operator sees costs and can pause paid steps", async ({ browser, request }) => {
  const { workspace: wid, email: OWNER_EMAIL } = await setup(request);
  await ok(await request.post(`${API}/v1/admin/packs`, { headers: OPS, data: { name: "Starter", credits: "30", price_usd: "29" } }));

  const ownerCtx = await browser.newContext();
  await ownerCtx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${OWNER_EMAIL}`);
  const owner = await ownerCtx.newPage();
  await owner.goto("/billing");
  await expect(owner.getByLabel("Credit balance")).toContainText("20.00");
  await owner.getByRole("button", { name: "Buy Starter" }).click();
  await expect(owner.getByText("This is a test checkout")).toBeVisible();
  await owner.getByRole("button", { name: "Pay now (test)" }).click();
  await expect(owner.getByText("Payment received")).toBeVisible();
  await expect(owner.getByLabel("Credit balance")).toContainText("50.00");
  await expect(owner.getByRole("cell", { name: /Purchase/ })).toBeVisible();

  const opsCtx = await browser.newContext();
  await opsCtx.addInitScript((t) => localStorage.setItem("newsagent.token", t), "dev:ops@example.com");
  const ops = await opsCtx.newPage();
  await ops.goto("/admin");
  await ops.getByRole("button", { name: "Pause all paid steps" }).click();
  await expect(ops.getByText("Paid steps are paused.")).toBeVisible();
  await ops.getByRole("button", { name: "Resume paid steps" }).click();
  await expect(ops.getByText("Paid steps are paused.")).toHaveCount(0);
  await ops.getByRole("tab", { name: "Costs" }).click();
  await expect(ops.getByRole("heading", { name: /Cost per finished video/ })).toBeVisible();
  expect(wid).toBeTruthy();
});

test("owner can download their data and delete the workspace", async ({ browser, request }) => {
  const { email: OWNER_EMAIL, OWNER } = await setup(request);
  const ctx = await browser.newContext({ acceptDownloads: true });
  await ctx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${OWNER_EMAIL}`);
  const page = await ctx.newPage();
  await page.goto("/account");
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download my data" }).click();
  expect((await dl).suggestedFilename()).toBe("my-data.json");
  const del = page.getByRole("button", { name: "Delete everything" });
  await expect(del).toBeDisabled();
  await page.getByLabel(/Type "DELETE Pilot Co"/).fill("DELETE Pilot Co");
  await del.click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect((await request.get(`${API}/v1/me`, { headers: OWNER })).status()).toBe(403);
});

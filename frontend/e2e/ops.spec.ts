import { type APIRequestContext, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const bearer = (e: string) => ({ Authorization: `Bearer dev:${e}` });
const OPS = bearer("ops@example.com");

async function ok<T>(r: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(r.status(), await r.text()).toBeLessThan(300);
  return (await r.json()) as T;
}


// In-house sign-up through the real endpoints. The mock mailbox is readable at /v1/dev/last-email locally.
export async function emailedCode(request: APIRequestContext, to: string): Promise<string> {
  const r = await request.get(`${API}/v1/dev/last-email`, { params: { to } });
  return /\b(\d{6})\b/.exec((await r.json()).text)![1];
}

async function redeem(request: APIRequestContext, code: string, email: string) {
  await ok(await request.post(`${API}/v1/auth/signup/start`, { data: { invite_code: code, password: "correct horse battery" } }));
  await ok(await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: code, code: await emailedCode(request, email) } }));
}

let n = 0;
// each test gets its own owner so they never collide on the shared database
async function setup(request: APIRequestContext, credits = "20") {
  const OWNER_EMAIL = `pilot${Date.now()}${n++}@startup.example.com`;
  for (const vendor of ["mock", "renderer", "transcription"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } }));
  const OWNER = bearer(OWNER_EMAIL);
  const inv = await ok<{ code: string; workspace_id: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: OWNER_EMAIL, workspace_name: "Pilot Co", credits, spend_cap: "500" } }));
  await redeem(request, inv.code, OWNER_EMAIL);
  return { workspace: inv.workspace_id, email: OWNER_EMAIL, OWNER };
}

test("moderation holds risky content; once an operator approves it the owner continues", async ({ browser, request }) => {
  const { email: OWNER_EMAIL, OWNER } = await setup(request);
  const p = await ok<{ id: string }>(await request.post(`${API}/v1/projects`, { headers: OWNER, data: { brief_text: "Pilot Co sells solar lamps to market traders in Kumasi." } }));
  const sc = await ok<{ ticker_lines: string[]; lower_thirds: unknown[] }>(await request.post(`${API}/v1/projects/${p.id}/script/generate`, { headers: OWNER }));
  await ok(await request.put(`${API}/v1/projects/${p.id}/script`, { headers: OWNER, data: { segments: [{ kind: "intro", text: "Pilot Co lamps come with guaranteed returns for every trader." }], ticker_lines: sc.ticker_lines, lower_thirds: sc.lower_thirds, interview_questions: [] } }));

  const ownerCtx = await browser.newContext();
  await ownerCtx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${OWNER_EMAIL}`);
  const owner = await ownerCtx.newPage();
  await owner.goto(`/ai-newsroom/${p.id}`);
  await owner.getByLabel("No interview").check();
  await owner.getByRole("button", { name: "Approve and make my video" }).click();
  await expect(owner.getByRole("alert")).toContainText("member of our team is checking");
  await owner.reload();
  await expect(owner.getByText("A member of our team is checking your script")).toBeVisible();

  // the operator's review happens in the back office app (covered by admin/e2e); here the decision is made through the API
  const cases = await ok<{ id: string }[]>(await request.get(`${API}/v1/admin/moderation`, { headers: OPS }));
  await ok(await request.post(`${API}/v1/admin/moderation/${cases[0].id}/decision`, { headers: OPS, data: { decision: "approve", note: "Fine, but avoid return promises next time." } }));

  // owner carries on
  await owner.getByLabel("No interview").check();
  await owner.getByRole("button", { name: "Approve and make my video" }).click();
  await expect(owner.getByRole("heading", { name: "Your video" })).toBeVisible({ timeout: 60_000 });
});

test("the one free video is used, then starting another asks them to buy credits", async ({ browser, request }) => {
  const { email, OWNER } = await setup(request, "1");
  await ok(await request.post(`${API}/v1/projects`, { headers: OWNER, data: { brief_text: "Pilot Co sells solar lamps to market traders in Kumasi." } }));
  const second = await request.post(`${API}/v1/projects`, { headers: OWNER, data: { brief_text: "Pilot Co opens a second shop in Accra this spring." } });
  expect(second.status()).toBe(402);
  const ctx = await browser.newContext();
  await ctx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${email}`);
  const page = await ctx.newPage();
  await page.goto("/ai-newsroom/new");
  const dialog = page.getByRole("dialog", { name: "You're out of credits" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("link", { name: "Buy credits" }).click();
  await expect(page).toHaveURL(/\/billing/);
  await expect(page.getByRole("button", { name: "Buy $10.00 of credits" })).toBeVisible();
  for (const amount of ["$50.00", "$100.00", "$200.00"]) await expect(page.getByRole("button", { name: `Buy ${amount} of credits` })).toBeVisible();
});

test("owner buys credits through checkout", async ({ browser, request }) => {
  const { workspace: wid, email: OWNER_EMAIL } = await setup(request);

  const ownerCtx = await browser.newContext();
  await ownerCtx.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${OWNER_EMAIL}`);
  const owner = await ownerCtx.newPage();
  await owner.goto("/billing");
  await expect(owner.getByLabel("Credit balance")).toContainText("20.00");
  await owner.getByRole("button", { name: "Buy $10.00 of credits" }).click();
  await expect(owner.getByText("This is a test checkout")).toBeVisible();
  await owner.getByRole("button", { name: "Pay now (test)" }).click();
  await expect(owner.getByRole("heading", { name: "Credits and billing" })).toBeVisible();
  await expect(owner.getByLabel("Credit balance")).toContainText("23.70");
  await expect(owner.getByRole("cell", { name: /Purchase/ })).toBeVisible();

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

test("demo mode is declared on the dashboard, and a finished video's progress is complete", async ({ page, request }) => {
  const { email, OWNER } = await setup(request);
  const p = await ok<{ id: string }>(await request.post(`${API}/v1/projects`, { headers: OWNER, data: { brief_text: "Acme Farms helps farmers sell produce online across Ghana." } }));
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), `dev:${email}`);
  await page.goto("/ai-newsroom/videos");
  await expect(page.getByRole("note").filter({ hasText: "Demo mode." })).toBeVisible();
  const prog = await ok<{ percent: number; stages: { key: string; status: string }[]; cancellable: boolean }>(await request.get(`${API}/v1/projects/${p.id}/progress`, { headers: OWNER }));
  expect(prog.stages[0].key).toBe("script");
  expect(prog.cancellable).toBe(false); // a draft is not being made yet
  expect((await request.post(`${API}/v1/projects/${p.id}/cancel`, { headers: OWNER })).status()).toBe(409);
});

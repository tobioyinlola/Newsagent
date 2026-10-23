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
async function setup(request: APIRequestContext) {
  const OWNER_EMAIL = `pilot${Date.now()}${n++}@startup.example.com`;
  for (const vendor of ["mock", "renderer", "transcription"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } }));
  const OWNER = bearer(OWNER_EMAIL);
  const inv = await ok<{ code: string; workspace_id: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: OWNER_EMAIL, workspace_name: "Pilot Co", credits: "20", spend_cap: "500" } }));
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
  await owner.goto(`/projects/${p.id}`);
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

test("owner buys credits through checkout", async ({ browser, request }) => {
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

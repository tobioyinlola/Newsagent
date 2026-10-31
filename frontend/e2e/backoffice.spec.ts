import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { type APIRequestContext, type Page, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const sidebar = (page: Page) => page.getByRole("navigation", { name: "Back office" });
const OPS = { Authorization: "Bearer dev:ops@example.com" };
const PASSWORD = "correct horse battery";
let n = 0;

async function ok<T>(r: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(r.status(), await r.text()).toBeLessThan(300);
  return (await r.json()) as T;
}
const codeFor = async (request: APIRequestContext, to: string) => /\b(\d{6})\b/.exec((await (await request.get(`${API}/v1/dev/last-email`, { params: { to } })).json()).text)![1];

// a customer signed up through the real endpoints
async function customer(request: APIRequestContext, company: string, credits = "25") {
  const email = `owner${Date.now()}${n++}@customer.example.com`;
  const inv = await ok<{ code: string; workspace_id: string }>(await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: company, credits } }));
  await ok(await request.post(`${API}/v1/auth/signup/start`, { data: { invite_code: inv.code, password: PASSWORD } }));
  const s = await ok<{ token: string }>(await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: inv.code, code: await codeFor(request, email) } }));
  return { email, workspace: inv.workspace_id, headers: { Authorization: `Bearer ${s.token}` } };
}

// `dev:` tokens (local only) stand in for a signed-in operator; the real sign-in is tested separately below
async function asOperator(page: Page) {
  await page.addInitScript(() => { if (!sessionStorage.getItem("seeded")) { sessionStorage.setItem("seeded", "1"); sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"); } });
}

test("the overview shows sign-ups, who is paying and how videos are doing", async ({ page, request }) => {
  for (const vendor of ["mock", "renderer"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } }));
  const a = await customer(request, "Acme Farms");
  await customer(request, "Beta Pay");
  const co = await ok<{ checkout_id: string }>(await request.post(`${API}/v1/billing/checkout`, { headers: a.headers, data: { amount_usd: "50" } }));
  await ok(await request.post(`${API}/v1/billing/dev/pay/${co.checkout_id}`, { headers: a.headers }));
  await ok(await request.post(`${API}/v1/projects`, { headers: a.headers, data: { brief_text: "Acme Farms helps farmers sell produce online across Ghana." } }));

  await asOperator(page);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  const figures = page.getByLabel("Key figures");
  await expect(figures.getByText("Paying companies")).toBeVisible();
  await expect(figures.getByText("$50").first()).toBeVisible(); // revenue
  const latest = page.getByRole("table", { name: "Latest sign-ups" });
  await expect(latest.getByRole("row", { name: /Acme Farms.*Paying/ })).toBeVisible();
  await expect(latest.getByRole("row", { name: /Beta Pay.*Not yet/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /New sign-ups per day/ })).toBeVisible();
  await expect(page.getByRole("table", { name: "Top customers" }).getByRole("link", { name: "Acme Farms" })).toBeVisible();
  await page.getByRole("button", { name: "90 days" }).click();
  await expect(page.getByRole("button", { name: "90 days" })).toHaveAttribute("aria-pressed", "true");
});

test("find a customer and see their people, videos and payments", async ({ page, request }) => {
  await customer(request, "Zeta Logistics");
  const b = await customer(request, "Yoyo Foods");
  await asOperator(page);
  await page.goto("/admin/customers");
  await page.getByLabel("Search customers").fill("yoyo");
  await page.getByRole("button", { name: "Search" }).click();
  const rows = page.getByRole("table", { name: /Customers/ });
  await expect(rows.getByRole("link", { name: "Yoyo Foods" })).toBeVisible();
  await expect(rows.getByRole("link", { name: "Zeta Logistics" })).toHaveCount(0);
  await rows.getByRole("link", { name: "Yoyo Foods" }).click();
  await expect(page.getByRole("heading", { name: "Yoyo Foods" })).toBeVisible();
  await expect(page.getByRole("table", { name: "People" }).getByText(b.email)).toBeVisible();
  await expect(page.getByText("No videos yet.")).toBeVisible();
  await expect(page.getByText("No payments yet.")).toBeVisible();
});

test("revenue lists paying companies and every payment, including offline ones", async ({ page, request }) => {
  const c = await customer(request, "Gamma Grains");
  await ok(await request.post(`${API}/v1/admin/workspaces/${c.workspace}/credits`, { headers: OPS, data: { credits: "40", ref: `INV-${Date.now()}`, note: "bank transfer" } }));
  await asOperator(page);
  await page.goto("/admin/revenue");
  await expect(page.getByRole("heading", { name: "Revenue" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Paying companies" }).getByRole("link", { name: "Gamma Grains" })).toBeVisible();
  await expect(page.getByRole("table", { name: /Payments, newest first/ }).getByText("not recorded").first()).toBeVisible();
});

test("operators review held content, pause and resume paid steps, and see it in the audit log", async ({ page, request }) => {
  for (const vendor of ["mock", "renderer"]) await ok(await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } }));
  const c = await customer(request, "Delta Lamps");
  const p = await ok<{ id: string }>(await request.post(`${API}/v1/projects`, { headers: c.headers, data: { brief_text: "Delta Lamps sells solar lamps to market traders in Kumasi." } }));
  const sc = await ok<{ ticker_lines: string[]; lower_thirds: unknown[] }>(await request.post(`${API}/v1/projects/${p.id}/script/generate`, { headers: c.headers }));
  await ok(await request.put(`${API}/v1/projects/${p.id}/script`, { headers: c.headers, data: { segments: [{ kind: "intro", text: "Delta lamps come with guaranteed returns for every trader." }], ticker_lines: sc.ticker_lines, lower_thirds: sc.lower_thirds, interview_questions: [] } }));
  expect((await request.post(`${API}/v1/projects/${p.id}/script/approve`, { headers: c.headers, data: {} })).status()).toBe(409); // held for review

  await asOperator(page);
  await page.goto("/admin");
  await expect(page.getByLabel("Needs attention").getByText(/waiting for review/)).toBeVisible();
  await page.getByRole("link", { name: "Review now" }).click();
  await expect(page.getByLabel("Content under review")).toContainText("guaranteed returns");
  await expect(page.getByText("financial promises")).toBeVisible();
  await page.getByLabel("Note to the owner").fill("Fine, but avoid return promises next time.");
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Nothing waiting.")).toBeVisible();

  await sidebar(page).getByRole("link", { name: "Operations" }).click();
  await page.getByRole("button", { name: "Pause all paid steps" }).click();
  await expect(page.getByText("Paid steps are paused.").first()).toBeVisible();
  await page.goto("/admin");
  await expect(page.getByLabel("Needs attention").getByText("Paid steps are paused.")).toBeVisible();
  await sidebar(page).getByRole("link", { name: "Operations" }).click();
  await page.getByRole("button", { name: "Resume paid steps" }).click();
  await expect(page.getByText("Paid steps are paused.")).toHaveCount(0);

  await sidebar(page).getByRole("link", { name: "Costs" }).click();
  await expect(page.getByRole("heading", { name: /Cost per finished video/ })).toBeVisible();
  await sidebar(page).getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByRole("cell", { name: "moderation.approve" })).toBeVisible();
});

test("a customer cannot use the back office", async ({ page, request }) => {
  const c = await customer(request, "Epsilon Eats");
  const token = c.headers.Authorization.replace("Bearer ", "");
  await page.addInitScript((t) => sessionStorage.setItem("newsagent.admin.token", t), token);
  await page.goto("/admin");
  await expect(page.getByText("isn't a Cover Founder operator")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Overview" })).toHaveCount(0);
  for (const path of ["/v1/admin/overview", "/v1/admin/customers", "/v1/admin/payments"]) expect((await request.get(`${API}${path}`, { headers: c.headers })).status()).toBe(403);
});

test("operators sign in with a password and a code emailed to them, and are signed out when they leave", async ({ page, request }) => {
  // the operator has no password yet: they set one with "forgot password"
  await ok(await request.post(`${API}/v1/auth/password/forgot`, { data: { email: "ops@example.com" } }));
  await ok(await request.post(`${API}/v1/auth/password/reset`, { data: { email: "ops@example.com", code: await codeFor(request, "ops@example.com"), new_password: PASSWORD } }));

  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/login/);
  await page.getByLabel("Email").fill("ops@example.com");
  await page.getByLabel("Password", { exact: true }).fill("not the password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("don't match");
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await page.getByLabel("6-digit code").fill("000000");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByLabel("6-digit code").fill(await codeFor(request, "ops@example.com"));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Sign out" }).click(); // the confirmation
  await expect(page).toHaveURL(/\/admin\/login/);
  await page.goto("/admin/customers");
  await expect(page).toHaveURL(/\/admin\/login/);
});

test("the sidebar collapses to icons and remembers it", async ({ page }) => {
  await asOperator(page);
  await page.goto("/admin");
  await expect(sidebar(page).getByRole("link", { name: "Customers" })).toBeVisible();
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
  await page.reload();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
  await sidebar(page).getByRole("link", { name: "Customers" }).click();
  await expect(page).toHaveURL(/\/admin\/customers/);
});

test("operators upload presenter clips, see them listed, switch them off and delete them", async ({ page }) => {
  const mp4 = path.join(os.tmpdir(), `presenter-${Date.now()}.mp4`);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=1280x720:r=30:d=6", "-f", "lavfi", "-i", "sine=frequency=440:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", mp4]);
  await asOperator(page);
  await page.goto("/admin");
  await sidebar(page).getByRole("link", { name: "Presenter clips" }).click();
  await expect(page.getByRole("heading", { name: "Presenter clips" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload clip" })).toBeDisabled(); // nothing chosen, rights not confirmed
  await page.getByLabel("Title").fill("Studio wide, evening");
  await page.getByLabel("How it is used").selectOption("intro");
  await page.getByLabel("Video file").setInputFiles(mp4);
  await expect(page.getByRole("button", { name: "Upload clip" })).toBeDisabled(); // rights still unconfirmed
  await page.getByLabel(/I own this footage/).check();
  await page.getByRole("button", { name: "Upload clip" }).click();
  await expect(page.getByText("Added. It will be used in new videos from now on.")).toBeVisible();
  const card = page.getByRole("listitem").filter({ hasText: "Studio wide, evening" });
  await expect(card).toContainText(/6\.0 s · \d+×\d+ · with sound/);
  await expect(card.getByLabel("Preview: Studio wide, evening")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Opening shot (1 in use)" })).toBeVisible();
  await card.getByRole("button", { name: "In use: switch off" }).click();
  await expect(page.getByRole("heading", { name: "Opening shot (0 in use)" })).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await card.getByRole("button", { name: "Delete" }).click();
  await expect(card).toHaveCount(0);
});

test("a customer cannot reach the presenter clips", async ({ request }) => {
  const c = await customer(request, "Gamma Co");
  expect((await request.get(`${API}/v1/admin/presenter-clips`, { headers: c.headers })).status()).toBe(403);
});

test("operators delete a customer's video from the back office; customers can't", async ({ page, request }) => {
  const a = await customer(request, "Delete Me Co");
  const p = await ok<{ id: string }>(await request.post(`${API}/v1/projects`, { headers: a.headers, data: { brief_text: "Delete Me Co sells tea to offices across Lagos." } }));
  expect((await request.delete(`${API}/v1/projects/${p.id}`, { headers: a.headers })).status()).toBe(405);
  await asOperator(page);
  await page.goto(`/admin/customers/${a.workspace}`);
  await expect(page.getByRole("cell", { name: p.id.slice(0, 6) })).toBeVisible();
  page.on("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete video" }).click();
  await expect(page.getByText("No videos yet.")).toBeVisible();
});

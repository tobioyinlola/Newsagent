import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };

async function readyBusiness(request: import("@playwright/test").APIRequestContext, opts: { country?: string; credits: string }) {
  for (const vendor of ["mock", "renderer"]) {
    expect((await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } })).ok()).toBeTruthy();
  }
  // open sign-up, the way a business creates its own workspace (an invited workspace has no country of its own)
  const email = `readyplan${Date.now()}${Math.floor(Math.random() * 1e4)}@business.example.com`;
  const started = await request.post(`${API}/v1/auth/signup/start`, { data: { accepted_terms: true, email, business_name: "Ready Plan Test", city: "Lagos", country: opts.country ?? "Atlantis", industry: "technology", password: "correct horse battery" } });
  expect(started.ok(), await started.text()).toBeTruthy();
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  const signup = await (await request.post(`${API}/v1/auth/signup/verify`, { data: { email, code: /\b(\d{6})\b/.exec(mail.text)![1] } })).json();
  const me = await (await request.get(`${API}/v1/me`, { headers: { Authorization: `Bearer ${signup.token}` } })).json();
  expect((await request.patch(`${API}/v1/admin/workspaces/${me.workspace_id}`, { headers: OPS, data: { credit_balance: opts.credits, spend_cap: "100000" } })).ok()).toBeTruthy();
  const headers = { Authorization: `Bearer ${signup.token}` };
  const project = await (await request.post(`${API}/v1/projects`, { headers, data: { brief_text: "Acme helps farmers sell fresh produce to local businesses in Lagos." } })).json();
  const script = await (await request.post(`${API}/v1/projects/${project.id}/script/generate`, { headers })).json();
  expect((await request.put(`${API}/v1/projects/${project.id}/script`, { headers, data: { segments: [{ kind: "intro", text: "Acme helps farmers sell produce." }], ticker_lines: script.ticker_lines, lower_thirds: script.lower_thirds, interview_questions: script.interview_questions } })).ok()).toBeTruthy();
  expect((await request.post(`${API}/v1/projects/${project.id}/script/approve`, { headers })).ok()).toBeTruthy();
  await expect.poll(async () => (await (await request.get(`${API}/v1/projects/${project.id}`, { headers })).json()).state).toBe("final_ready");
  return { token: signup.token as string, projectId: project.id as string };
}

test("a finished video offers a plan made for the business, and starts the request with its outlets chosen", async ({ page, request }) => {
  const { token, projectId } = await readyBusiness(request, { country: "Nigeria", credits: "250" });
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), token);
  await page.goto(`/ai-newsroom/${projectId}`);
  const dialog = page.getByRole("alertdialog", { name: "Take your story to over 2,500 media outlets?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Recommended for you")).toBeVisible();
  await expect(dialog.getByText(/You have (249|250) credits, so it fits\./)).toBeVisible();
  const line = (await dialog.getByText(/ plan: \d+ outlets? for /).textContent()) ?? "";
  const count = Number(/: (\d+) outlet/.exec(line)![1]);
  expect(count).toBeGreaterThan(0);
  await page.screenshot({ path: "test-results/ready-plan-dialog.png" });

  await dialog.getByRole("button", { name: "Start with this plan" }).click();
  await expect(page).toHaveURL(/\/distribution\/request\?project=.+&pick=1/);
  await expect(page.getByText(new RegExp(`You chose ${count} outlets?`))).toBeVisible();
  await page.getByRole("button", { name: "Start a distribution request" }).click();
  await expect(page.getByLabel("Selected outlets")).toContainText(`${count} selected`); // the plan's outlets arrive chosen
});

test("a business whose country we cannot place sees the prompt as before", async ({ page, request }) => {
  const { token, projectId } = await readyBusiness(request, { credits: "250" });
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), token);
  await page.goto(`/ai-newsroom/${projectId}`);
  const dialog = page.getByRole("alertdialog", { name: "Take your story to over 2,500 media outlets?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Yes, choose outlets" })).toBeVisible();
  await expect(dialog.getByText("Recommended for you")).toHaveCount(0);
});

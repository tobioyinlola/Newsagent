import { type APIRequestContext, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };
const setPlanner = async (request: APIRequestContext, enabled: boolean) => expect((await request.put(`${API}/v1/admin/planner-settings`, { headers: OPS, data: { enabled } })).ok()).toBeTruthy();

// With the switch off, nobody is offered plans and every screen looks as it did before they existed.
test("with suggested plans switched off, the public page and the request look as they did before", async ({ page, request }) => {
  await setPlanner(request, false);
  try {
    await page.goto("/press-distribution");
    await page.getByRole("link", { name: "Choose distribution outlets" }).click();
    await expect(page.getByRole("heading", { name: "Pick where your story goes." })).toBeVisible();
    await expect(page.getByRole("checkbox").first()).toBeVisible(); // the full list is there
    await expect(page.getByRole("heading", { name: "Get a suggested plan" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "All outlets" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Suggested for you only/ })).toHaveCount(0);
    expect((await request.post(`${API}/v1/public/distribution/plan`, { data: { countries: ["Nigeria"] } })).status()).toBe(404);
  } finally {
    await setPlanner(request, true);
  }
});

test("a signed-in business sees no planner, no recommendation and no email-link plan while it is off", async ({ page, request }) => {
  const email = `switch${Date.now()}@business.example.com`;
  await request.post(`${API}/v1/auth/signup/start`, { data: { accepted_terms: true, email, business_name: "Switch Test", city: "Lagos", country: "Nigeria", industry: "technology", password: "correct horse battery" } });
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  const signup = await (await request.post(`${API}/v1/auth/signup/verify`, { data: { email, code: /\b(\d{6})\b/.exec(mail.text)![1] } })).json();
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), signup.token);
  await setPlanner(request, false);
  try {
    await page.goto("/distribution/request?plan=1"); // the link an email would carry
    await expect(page.getByRole("button", { name: "Start a distribution request" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Get a suggested plan" })).toHaveCount(0);
    await page.getByRole("button", { name: "Start a distribution request" }).click();
    await expect(page.getByRole("heading", { name: "Where would you like to distribute?" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Get a suggested plan" })).toHaveCount(0);
  } finally {
    await setPlanner(request, true);
  }
});

test("the back office switch turns suggested plans on and off for visitors at once", async ({ page, request }) => {
  const visitors = async () => (await (await request.get(`${API}/v1/public/distribution/outlets`)).json()).planner as boolean;
  await setPlanner(request, false);
  try {
    await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
    await page.goto("/admin/distribution");
    await page.getByRole("button", { name: "Suggested plans" }).click();
    const sw = page.getByRole("switch");
    await expect(sw).toHaveAttribute("aria-checked", "false");
    await expect(page.getByText(/Off: nobody is offered plans/)).toBeVisible();
    expect(await visitors()).toBe(false);

    await sw.click();
    await expect(sw).toHaveAttribute("aria-checked", "true");
    await expect(page.getByText(/On: plans are offered/)).toBeVisible();
    await expect(page.getByText(/Changed by ops@example.com/)).toBeVisible();
    expect(await visitors()).toBe(true);
    await page.screenshot({ path: "test-results/planner-switch-on.png" });

    await sw.click();
    await expect(sw).toHaveAttribute("aria-checked", "false");
    expect(await visitors()).toBe(false);
  } finally {
    await setPlanner(request, true);
  }
});

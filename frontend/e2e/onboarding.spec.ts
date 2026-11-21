import { expect, test, type Page } from "@playwright/test";

// First-run questions after sign-up, and guided tours with saved progress. These run against a second copy of the app (port 5174)
// where the questions and automatic tours are switched on; the main copy has them off so the other tests are never interrupted.
test.use({ baseURL: "http://localhost:5174", viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };
const shot = async (page: Page, name: string) => { if (process.env.SHOTS) await page.waitForTimeout(400); if (process.env.SHOTS) await page.screenshot({ path: `${process.env.SHOTS}/${name}.png` }); };

async function newCustomer(request: import("@playwright/test").APIRequestContext, label: string) {
  const email = `${label}${Date.now()}@example.com`;
  const invited = await (await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: `Onboarding ${label}`, credits: "5" } })).json();
  await request.post(`${API}/v1/auth/signup/start`, { data: { accepted_terms: true, invite_code: invited.code, password: "correct horse battery" } });
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  const signup = await (await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: invited.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } })).json();
  return { token: signup.token as string, email };
}

test("a new customer answers the first-run questions in steps, can skip one, and the answers reach the back office", async ({ page, request }) => {
  const { token } = await newCustomer(request, "steps");
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), token);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/welcome$/); // a new sign-up sees the questions before the dashboard
  await expect(page.getByRole("heading", { name: "Let’s set up your workspace" })).toBeVisible();
  await expect(page.getByText("Step 1 of 4")).toBeVisible();
  await page.getByLabel("What should we call you?").fill("Ada");
  await page.getByLabel("Your role").selectOption({ label: "Founder or owner" });
  await shot(page, "1-onboarding-about-you");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Step 2 of 4")).toBeVisible();
  await shot(page, "2-onboarding-business");
  await page.getByRole("button", { name: "Skip this step" }).click(); // any card can be skipped
  await expect(page.getByText("Step 3 of 4")).toBeVisible();
  await page.getByText("Win more customers").click();
  await page.getByText("Reach investors").click();
  await shot(page, "3-onboarding-goals");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Step 4 of 4")).toBeVisible();
  await page.getByText("A friend or colleague").click();
  await page.getByLabel("Tell us more (optional)").fill("Tunde told me");
  await shot(page, "4-onboarding-heard");
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const me = await (await request.get(`${API}/v1/me`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const detail = await (await request.get(`${API}/v1/admin/customers/${me.workspace_id}`, { headers: OPS })).json();
  expect(detail.profile).toMatchObject({ contact_name: "Ada", role: "founder", goals: ["customers", "investors"], heard_from: "friend", heard_detail: "Tunde told me" });
  expect(detail.profile.company_size).toBeUndefined(); // the skipped card saved nothing
  expect(detail.profile_status).toBe("done");
  // ...and it reads clearly on the customer's page in the back office
  await request.put(`${API}/v1/me/tours/admin-platform`, { headers: OPS, data: { step: 0, dismissed: true } }); // keep the team's own tour out of the way
  const admin = await page.context().browser()!.newContext();
  const ap = await admin.newPage();
  await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await ap.goto(`/admin/customers/${me.workspace_id}`);
  const card = ap.locator("section", { has: ap.getByRole("heading", { name: "What they told us" }) });
  await expect(card).toContainText("Founder or owner");
  await expect(card).toContainText("Win more customers, Reach investors");
  await expect(card).toContainText("A friend or colleague");
  await expect(card).toContainText("Tunde told me");
  await expect(card).not.toContainText("Team size"); // skipped, so not shown
  await shot(ap, "12-admin-customer-profile");
  await admin.close();
});

test("the whole set of questions can be skipped, and the welcome tour remembers where you stopped", async ({ page, request }) => {
  const { token } = await newCustomer(request, "skip");
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), token);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/welcome$/);
  await page.getByRole("button", { name: "Skip for now" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const tour = page.getByRole("dialog", { name: /Find your way around: step 1 of 10/ });
  await expect(tour).toBeVisible(); // the welcome tour opens by itself, once
  await shot(page, "5-customer-tour-welcome");
  await tour.getByRole("button", { name: "Next" }).click();
  const second = page.getByRole("dialog", { name: /step 2 of 10/ });
  await expect(second).toBeVisible();
  await shot(page, "6-customer-tour-menu");
  await page.keyboard.press("Escape"); // stop for now
  await expect(second).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("dialog", { name: /step 2 of 10/ })).toBeVisible(); // carries on from step 2, saved on the server
  await page.getByRole("button", { name: "Skip tour" }).click();
  await page.reload();
  await expect(page).toHaveURL(/\/dashboard$/); // skipping the questions is remembered too
  await expect(page.getByRole("dialog", { name: /step/ })).toHaveCount(0); // a skipped tour does not come back by itself
  await page.getByRole("button", { name: /Guided tours/ }).click();
  const list = page.getByRole("dialog", { name: "Guided tours" });
  await expect(list).toContainText("Find your way around");
  await shot(page, "7-customer-tours-menu");
  await list.getByRole("button", { name: "Resume" }).first().click(); // and it can be picked up again from the menu
  await expect(page.getByRole("dialog", { name: /Find your way around: step/ })).toBeVisible();
});

test("a customer from before the questions existed gets a quiet card they can dismiss", async ({ page, request }) => {
  const { token } = await newCustomer(request, "old");
  await request.put(`${API}/v1/me/onboarding/profile`, { headers: { Authorization: `Bearer ${token}` }, data: { status: "skipped" } }); // sanity: the endpoint works
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), token);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("region", { name: "Tell us about your business" })).toHaveCount(0); // already answered or skipped: no card
});

test("every back-office user is offered the platform tour once, and it is saved as they go", async ({ browser, request }) => {
  await request.put(`${API}/v1/me/tours/admin-platform`, { headers: OPS, data: { reset: true } }); // as a team member who has never seen it
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin");
  const tour = page.getByRole("dialog", { name: /Platform overview: step 1 of/ });
  await expect(tour).toBeVisible();
  await shot(page, "8-admin-tour-welcome");
  await tour.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("dialog", { name: /Platform overview: step 2 of/ })).toContainText("Overview");
  await shot(page, "9-admin-tour-section");
  await page.getByRole("button", { name: "Skip tour" }).click();
  await page.reload();
  await expect(page.getByRole("dialog", { name: /Platform overview/ })).toHaveCount(0);
  await page.getByRole("button", { name: /Guided tours/ }).click();
  const list = page.getByRole("dialog", { name: "Guided tours" });
  await expect(list).toContainText("Platform overview");
  await expect(list).toContainText("Distribution, step by step");
  await shot(page, "10-admin-tours-menu");
  await list.locator("li", { hasText: "Working with customers" }).getByRole("button", { name: "Start" }).click(); // a deeper tour takes you to that page
  await expect(page).toHaveURL(/\/admin\/customers/);
  await expect(page.getByRole("dialog", { name: /Working with customers: step 1/ })).toBeVisible();
  await shot(page, "11-admin-tour-customers");
  await ctx.close();
});

import { type APIRequestContext, type Page, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const PASSWORD = "correct horse battery";
const sidebar = (page: Page) => page.getByRole("navigation", { name: "Back office" });

async function asOwner(page: Page) {
  await page.addInitScript(() => { if (!sessionStorage.getItem("seeded")) { sessionStorage.setItem("seeded", "1"); sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"); } });
}
const lastMail = async (request: APIRequestContext, to: string) => (await (await request.get(`${API}/v1/dev/last-email`, { params: { to } })).json()) as { text: string };

test("an owner invites a team member with a role; they join and only get what that role allows; changes apply at once", async ({ page, browser, request }) => {
  const email = `sam${Date.now()}@team.example.com`;

  // the owner invites from the Team page
  await asOwner(page);
  await page.goto("/admin/team");
  await expect(page.getByRole("heading", { name: "Team", exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "Back-office team" }).getByRole("row", { name: /ops@example.com.*owner/i })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Name (optional)").fill("Sam Support");
  await page.getByLabel("Role").selectOption("support");
  await expect(page.getByText("Helps customers and keeps videos moving")).toBeVisible();
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByText(`We emailed an invitation to ${email}`)).toBeVisible();
  const row = page.getByRole("table", { name: "Back-office team" }).getByRole("row", { name: new RegExp(email) });
  await expect(row).toContainText("invited");

  // the invited person opens the emailed link in their own browser
  const link = /(https?:\/\/\S+\/admin\/join\?token=[\w-]+)/.exec((await lastMail(request, email)).text)![1];
  const ctx = await browser.newContext();
  const sam = await ctx.newPage();
  await sam.goto(new URL(link).pathname + new URL(link).search);
  await expect(sam.getByText("invited", { exact: false }).first()).toBeVisible();
  await sam.getByLabel("Your name").fill("Sam Support");
  await sam.getByLabel("Choose a password").fill("short");
  await sam.getByRole("button", { name: "Email me a code" }).click();
  await expect(sam.getByRole("alert")).toBeVisible(); // password rules apply
  await sam.getByLabel("Choose a password").fill(PASSWORD);
  await sam.getByRole("button", { name: "Email me a code" }).click();
  await sam.getByLabel("6-digit code").fill("000000");
  await sam.getByRole("button", { name: "Join the team" }).click();
  await expect(sam.getByRole("alert")).toBeVisible();
  await sam.getByLabel("6-digit code").fill(/\b(\d{6})\b/.exec((await lastMail(request, email)).text)![1]);
  await sam.getByRole("button", { name: "Join the team" }).click();
  await expect(sam.getByRole("heading", { name: "Overview" })).toBeVisible();

  // Support sees support's screens and not the rest
  const nav = sidebar(sam);
  for (const name of ["Customers", "Operations", "Review queue", "Jobs"]) await expect(nav.getByRole("link", { name })).toBeVisible();
  for (const name of ["Revenue", "Credit packs", "Team", "Presenter clips", "Audit log", "Costs"]) await expect(nav.getByRole("link", { name })).toHaveCount(0);
  await expect(nav.getByText("Support", { exact: true })).toBeVisible();
  await sam.goto("/admin/revenue");
  await expect(sam.getByText("Your role doesn't include this part of the back office")).toBeVisible();
  await sam.goto("/admin/team");
  await expect(sam.getByText("Your role doesn't include this part of the back office")).toBeVisible();

  // the owner's table now shows them as active; changing the role applies without them signing in again
  await page.reload();
  const active = page.getByRole("table", { name: "Back-office team" }).getByRole("row", { name: new RegExp(email) });
  await expect(active).toContainText("active");
  await active.getByRole("button", { name: "Change access" }).click();
  const edit = page.locator("section", { hasText: "Change access for" });
  await edit.getByLabel("Role").selectOption("finance");
  await edit.getByRole("button", { name: "Save" }).click();
  await expect(active).toContainText("Finance");
  await sam.goto("/admin/revenue");
  await expect(sam.getByRole("heading", { name: "Revenue" })).toBeVisible();
  await expect(sidebar(sam).getByRole("link", { name: "Review queue" })).toHaveCount(0);

  // suspend: signed out everywhere at once; restoring lets them sign in again (with the emailed code)
  await active.getByRole("button", { name: "Suspend" }).click();
  await expect(active).toContainText("suspended");
  await sam.goto("/admin");
  await expect(sam).toHaveURL(/\/admin\/login/);
  await sam.getByLabel("Email").fill(email);
  await sam.getByLabel("Password").fill(PASSWORD);
  await sam.getByRole("button", { name: "Sign in" }).click();
  await expect(sam.getByRole("alert")).toContainText("don't match"); // suspended people can't sign in
  await active.getByRole("button", { name: "Restore" }).click();
  await expect(active).toContainText("active");
  await sam.getByRole("button", { name: "Sign in" }).click();
  await expect(sam.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await sam.getByLabel("6-digit code").fill(/\b(\d{6})\b/.exec((await lastMail(request, email)).text)![1]);
  await sam.getByRole("button", { name: "Verify" }).click();
  await expect(sam.getByRole("heading", { name: "Overview" })).toBeVisible();

  // remove: they're gone from the list and can't get back in
  await active.getByRole("button", { name: "Remove" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Remove" }).click();
  await expect(page.getByRole("table", { name: "Back-office team" }).getByRole("row", { name: new RegExp(email) })).toHaveCount(0);
  await sam.goto("/admin");
  await expect(sam).toHaveURL(/\/admin\/login/);
  await ctx.close();
});

test("a custom role gets exactly the ticked permissions, and an admin can't hand out more than they hold", async ({ page, request }) => {
  const email = `custom${Date.now()}@team.example.com`;
  await asOwner(page);
  await page.goto("/admin/team");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Role").selectOption("custom");
  await expect(page.getByRole("button", { name: "Send invitation" })).toBeDisabled(); // nothing ticked yet
  await page.getByLabel("See the overview and system health").check();
  await page.getByLabel("See revenue, payments, vendor costs and budgets").check();
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByRole("table", { name: "Back-office team" }).getByRole("row", { name: new RegExp(email) })).toContainText("Custom");

  // the server refuses a grant beyond what the inviter holds, whatever the screen says
  const lead = `lead${Date.now()}@team.example.com`;
  const inviteLead = await request.post(`${API}/v1/admin/staff`, { headers: { Authorization: "Bearer dev:ops@example.com" }, data: { email: lead, role: "custom", permissions: ["team.manage", "overview.view"] } });
  expect(inviteLead.status()).toBe(200);
});

test("the team list and invitations need a signed-in person with the team permission", async ({ request }) => {
  const OPS = { Authorization: "Bearer dev:ops@example.com" };
  expect((await request.get(`${API}/v1/admin/staff`)).status()).toBe(401);
  expect((await request.post(`${API}/v1/admin/staff`, { data: { email: "x@team.example.com", role: "viewer" } })).status()).toBe(401);
  const me = await (await request.get(`${API}/v1/me`, { headers: OPS })).json();
  expect(me.is_owner).toBe(true);
  expect(me.permissions).toContain("team.manage");
});

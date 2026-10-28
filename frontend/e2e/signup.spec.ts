import { expect, test } from "@playwright/test";

// A business signs up on its own: no invitation, a confirmed email, then straight to the dashboard.
test("open sign-up: business name, email, password, emailed code, dashboard", async ({ page, request }) => {
  const email = `owner${Date.now()}@newbiz.example.com`;
  await page.goto("/");
  await page.getByRole("link", { name: "Publish your free story!" }).first().click();
  await expect(page.getByRole("heading", { name: "Publish your story free" })).toBeVisible();
  await page.getByLabel("Business name").fill("NewBiz Ltd");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("correct horse battery");
  await page.getByLabel("Confirm password").fill("correct horse battery");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByLabel("6-digit code")).toBeVisible();

  await page.getByLabel("6-digit code").fill("000000"); // a wrong code is refused
  await page.getByRole("button", { name: "Verify and create workspace" }).click();
  await expect(page.getByRole("alert")).toBeVisible();

  const mail = await (await request.get("http://localhost:8000/v1/dev/last-email", { params: { to: email } })).json();
  await page.getByLabel("6-digit code").fill(/\b(\d{6})\b/.exec(mail.text)![1]);
  await page.getByRole("button", { name: "Verify and create workspace" }).click();
  await expect(page.getByRole("heading", { name: "Welcome, NewBiz Ltd" })).toBeVisible({ timeout: 15_000 });
});

test("the website field in the details step takes anything, or nothing", async ({ page, request }) => {
  const email = `site${Date.now()}@newbiz.example.com`;
  await request.post("http://localhost:8000/v1/auth/signup/start", { data: { email, business_name: "Site Biz", password: "correct horse battery" } });
  const mail = await (await request.get("http://localhost:8000/v1/dev/last-email", { params: { to: email } })).json();
  const s = await (await request.post("http://localhost:8000/v1/auth/signup/verify", { data: { email, code: /\b(\d{6})\b/.exec(mail.text)![1] } })).json();
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), s.token);
  await page.goto("/projects/new");
  const site = page.getByLabel("Website (optional)");
  await site.fill("mybusiness.com");
  await expect(site).toHaveJSProperty("validity.valid", true); // no browser URL check on this optional field
  await site.fill("");
  await expect(site).toHaveJSProperty("validity.valid", true);
});

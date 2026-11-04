import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

// A visitor picks outlets on the public page, signs up, and lands in the distribution request with them already chosen.
test("a visitor picks outlets by topic and place, signs up, and finds them in their distribution request", async ({ page, request }) => {
  await page.goto("/press-distribution");
  await page.getByRole("link", { name: "Choose distribution outlets" }).click();
  await expect(page.getByRole("heading", { name: "Pick where your story goes." })).toBeVisible();

  // topic and place
  await page.getByRole("button", { name: /^Technology/ }).click();
  await page.getByLabel("Region", { exact: true }).selectOption("Africa");
  await page.getByLabel("Country", { exact: true }).selectOption("Nigeria");
  await expect(page.getByRole("checkbox")).toHaveCount(4); // Techpoint Africa, Tech Next, Tech Cabal, Techeconomy
  await page.getByLabel("Country", { exact: true }).selectOption("Ghana");
  await expect(page.getByText("We have no outlets in Ghana yet. They are coming soon.")).toBeVisible();
  await page.getByLabel("Country", { exact: true }).selectOption("Nigeria");
  await page.getByRole("checkbox", { name: /Techpoint Africa/ }).check();
  await page.getByRole("checkbox", { name: /Tech Cabal/ }).check();
  const bar = page.getByRole("region", { name: "Your selection" });
  await expect(bar).toContainText("2 selected");
  await expect(bar).toContainText("180 credits"); // 83 + 97, shown before any sign-up
  await page.screenshot({ path: "test-results/public-picker-desktop.png", fullPage: false });

  // sign up: the choice comes along
  await page.getByRole("button", { name: "Continue: create your free account" }).click();
  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByText(/You chose 2 distribution outlets/)).toBeVisible();
  const email = `picker${Date.now()}@business.example.com`;
  await page.getByLabel("Business name").fill("Picker Business");
  await page.getByLabel("Country", { exact: true }).fill("Nigeri");
  await page.getByRole("option", { name: "Nigeria", exact: true }).click();
  await page.getByLabel("City", { exact: true }).fill("Lago");
  await page.getByRole("option", { name: "Lagos", exact: true }).first().click();
  await page.getByLabel("Industry", { exact: true }).selectOption("technology");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("correct horse battery");
  await page.getByLabel("Confirm password", { exact: true }).fill("correct horse battery");
  await page.getByLabel(/I have read and agree to the Terms of Use/).check();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByLabel("6-digit code")).toBeVisible();
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  await page.getByLabel("6-digit code").fill(/\b(\d{6})\b/.exec(mail.text)![1]);
  await page.getByRole("button", { name: "Verify and create workspace" }).click();

  // straight into the distribution request
  await expect(page).toHaveURL(/\/distribution\/request\?pick=1/, { timeout: 15000 });
  await expect(page.getByText(/You chose 2 outlets/)).toBeVisible();
  await page.screenshot({ path: "test-results/public-picker-request.png" });
  await page.getByRole("button", { name: "Start a distribution request" }).click();
  await expect(page.getByLabel("Selected outlets", { exact: true })).toContainText("2 selected");
  await expect(page.getByRole("checkbox", { name: /Techpoint Africa/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /Tech Cabal/ })).toBeChecked();
  // the choice is used up: going back to the page does not add it again
  expect(await page.evaluate(() => localStorage.getItem("newsagent.distribution.pick"))).toBeNull();

  // the signed-in picker has the same filters
  await page.getByRole("button", { name: /^Gossip Blogs/ }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(1); // 88 Lately is the only gossip blog that costs credits so far
  await page.getByRole("button", { name: "All topics" }).click();
  await page.getByLabel("Region", { exact: true }).selectOption("Africa");
  await expect(page.getByRole("checkbox").first()).toBeVisible();
});

test("the public page works on a phone and a signed-in visitor goes straight to the request", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/press-distribution#choose");
  await expect(page.getByRole("heading", { name: "Pick where your story goes." })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole("button", { name: "Continue: create your free account" })).toBeDisabled();
  await page.getByRole("checkbox", { name: /Techpoint Africa/ }).check();
  await expect(page.getByRole("button", { name: "Continue: create your free account" })).toBeEnabled();
  await page.screenshot({ path: "test-results/public-picker-phone.png" });
});

test("the home page sends visitors straight to the outlet picker", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Choose your outlets" }).click();
  await expect(page).toHaveURL(/\/press-distribution#choose$/);
  await expect(page.getByRole("heading", { name: "Pick where your story goes." })).toBeInViewport();
});

test("an operator can refile an outlet in the back office and the public filters follow", async ({ browser, request, page }) => {
  const OPS = { Authorization: "Bearer dev:ops@example.com" };
  const cfg = await (await request.get(`${API}/v1/admin/distribution/config`, { headers: OPS })).json();
  const tech = cfg.outlets.find((o: { name: string }) => o.name === "Tech Next");
  const admin = await browser.newContext();
  const ap = await admin.newPage();
  await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  try {
    await ap.goto("/admin/distribution");
    await ap.getByRole("button", { name: "Notification and outlet settings" }).click();
    await ap.getByLabel("Configure outlet").selectOption(tech.id);
    await expect(ap.getByLabel(/^Topic/)).toHaveValue("Technology");
    await ap.getByLabel(/^Topic/).selectOption("General News");
    await ap.getByLabel(/^Country/).selectOption("Kenya");
    await ap.getByRole("button", { name: "Save outlet settings" }).click();
    await expect.poll(async () => (await (await request.get(`${API}/v1/public/distribution/outlets`)).json()).outlets.find((o: { name: string }) => o.name === "Tech Next").country).toBe("Kenya");
    await page.goto("/press-distribution#choose");
    await page.getByLabel("Country", { exact: true }).selectOption("Kenya");
    await expect(page.getByRole("checkbox", { name: /Tech Next/ })).toBeVisible();
  } finally {
    await request.put(`${API}/v1/admin/distribution/outlets/${tech.id}`, { headers: OPS, data: { ...tech, topic: "Technology", country: "Nigeria" } });
    await admin.close();
  }
});

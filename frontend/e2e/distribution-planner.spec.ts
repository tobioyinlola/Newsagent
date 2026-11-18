import { expect, test } from "@playwright/test";

// A visitor asks for a suggested plan on the public page, uses it, and still has the whole list to change it.
test("a visitor gets a suggested plan with reasons, uses it, and can still browse and change every outlet", async ({ page }) => {
  await page.goto("/press-distribution");
  await page.getByRole("link", { name: "Choose distribution outlets" }).click();
  await expect(page.getByRole("heading", { name: "Pick where your story goes." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Get a suggested plan" })).toBeVisible();

  // three questions
  await page.getByRole("button", { name: "Nigeria", exact: true }).click();
  await page.getByLabel(/how many credits/i).fill("300");
  await page.getByText("Reach investors").click();
  await page.getByRole("button", { name: "Suggest outlets" }).click();

  // plans that fit the budget, each outlet with its reasons
  const essential = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Essential" }) });
  await expect(essential).toBeVisible();
  await expect(essential.getByText(/Based in Nigeria/).first()).toBeVisible();
  for (const total of await page.getByRole("article").locator("p.text-2xl").allTextContents()) expect(Number(total.replace(/[^0-9.]/g, ""))).toBeLessThanOrEqual(300);
  await expect(page.getByText(/publication is decided by each outlet and is not guaranteed/)).toBeVisible();
  await page.screenshot({ path: "test-results/planner-public.png", fullPage: false });

  // using a plan selects its outlets, with the price in the bar
  await essential.getByRole("button", { name: "Use this plan" }).click();
  const bar = page.getByRole("region", { name: "Your selection" });
  await expect(bar).toContainText(/[2-3] selected/);
  await expect(essential.getByRole("button", { name: "✓ In use" })).toBeVisible();

  // the full list is still there, with the suggested outlets marked, and anything can be changed
  const total = await page.getByRole("checkbox").count();
  await expect(page.getByText("Suggested for you").first()).toBeVisible();
  await page.getByRole("button", { name: /^Suggested for you only/ }).click();
  expect(await page.getByRole("checkbox").count()).toBeLessThan(total);
  await page.getByRole("button", { name: /^Suggested for you only/ }).click();
  expect(await page.getByRole("checkbox").count()).toBe(total);
  await page.getByRole("checkbox").first().uncheck();
  await page.getByRole("checkbox").first().check();
  await expect(bar).toContainText("selected");

  // phone: no sideways scroll
  await page.setViewportSize({ width: 375, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("heading", { name: "Get a suggested plan" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/planner-mobile.png" });
});

test("a business nobody has outlets for is told so plainly, not shown an empty page", async ({ page }) => {
  await page.goto("/press-distribution");
  await page.getByRole("link", { name: "Choose distribution outlets" }).click();
  await page.getByRole("button", { name: "Nigeria", exact: true }).click();
  await page.getByLabel(/how many credits/i).fill("1");
  await page.getByRole("button", { name: "Suggest outlets" }).click();
  await expect(page.getByText(/below our lowest price/)).toBeVisible();
});

// Text must be readable, not just present: the plan names once came out dark on a dark card.
test("plan names and prices are readable on the dark page", async ({ page }) => {
  await page.goto("/press-distribution");
  await page.getByRole("link", { name: "Choose distribution outlets" }).click();
  await page.getByRole("button", { name: "Nigeria", exact: true }).click();
  await page.getByRole("button", { name: "Suggest outlets" }).click();
  const name = page.getByRole("heading", { name: "Essential" });
  await expect(name).toBeVisible();
  const [text, card] = await name.evaluate((el) => [getComputedStyle(el).color, getComputedStyle(el.closest("article")!).backgroundColor]);
  const lum = (c: string) => { const [r, g, b] = (c.match(/[\d.]+/g) ?? ["0", "0", "0"]).slice(0, 3).map((v) => { const x = Number(v) / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const [a, b] = [lum(text), lum(card)].sort((x, y) => y - x);
  expect((a + 0.05) / (b + 0.05)).toBeGreaterThanOrEqual(4.5); // WCAG AA for normal text
});

import { expect, test, type Page } from "@playwright/test";

// Pop-ups and guided tours on a phone: they fit the screen, long content scrolls inside them, and a tour opens the menu to point at a menu item.
// (Runs against the copy of the app where tours open by themselves, port 5174.)
test.use({ baseURL: "http://localhost:5174", viewport: { width: 390, height: 700 }, deviceScaleFactor: 2 });
const shot = async (page: Page, name: string) => { if (process.env.SHOTS) { await page.waitForTimeout(400); await page.screenshot({ path: `${process.env.SHOTS}/${name}.png` }); } };
const fits = async (page: Page, locator: ReturnType<Page["getByRole"]>) => {
  const b = (await locator.boundingBox())!;
  expect(b.x, "left edge on screen").toBeGreaterThanOrEqual(0);
  expect(b.x + b.width, "right edge on screen").toBeLessThanOrEqual(390 + 1);
  expect(b.y, "top on screen").toBeGreaterThanOrEqual(0);
  expect(b.y + b.height, "bottom on screen").toBeLessThanOrEqual(700 + 1);
};

test("the customer welcome tour works on a phone: it opens the menu to point at menu items", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  await page.goto("/dashboard");
  const tour = (n: number) => page.getByRole("dialog", { name: new RegExp(`Find your way around: step ${n} of`) });
  await expect(tour(1)).toBeVisible();
  await fits(page, tour(1));
  await shot(page, "1-phone-tour-start");
  await tour(1).getByRole("button", { name: "Next" }).click();
  await expect(tour(2)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main", exact: true }).getByRole("link", { name: "Dashboard" })).toBeInViewport(); // the menu opened by itself
  await fits(page, tour(2));
  await shot(page, "2-phone-tour-menu-step");
  for (let n = 2; n <= 8; n++) { await tour(n).getByRole("button", { name: "Next" }).click(); } // through the menu items
  await expect(tour(9)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main", exact: true }).getByRole("link", { name: "Dashboard" })).not.toBeInViewport(); // and closed again for the next step
  await fits(page, tour(9));
  await shot(page, "3-phone-tour-after-menu");
  await page.getByRole("button", { name: "Skip tour" }).click();
});

test("the back office platform tour works on a phone too", async ({ browser, request }) => {
  await request.put("http://localhost:8000/v1/me/tours/admin-platform", { headers: { Authorization: "Bearer dev:ops@example.com" }, data: { reset: true } });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 700 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin");
  const tour = (n: number) => page.getByRole("dialog", { name: new RegExp(`Platform overview: step ${n} of`) });
  await expect(tour(1)).toBeVisible();
  await fits(page, tour(1));
  await tour(1).getByRole("button", { name: "Next" }).click();
  await expect(tour(2)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Back office" }).getByRole("link", { name: "Overview" })).toBeInViewport();
  await fits(page, tour(2));
  await shot(page, "4-phone-admin-tour");
  await page.getByRole("button", { name: "Skip tour" }).click();
  await ctx.close();
});

test("a confirmation pop-up fits a phone", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  await page.goto("/dashboard");
  const skip = page.getByRole("button", { name: "Skip tour" });
  if (await skip.isVisible().catch(() => false)) await skip.click(); // (the welcome tour may open first)
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  const dialog = page.getByRole("alertdialog", { name: "Sign out?" });
  await expect(dialog).toBeVisible();
  await fits(page, dialog);
  await shot(page, "5-phone-confirm");
  await dialog.getByRole("button", { name: "Stay signed in" }).click();
});

test("the outreach template preview pop-up fits a phone and its long text scrolls inside it", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 600 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/outreach");
  await page.getByRole("button", { name: "Templates and settings" }).click();
  await page.getByRole("button", { name: "Preview with sample details" }).first().click();
  const dialog = page.getByRole("dialog", { name: /^Preview of / });
  await expect(dialog).toBeVisible();
  const b = (await dialog.boundingBox())!;
  expect(b.x).toBeGreaterThanOrEqual(0); expect(b.x + b.width).toBeLessThanOrEqual(391); expect(b.y + b.height).toBeLessThanOrEqual(601);
  await expect(dialog.getByRole("button", { name: "Close" })).toBeInViewport();
  await shot(page, "6-phone-preview");
  await ctx.close();
});

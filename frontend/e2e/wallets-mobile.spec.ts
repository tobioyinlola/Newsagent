import { expect, test } from "@playwright/test";

// On a phone the wallet list and a customer's wallet history are stacked cards, not a wide table; the pages never scroll sideways.
test("wallets and wallet history fit a phone", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
  await page.goto("/admin/wallets");
  await expect(page.getByRole("heading", { name: "Wallets", exact: true })).toBeVisible();
  const cards = page.getByRole("list", { name: "Customer wallets" });
  await expect(cards).toBeVisible();
  await expect(cards.getByText("Credits left").first()).toBeVisible();
  await expect(page.getByRole("table", { name: "Customer wallets" })).toBeHidden();
  expect(await fits()).toBe(true);
  await cards.getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "Wallet history" })).toBeVisible();
  expect(await fits()).toBe(true);
  await page.goto("/admin/team");
  await expect(page.getByRole("table", { name: "Back-office team" })).toBeVisible();
  expect(await fits()).toBe(true); // the team table scrolls inside its card now
  await ctx.close();
});

test("on a laptop the same pages show tables", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/admin/wallets");
  await expect(page.getByRole("table", { name: "Customer wallets" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Customer wallets" })).toBeHidden();
});

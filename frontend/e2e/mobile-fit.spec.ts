import { expect, test } from "@playwright/test";

// On a small phone no page scrolls sideways, and the back-office customer list is stacked cards rather than a cramped table.
test("public, customer and back-office pages fit a 360px phone", async ({ browser }) => {
  test.setTimeout(180_000);
  const ctx = await browser.newContext({ viewport: { width: 360, height: 780 } });
  const page = await ctx.newPage();
  const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
  for (const path of ["/", "/press-distribution", "/ai-newsroom", "/latest-stories", "/terms", "/login", "/signup"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect(await fits(), path).toBe(true);
  }
  await expect(page.getByRole("link", { name: "Privacy Policy" }).last()).toBeVisible();
  await page.goto("/");
  const footerLink = page.getByRole("contentinfo").getByRole("link", { name: "Press Distribution" });
  expect((await footerLink.boundingBox())!.height).toBeGreaterThanOrEqual(44); // easy to tap
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  for (const path of ["/dashboard", "/distribution/request", "/settings/billing", "/analytics"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect(await fits(), path).toBe(true);
  }
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/customers");
  const cards = page.getByRole("list", { name: "Customers" });
  await expect(cards).toBeVisible();
  await expect(cards.getByText("Credits").first()).toBeVisible();
  expect(await fits()).toBe(true);
  await ctx.close();
});

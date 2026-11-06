import { expect, test } from "@playwright/test";

// The sidebar has "Buy credits" just above "Settings"; it opens the billing tab, and only it is highlighted there.
test("Buy credits sits above Settings in the sidebar and opens the billing tab", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/dashboard");
  const nav = page.getByRole("navigation", { name: "Main", exact: true });
  const buy = nav.getByRole("link", { name: "Buy credits", exact: true });
  const settings = nav.getByRole("link", { name: "Settings", exact: true });
  await expect(buy).toBeVisible();
  expect((await buy.boundingBox())!.y).toBeLessThan((await settings.boundingBox())!.y);
  await buy.click();
  await expect(page).toHaveURL(/\/settings\/billing/);
  await expect(page.getByRole("heading", { name: "Credits and billing" })).toBeVisible();
  await expect(buy).toHaveClass(/bg-brand-green/);
  await expect(settings).not.toHaveClass(/bg-brand-green/); // only the link you are on is lit
  await settings.click();
  await expect(page).toHaveURL(/\/settings\/profile/);
  await expect(settings).toHaveClass(/bg-brand-green/);
});

import { expect, test } from "@playwright/test";

// Run with E2E_SHOW_OUTREACH=false: the unfinished Outreach page is not in the menu and its address goes nowhere.
test.skip(process.env.E2E_SHOW_OUTREACH !== "false", "only meaningful when the page is switched off");

test("the Outreach page is hidden from the back office while it is unfinished", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/distribution");
  await expect(page.getByRole("link", { name: "Distribution" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Outreach" })).toHaveCount(0);
  await page.goto("/admin/outreach");
  await expect(page.getByRole("heading", { name: "Outreach to outlets" })).toHaveCount(0);
});

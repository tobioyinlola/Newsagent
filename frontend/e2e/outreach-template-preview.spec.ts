import { expect, test } from "@playwright/test";

// The sample preview of an outreach email template shows right under its button.
test.use({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
test("previewing an outreach template with sample details", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/outreach");
  await page.getByRole("button", { name: "Templates and settings" }).click();
  const first = page.getByRole("button", { name: "Preview with sample details" }).first();
  await first.click();
  const preview = page.getByRole("region", { name: /^Preview of / }).first();
  await expect(preview).toBeVisible();
  await expect(preview).toContainText("nothing is sent");
  await expect(preview).not.toContainText("{"); // every placeholder was filled in
  await preview.screenshot({ path: "/tmp/claude-0/-home-user-Newsagent/a52b5115-9221-5348-85e2-72cf334b0385/scratchpad/template-preview.png" });
  await preview.getByRole("button", { name: "Close preview" }).click();
  await expect(preview).toHaveCount(0);
});

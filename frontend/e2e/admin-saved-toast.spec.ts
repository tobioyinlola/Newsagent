import { expect, test } from "@playwright/test";

// Anything saved in the back office pops up a short "Saved" message, from any page.
test("saving in the back office pops up a Saved message", async ({ browser, request }) => {
  const OPS = { Authorization: "Bearer dev:ops@example.com" };
  const API = process.env.E2E_API ?? "http://localhost:8000";
  const original = await (await request.get(`${API}/v1/admin/distribution/config`, { headers: OPS })).json();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  try {
    await page.goto("/admin/distribution");
    await page.getByRole("button", { name: "Notification and outlet settings" }).click();
    await page.getByLabel("Team sale notification emails").fill("toast-check@example.com");
    await expect(page.getByText("✓ Saved")).toHaveCount(0);
    await page.getByRole("button", { name: "Save team recipients" }).click();
    await expect(page.getByText("✓ Saved")).toBeVisible();
    await expect(page.getByText("✓ Saved")).toBeHidden({ timeout: 8_000 }); // it goes away by itself
  } finally {
    await request.put(`${API}/v1/admin/distribution/config`, { headers: OPS, data: { team_emails: original.team_emails } });
    await ctx.close();
  }
});

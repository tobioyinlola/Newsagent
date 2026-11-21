import { expect, test, type Page } from "@playwright/test";

// Long lists come a page at a time, the same way everywhere: "Showing 11 to 12 of 12", Previous / Next, and a choice of rows per page.
const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };
const shot = async (page: Page, name: string) => {
  if (!process.env.SHOTS) return;
  await page.getByRole("navigation", { name: "Pagination" }).first().scrollIntoViewIfNeeded(); // show the pager itself, not just the top of the page
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${process.env.SHOTS}/${name}.png` });
};

test("a customer's videos come a page at a time", async ({ page }) => {
  // The server's side of this (page, offset, total header) is covered by its own tests; here the screen is checked with 12 stubbed videos
  // (making 12 real ones would use up the hourly limit on creating videos that other tests share).
  const videos = Array.from({ length: 12 }, (_, i) => ({ id: `video${String(i).padStart(2, "0")}`, state: "draft", created_at: `2026-10-${String(30 - i).padStart(2, "0")}T10:00:00Z`, founder_name: "" }));
  await page.route(/\/v1\/projects(\?.*)?$/, (route) => {
    const q = new URL(route.request().url()).searchParams; const limit = Number(q.get("limit") ?? 100); const offset = Number(q.get("offset") ?? 0);
    return route.fulfill({ json: videos.slice(offset, offset + limit), headers: { "X-Total-Count": String(videos.length), "Access-Control-Expose-Headers": "X-Total-Count" } });
  });
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  await page.goto("/ai-newsroom/videos");
  await expect(page.getByText("Showing 1 to 12 of 12 videos")).toBeVisible();
  await page.getByLabel("Rows per page").selectOption("10");
  await expect(page.getByText("Showing 1 to 10 of 12 videos")).toBeVisible();
  await expect(page.getByRole("link", { name: /Draft/ })).toHaveCount(10);
  await shot(page, "13-pager-customer-videos");
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.getByText("Showing 11 to 12 of 12 videos")).toBeVisible();
  await expect(page.getByRole("link", { name: /Draft/ })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Next page" })).toBeDisabled();
  await page.getByRole("button", { name: "Page 1" }).click();
  await expect(page.getByText("Showing 1 to 10 of 12 videos")).toBeVisible();
});

test("the back office audit log comes a page at a time", async ({ browser, request }) => {
  for (let i = 0; i < 12; i++) await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: `audit${i}${Date.now()}@example.com`, workspace_name: `Audit ${i}`, credits: "1" } }); // each one is written to the audit log
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/audit");
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
  await page.getByLabel("Rows per page").selectOption("10");
  await expect(page.getByText(/^Showing 1 to 10 of \d+ entries$/)).toBeVisible();
  const first = await page.locator("tbody tr").first().innerText();
  await shot(page, "14-pager-admin-audit");
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.getByText(/^Showing 11 to \d+ of \d+ entries$/)).toBeVisible();
  await expect(page.locator("tbody tr").first()).not.toHaveText(first); // a different set of rows (they arrive a moment after the page number changes)
  await ctx.close();
});

import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

// The operator sees how the suggested plans are doing: counts only, in plain words.
test("the suggested-plans numbers show in the admin area and add up with what visitors did", async ({ page, request }) => {
  // a visitor asks for a plan and uses one (the same calls the website makes)
  await request.post(`${API}/v1/public/distribution/plan`, { data: { countries: ["Nigeria"], budget: "300" } });
  await request.post(`${API}/v1/public/distribution/plan/event`, { data: { kind: "used", source: "public", plan_key: "balanced", outlets: 4, credits: "80" } });

  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/distribution");
  await page.getByRole("button", { name: "Suggested plans" }).click();
  await expect(page.getByRole("heading", { name: "Suggested plans", exact: true })).toBeVisible();
  await expect(page.getByText("Plans viewed", { exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "Suggested plans by screen" })).toBeVisible();
  await expect(page.getByRole("row", { name: /Website distribution page/ })).toBeVisible();
  await page.screenshot({ path: "test-results/admin-planner-stats.png", fullPage: true });
  await page.getByLabel("Period").selectOption("7");
  await expect(page.getByText("Plans chosen", { exact: true })).toBeVisible();
});

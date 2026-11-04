import { expect, test } from "@playwright/test";

test("the home page does not show the numbers strip for now", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/v1/public/stats")) asked.push(r.url()); });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Cover Founder in numbers" })).toHaveCount(0);
  await expect(page.getByText("Videos created")).toHaveCount(0);
  await expect(page.getByText("Continents coverage")).toHaveCount(0);
  await expect(page.getByText("Geography", { exact: true })).toHaveCount(0);
  expect(asked).toEqual([]); // and its numbers are not even fetched
  await expect(page.getByRole("heading", { name: "Business Interviews" })).toBeVisible(); // the rest of the page is unchanged
});

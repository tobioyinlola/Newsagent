import { expect, test } from "@playwright/test";

const card = (n: number, kind: string) => ({ slug: `${kind}-${n}`, title: `${kind} story ${n}`, summary: "s", company: "Acme", industry: "Technology", published_at: "2026-11-03T10:00:00Z", duration_s: 60, thumbnail_url: null, category: kind === "cf" ? "CF News" : null, has_video: true });

test("the home page shows 8 stories in each row, and the rest are under See more", async ({ page }) => {
  const asked: number[] = [];
  await page.route("**/v1/public/stories?*", (route) => { const limit = Number(new URL(route.request().url()).searchParams.get("limit")); asked.push(limit); return route.fulfill({ json: Array.from({ length: 30 }, (_, i) => card(i + 1, "biz")).slice(0, limit) }); });
  await page.route("**/v1/public/cf-news*", (route) => route.fulfill({ json: Array.from({ length: 20 }, (_, i) => card(i + 1, "cf")) }));
  await page.goto("/");
  const business = page.getByRole("region", { name: "Latest stories" });
  const news = page.getByRole("region", { name: "CF News" });
  await expect(business.getByRole("link")).toHaveCount(8);
  await expect(news.getByRole("link")).toHaveCount(8);
  expect(asked).toContain(8); // only 8 are asked for, not more
  await page.getByRole("link", { name: "See more stories" }).click();
  await expect(page).toHaveURL(/\/latest-stories$/);
  await page.goBack();
  await page.getByRole("link", { name: "See more CF News" }).click();
  await expect(page).toHaveURL(/\/cf-news$/);
});

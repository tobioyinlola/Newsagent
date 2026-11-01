import { expect, test } from "@playwright/test";

// 45 published News Desk stories, newest first, served the way /v1/public/cf-news pages them (limit + offset).
const stories = Array.from({ length: 45 }, (_, i) => ({
  slug: `cf-story-${i + 1}`,
  title: `CF News story ${i + 1}`,
  summary: "A short summary.",
  company: "Cover Founder News",
  industry: "Technology",
  category: "cf-news",
  published_at: new Date(Date.UTC(2026, 9, 31) - i * 3_600_000).toISOString(),
  duration_s: 42,
  has_video: true,
  thumbnail_url: "/newsroom-hero.webp",
}));

test("CF News is a grid of 20 stories that loads older ones with See more", async ({ page }) => {
  const asked: { limit: number; offset: number }[] = [];
  await page.route("**/v1/public/cf-news*", async (route) => {
    const u = new URL(route.request().url());
    const limit = Number(u.searchParams.get("limit")), offset = Number(u.searchParams.get("offset") ?? 0);
    asked.push({ limit, offset });
    await route.fulfill({ json: stories.slice(offset, offset + limit) });
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/cf-news");

  const grid = page.getByRole("region", { name: "CF News stories" });
  const tiles = grid.getByRole("link");
  await expect(tiles).toHaveCount(20);
  await expect(tiles.first()).toContainText("CF News story 1");
  // no sub-header and no sideways carousel: just the stories
  await expect(page.getByRole("heading", { level: 2, name: "CF News" })).toHaveCount(0);
  await expect(page.locator('[aria-roledescription="carousel"]')).toHaveCount(0);
  // four across on a desktop, so nothing is hidden off to the right
  const tops = await Promise.all([0, 1, 2, 3, 4].map(async (i) => (await tiles.nth(i).boundingBox())!.y));
  expect(new Set(tops.slice(0, 4)).size).toBe(1);
  expect(tops[4]).toBeGreaterThan(tops[0]);
  await page.screenshot({ path: "test-results/cf-news-grid-desktop.png", fullPage: true });

  await page.getByRole("button", { name: "See more" }).click();
  await expect(tiles).toHaveCount(40);
  await expect(tiles.nth(20)).toContainText("CF News story 21");
  await page.getByRole("button", { name: "See more" }).click();
  await expect(tiles).toHaveCount(45);
  await expect(page.getByRole("button", { name: "See more" })).toHaveCount(0);
  expect(asked).toEqual([{ limit: 21, offset: 0 }, { limit: 21, offset: 20 }, { limit: 21, offset: 40 }]);

  // a phone: one column, no sideways scrolling
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/cf-news-grid-phone.png" });
});

test("CF News shows no See more when every story fits on the first page", async ({ page }) => {
  await page.route("**/v1/public/cf-news*", (route) => route.fulfill({ json: stories.slice(0, 7) }));
  await page.goto("/cf-news");
  await expect(page.getByRole("region", { name: "CF News stories" }).getByRole("link")).toHaveCount(7);
  await expect(page.getByRole("button", { name: "See more" })).toHaveCount(0);
});

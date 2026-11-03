import { expect, test } from "@playwright/test";

// 30 published business stories, newest first, served the way /v1/public/stories pages them (limit + offset).
const stories = Array.from({ length: 30 }, (_, i) => ({
  slug: `business-story-${i + 1}`,
  title: `Business story ${i + 1}`,
  summary: "A short summary.",
  company: `Company ${i + 1}`,
  industry: "Technology", // every story shares an industry: it must NOT turn into a category row
  category: "business",
  published_at: new Date(Date.UTC(2026, 9, 31) - i * 3_600_000).toISOString(),
  duration_s: 200,
  has_video: true,
  thumbnail_url: "/newsroom-hero.webp",
}));

async function serve(page: import("@playwright/test").Page, all = stories) {
  const asked: { limit: number; offset: number }[] = [];
  await page.route("**/v1/public/stories?*", async (route) => {
    const u = new URL(route.request().url());
    const limit = Number(u.searchParams.get("limit")), offset = Number(u.searchParams.get("offset") ?? 0);
    asked.push({ limit, offset });
    await route.fulfill({ json: all.slice(offset, offset + limit) });
  });
  await page.route("**/v1/public/cf-news*", (route) => route.fulfill({ json: [] }));
  return asked;
}

test("Featured stories shows the 12 latest as a grid, with no categories, and loads older ones with See more", async ({ page }) => {
  const asked = await serve(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/latest-stories");

  const grid = page.getByRole("region", { name: "Latest stories" });
  const tiles = grid.getByRole("link");
  await expect(tiles).toHaveCount(12);
  await expect(tiles.first()).toContainText("Business story 1");
  await expect(tiles.nth(11)).toContainText("Business story 12");
  // no categories yet: no "Top stories" row and no row per industry
  await expect(page.getByRole("heading", { level: 2, name: "Top stories" })).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 2, name: "Technology" })).toHaveCount(0);
  // four across on a desktop, so nothing is hidden off to the right
  const tops = await Promise.all([0, 1, 2, 3, 4].map(async (i) => (await tiles.nth(i).boundingBox())!.y));
  expect(new Set(tops.slice(0, 4)).size).toBe(1);
  expect(tops[4]).toBeGreaterThan(tops[0]);
  await page.screenshot({ path: "test-results/latest-stories-grid-desktop.png", fullPage: true });

  await page.getByRole("button", { name: "See more" }).click();
  await expect(tiles).toHaveCount(24);
  await expect(tiles.nth(12)).toContainText("Business story 13");
  await page.getByRole("button", { name: "See more" }).click();
  await expect(tiles).toHaveCount(30);
  await expect(page.getByRole("button", { name: "See more" })).toHaveCount(0); // nothing older is left
  expect(asked).toEqual([{ limit: 13, offset: 0 }, { limit: 13, offset: 12 }, { limit: 13, offset: 24 }]);

  // a phone: no sideways scrolling
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("Featured stories shows no See more when every story fits on the first page", async ({ page }) => {
  await serve(page, stories.slice(0, 7));
  await page.goto("/latest-stories");
  await expect(page.getByRole("region", { name: "Latest stories" }).getByRole("link")).toHaveCount(7);
  await expect(page.getByRole("button", { name: "See more" })).toHaveCount(0);
});

test("Featured stories with no stories yet still invites the first one", async ({ page }) => {
  await serve(page, []);
  await page.goto("/latest-stories");
  await expect(page.getByRole("heading", { name: "The first story could be yours." })).toBeVisible();
});

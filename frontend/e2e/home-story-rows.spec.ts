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
  // a desktop or landscape screen: four across, two rows, so everything is on show and nothing scrolls sideways
  await page.setViewportSize({ width: 1280, height: 900 });
  for (const region of [business, news]) {
    const tiles = region.getByRole("link");
    const boxes = await Promise.all([0, 1, 2, 3, 4, 5, 6, 7].map(async (i) => (await tiles.nth(i).boundingBox())!));
    expect(new Set(boxes.slice(0, 4).map((b) => Math.round(b.y))).size).toBe(1); // the first four share a row
    expect(new Set(boxes.slice(4).map((b) => Math.round(b.y))).size).toBe(1); // the other four are the second row
    expect(boxes[4].y).toBeGreaterThan(boxes[0].y + boxes[0].height - 1);
    expect(boxes[3].x + boxes[3].width).toBeLessThanOrEqual(1280); // nothing off to the right
    await expect(region.getByRole("button")).toHaveCount(0); // no scroll arrows on a large screen
  }
  // a phone keeps the swipeable row
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(business.getByRole("button", { name: /Scroll .* right/ })).toBeVisible();
  const first = (await business.getByRole("link").nth(0).boundingBox())!;
  const fifth = (await business.getByRole("link").nth(4).boundingBox())!;
  expect(fifth.y).toBe(first.y); // one line, scrolled sideways
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("link", { name: "See more stories" }).click();
  await expect(page).toHaveURL(/\/latest-stories$/);
  await page.goBack();
  await page.getByRole("link", { name: "See more CF News" }).click();
  await expect(page).toHaveURL(/\/cf-news$/);
});

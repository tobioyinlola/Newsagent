import { expect, type Page, test } from "@playwright/test";

// Pictures inside a story are shown whole, in their own shape: a portrait headshot must never be cut down to a wide strip.
const svg = (w: number, h: number, fill: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect width="${w}" height="${h}" fill="${fill}"/><circle cx="${w / 2}" cy="${h / 3}" r="${Math.min(w, h) / 5}" fill="#fff"/></svg>`;
const PICTURES: Record<string, [number, number, string]> = {
  "portrait.svg": [800, 1200, "#a0522d"], // a headshot, taller than wide
  "wide.svg": [1600, 900, "#2f4f4f"], // a landscape photo
  "small.svg": [300, 200, "#556b2f"], // a small picture: never blown up past its real size
};
const paragraphs = Array.from({ length: 6 }, (_, i) => `Paragraph ${i + 1} of the story, long enough to read like a real paragraph of a press release about the company and its news.`);

async function mockStory(page: Page, category: string | null) {
  await page.route("**/pictures/*.svg", (route) => {
    const [w, h, fill] = PICTURES[new URL(route.request().url()).pathname.split("/").pop()!];
    return route.fulfill({ contentType: "image/svg+xml", body: svg(w, h, fill) });
  });
  await page.route("**/v1/public/stories?*", (route) => route.fulfill({ json: [] }));
  await page.route("**/v1/public/stories/nohena-pilot", (route) => route.fulfill({ json: {
    slug: "nohena-pilot", title: "Nohena completes a successful pilot", summary: "A short summary.", company: "Nohena", industry: "Technology",
    category, dateline: "LAGOS, Nigeria", about: "About Nohena.", disclosure: "", published_at: "2026-11-01T10:00:00Z", duration_s: null,
    has_video: false, video_url: null, thumbnail_url: "/pictures/portrait.svg", source_name: category ? "Example" : null, source_url: category ? "https://example.com" : null,
    sections: [{ heading: "", paragraphs }],
    pictures: Object.keys(PICTURES).map((name) => ({ url: `/pictures/${name}`, caption: `Caption for ${name}` })),
  } }));
  await page.route("**/v1/public/audience*", (route) => route.fulfill({ status: 204 }));
}

/** Every picture in the article shows its whole image: the box has the picture's own shape and fits the column. */
async function expectWholePictures(page: Page, article: ReturnType<Page["locator"]>) {
  const imgs = article.locator("figure img");
  await expect(imgs.first()).toBeVisible();
  const n = await imgs.count();
  expect(n).toBeGreaterThan(0);
  const column = (await article.boundingBox())!;
  for (let i = 0; i < n; i++) {
    await imgs.nth(i).scrollIntoViewIfNeeded();
    await expect.poll(() => imgs.nth(i).evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    const m = await imgs.nth(i).evaluate((el: HTMLImageElement) => ({ nw: el.naturalWidth, nh: el.naturalHeight, w: el.clientWidth, h: el.clientHeight, fit: getComputedStyle(el).objectFit }));
    expect(Math.abs(m.w / m.h - m.nw / m.nh), `picture ${i} keeps its shape`).toBeLessThan(0.02);
    expect(m.w, `picture ${i} is never enlarged`).toBeLessThanOrEqual(m.nw + 1);
    expect(m.w, `picture ${i} fits the column`).toBeLessThanOrEqual(column.width + 1);
    expect(m.fit).not.toBe("cover");
  }
}

test("pictures in a business story are shown whole, centred and in their own shape", async ({ page }) => {
  await mockStory(page, null);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/latest-stories/nohena-pilot");
  const article = page.locator("article").filter({ hasText: "Paragraph 1 of the story" }).first();
  await expect(article).toBeVisible();
  await expectWholePictures(page, article);
  // the portrait headshot is centred in the column, not stretched across it
  const portrait = page.getByRole("img", { name: "Caption for portrait.svg" }).last();
  const [p, a] = [(await portrait.boundingBox())!, (await article.boundingBox())!];
  expect(Math.abs(p.x + p.width / 2 - (a.x + a.width / 2))).toBeLessThan(4);
  await portrait.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/story-pictures-desktop.png" });

  await page.setViewportSize({ width: 390, height: 844 });
  await expectWholePictures(page, article);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await portrait.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/story-pictures-phone.png" });
});

test("pictures in a CF News story are shown whole as well", async ({ page }) => {
  await mockStory(page, "cf-news");
  await page.goto("/latest-stories/nohena-pilot");
  const article = page.getByRole("article", { name: "Technology news report" });
  await expect(article).toBeVisible();
  await expectWholePictures(page, article);
});

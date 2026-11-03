import { expect, test } from "@playwright/test";

const words = (n: number) => Array.from({ length: n }, (_, i) => `word${i + 1}`).join(" ");
const count = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);

test("'Tell us the key details' shows a live word count and never takes more than 250 words", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  await page.goto("/ai-newsroom/new");
  const box = page.getByLabel("Tell us the key details");
  await expect(page.getByText("0 / 250 words")).toBeVisible();
  await expect(page.getByText(/the most we take is 250 words/)).toBeVisible();

  // typing updates the count as you go
  await box.pressSequentially("Acme helps farmers sell produce", { delay: 5 });
  await expect(page.getByText("5 / 250 words")).toBeVisible();

  // a pasted wall of text is cut to 250 words, and the count says so
  await box.fill(words(300));
  expect(count(await box.inputValue())).toBe(250);
  await expect(page.getByText("250 / 250 words (limit reached)")).toBeVisible();
  expect((await box.inputValue()).endsWith("word250")).toBe(true);

  // typing more at the limit adds nothing, and the box still works for editing
  await box.pressSequentially(" extra words here", { delay: 5 });
  expect(count(await box.inputValue())).toBe(250);
  await expect(page.getByText("250 / 250 words (limit reached)")).toBeVisible();
  await box.fill(words(249));
  await expect(page.getByText("249 / 250 words")).toBeVisible();

  // line breaks and extra spaces are not words
  await box.fill("one two\n\n\nthree   four");
  await expect(page.getByText("4 / 250 words")).toBeVisible();
  await box.fill(words(250));
  await page.screenshot({ path: "test-results/details-word-count.png", fullPage: true });
});

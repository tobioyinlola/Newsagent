import { expect, test } from "@playwright/test";

test("the Terms of Use and Privacy Policy are pages, linked from the footer and from sign-up", async ({ page }) => {
  await page.goto("/");
  const footer = page.getByRole("contentinfo");
  await footer.getByRole("link", { name: "Terms of Use" }).first().click();
  await expect(page).toHaveURL(/\/terms$/);
  await expect(page.getByRole("heading", { name: "Terms of Use", level: 1 })).toBeVisible();
  // the permission to share videos and stories on social media is stated plainly
  await expect(page.getByRole("heading", { name: /Permission to publish and share your videos and stories/ })).toBeVisible();
  await expect(page.getByText(/YouTube, LinkedIn, X, Instagram, Facebook, TikTok/)).toBeVisible();
  await page.getByRole("link", { name: "Read the Privacy Policy" }).click();
  await expect(page).toHaveURL(/\/privacy$/);
  await expect(page.getByRole("heading", { name: "Privacy Policy", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: /How long we keep it/ })).toBeVisible();
  await page.getByRole("contentinfo").getByRole("link", { name: "Privacy Policy" }).first().click();
  await expect(page).toHaveURL(/\/privacy$/);

  // a contents link jumps to its section
  await page.getByRole("navigation", { name: "Contents" }).getByRole("link", { name: /Your rights and choices/ }).click();
  await expect(page).toHaveURL(/#rights$/);

  // sign-up cannot go on until both are agreed to, and offers links to read them
  await page.goto("/signup");
  const agree = page.getByLabel(/I have read and agree to the Terms of Use/);
  await expect(agree).not.toBeChecked();
  await expect(page.getByRole("link", { name: "Terms of Use" }).first()).toHaveAttribute("href", "/terms");
  await expect(page.getByRole("link", { name: "Privacy Policy" }).first()).toHaveAttribute("href", "/privacy");
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
});

test("the Terms and Privacy pages open at the top, even when reached from the bottom of another page", async ({ page }) => {
  await page.goto("/");
  await page.locator("footer").scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(500);
  await page.getByRole("contentinfo").getByRole("link", { name: "Terms of Use" }).first().click();
  await expect(page).toHaveURL(/\/terms$/);
  await expect(page.getByRole("heading", { name: "Terms of Use", level: 1 })).toBeInViewport();
  expect(await page.evaluate(() => window.scrollY)).toBe(0);

  // from the bottom of the Terms to the Privacy Policy
  await page.locator("#contact").scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(500);
  await page.getByRole("contentinfo").getByRole("link", { name: "Privacy Policy" }).first().click();
  await expect(page).toHaveURL(/\/privacy$/);
  await expect(page.getByRole("heading", { name: "Privacy Policy", level: 1 })).toBeInViewport();
  expect(await page.evaluate(() => window.scrollY)).toBe(0);

  // a link to a section still goes to that section
  await page.goto("/terms#permission");
  await expect(page.getByRole("heading", { name: /Permission to publish and share/ })).toBeInViewport();
});

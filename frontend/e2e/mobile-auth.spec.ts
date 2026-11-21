import { expect, test } from "@playwright/test";

// On a phone, sign-in and sign-up are just the form (no picture panel), and there is no Back button on the home screens.
test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("sign-in and sign-up show only the form, with no Back button", async ({ page }) => {
    for (const path of ["/login", "/signup"]) {
      await page.goto(path);
      await expect(page.locator(".auth-form-panel")).toBeVisible();
      await expect(page.locator(".auth-showcase")).toBeHidden();
      await expect(page.getByRole("button", { name: "Go back" })).toHaveCount(0);
    }
    await page.goto("/"); // arriving from another page of the app (so there is history to go back to) still shows no Back button
    await page.getByRole("link", { name: "Sign in" }).first().click();
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("button", { name: "Go back" })).toHaveCount(0);
  });

  test("the dashboard has no Back button, but other pages keep it", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Go back" })).toHaveCount(0);
    await page.getByRole("link", { name: /Make a video/ }).first().click();
    await expect(page).toHaveURL(/ai-newsroom\/new/);
    await expect(page.getByRole("button", { name: "Go back" })).toBeVisible();
  });
});

test("on a computer the sign-in picture panel is still there", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/login");
  await expect(page.locator(".auth-showcase")).toBeVisible();
});

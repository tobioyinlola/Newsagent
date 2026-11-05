import { expect, test } from "@playwright/test";

// Back office: every wallet with its balance, and a customer's full payment and usage history.
test("the team sees every wallet and a customer's payment and usage history", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/wallets");
  await expect(page.getByRole("heading", { name: "Wallets", exact: true })).toBeVisible();
  await expect(page.getByText("Credits left (all wallets)")).toBeVisible();
  const rows = page.getByRole("table", { name: "Customer wallets" }).locator("tbody tr");
  await expect(rows.first()).toBeVisible();
  const first = await rows.first().getByRole("link").innerText();

  // search and order
  await page.getByLabel("Search wallets").fill("zzz-no-such-company");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("No wallets match that search.")).toBeVisible();
  await page.getByLabel("Search wallets").fill("");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByLabel("Order by").selectOption("balance_low");
  await expect(rows.first()).toBeVisible();

  // a CSV of all wallets
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await download).suggestedFilename()).toBe("wallets.csv");

  // one customer's history
  await page.getByRole("link", { name: first, exact: true }).click();
  await expect(page.getByRole("heading", { name: "Wallet history" })).toBeVisible();
  await expect(page.getByText(/Balance now:/)).toBeVisible();
  for (const name of ["Everything", "Payments and credits added", "Usage"]) await expect(page.getByRole("button", { name })).toBeVisible();
  await page.getByRole("button", { name: "Usage" }).click();
  await expect(page.getByRole("button", { name: "Usage" })).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: "test-results/wallet-history.png", fullPage: true });
  await ctx.close();
});

import { expect, test } from "@playwright/test";

const methods = { ngn_per_usd: "1400", usd_card: true, ngn_card: true, ngn_bank_transfer: true };
const bank = { checkout_id: "bank-test", amount_usd: "10", amount_ngn: "14000", ngn_per_usd: "1400", credits: "3.70", status: "pending", reference: "CF0123456789abcdef0123456789abcdef", bank: { account_number: "0000000000", bank_name: "Test bank", beneficiary_name: null, account_label: "Test merchant" } };

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:ops@example.com"));
  await page.route("**/v1/billing/payment-methods", route => route.fulfill({ json: methods }));
});

test("NGN packages keep USD credit amounts and send the reviewed rate and chosen method", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/v1/billing/options", route => route.fulfill({ json: [{ amount_usd: "10", amount_ngn: "14000", credits: "3.70", videos: 3 }] }));
  let checkout: Record<string, unknown> | null = null;
  await page.route("**/v1/billing/checkout", async route => { checkout = route.request().postDataJSON(); await route.fulfill({ json: { checkout_id: "bank-test", url: "/billing/bank/bank-test" } }); });
  await page.route("**/v1/billing/bank/bank-test", route => route.fulfill({ json: bank }));
  await page.goto("/billing");
  await page.getByRole("radio", { name: "Nigerian naira (NGN)" }).check();
  await expect(page.getByText("₦14,000.00", { exact: true })).toBeVisible();
  await expect(page.getByText("3.70 credits", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: /Bank transfer/ }).check();
  await page.getByRole("button", { name: "Buy ₦14,000.00 of credits" }).click();
  await expect(page.getByRole("heading", { name: "Pay by bank transfer" })).toBeVisible();
  expect(checkout).toEqual({ amount_usd: "10", currency: "NGN", payment_method: "bank_transfer", ngn_per_usd: "1400" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test("unavailable NGN channels cannot start checkout", async ({ page }) => {
  await page.route("**/v1/billing/payment-methods", route => route.fulfill({ json: { ...methods, ngn_card: false, ngn_bank_transfer: false } }));
  await page.route("**/v1/billing/options", route => route.fulfill({ json: [{ amount_usd: "10", credits: "3.70", videos: 3 }] }));
  await page.goto("/billing");
  await page.getByRole("radio", { name: "Nigerian naira (NGN)" }).check();
  await expect(page.getByText(/Naira payments are being set up/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Buy ₦14,000.00 of credits" })).toBeDisabled();
  await page.getByRole("radio", { name: "US dollars (USD)" }).check();
  await expect(page.getByRole("button", { name: "Buy $10.00 of credits" })).toBeEnabled();
});

test("a forged bank return stays pending until the server confirms settlement", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let paid = false;
  await page.route("**/v1/billing/bank/bank-test", route => route.fulfill({ json: { ...bank, status: paid ? "paid" : "pending" } }));
  await page.goto("/billing/bank/bank-test?status=successful&paid=1");
  await expect(page.getByRole("heading", { name: "Transfer instructions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toHaveCount(0);
  await expect(page.getByText(bank.reference, { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  paid = true;
  await page.getByRole("button", { name: "Check transfer status" }).click();
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Transfer instructions" })).toHaveCount(0);
});

for (const option of [{ currency: "USD", method: "card", label: "Buy $1.00 of credits" }, { currency: "NGN", method: "card", label: "Buy ₦1,400.00 of credits" }, { currency: "NGN", method: "bank_transfer", label: "Buy ₦1,400.00 of credits" }]) {
  test(`one-dollar package: ${option.currency} ${option.method}`, async ({ page }) => {
    let checkout: Record<string, unknown> | null = null;
    await page.route("**/v1/billing/checkout", async route => { checkout = route.request().postDataJSON(); await route.fulfill({ json: { checkout_id: "one-dollar-test", url: "/billing?one-dollar-test=1" } }); });
    await page.goto("/billing");
    if (option.currency === "NGN") {
      await page.getByRole("radio", { name: "Nigerian naira (NGN)" }).check();
      if (option.method === "bank_transfer") await page.getByRole("radio", { name: /Bank transfer/ }).check();
    }
    const button = page.getByRole("button", { name: option.label, exact: true });
    const pack = page.locator("li").filter({ has: button });
    await expect(pack).toContainText("0.37 credits");
    await expect(pack).toContainText("Added to your wallet after payment");
    await button.click(); await expect(page).toHaveURL(/one-dollar-test=1/);
    expect(checkout).toEqual({ amount_usd: "1", currency: option.currency, payment_method: option.method, ...(option.currency === "NGN" ? { ngn_per_usd: "1400" } : {}) });
  });
}

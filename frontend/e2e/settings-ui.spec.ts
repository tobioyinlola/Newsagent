import { expect, test } from "@playwright/test";

test("settings tabs, legacy URLs and receipt submission remain usable on desktop and mobile", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "test"));
  let submitted = false;
  await page.route("**/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if (path === "/v1/me") data = { workspace_id: "test", workspace_name: "Ada Ventures", email: "ada@example.com", credit_balance: "30", permissions: [], is_operator: false };
    else if (path === "/v1/projects" || path === "/v1/distribution" || path === "/v1/auth/sessions" || ["/v1/billing/options", "/v1/billing/checkouts", "/v1/billing/ledger"].includes(path)) data = [];
    else if (path.includes("referrals")) data = { url: "https://www.coverfounder.com/signup?ref=test", reward_credits: "1", completed_referrals: 0, earned_credits: "0", referrals: [] };
    else if (path === "/v1/billing/transfer/purchase/uploads") data = { proof_id: "proof", upload_url: new URL(route.request().url()).origin + "/test-receipt-upload" };
    else if (path.endsWith("/submit")) { submitted = true; data = { ok: true }; }
    else if (path === "/v1/billing/transfer/purchase") data = { id: "purchase", status: submitted ? "pending_review" : "pending", currency: "NGN", amount: "14000", amount_usd: "10", credits: "3.7", ngn_per_usd: "1400", reference: "CF-TEST", bank: { bank_name: "Example bank", account_number: "1234567890" }, receipt: null };
    else if (path === "/v1/billing/summary") data = { credit_balance: "30", usd_per_credit: "2.7", low_balance_threshold: "5" };
    else if (path === "/v1/billing/usage") data = { lines: [], month: "2026-10", total_credits: "0" };
    return route.fulfill({ json: data });
  });
  await page.route("**/test-receipt-upload", route => route.fulfill({ status: 200, body: "" }));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/settings");
  await expect(page).toHaveURL(/settings\/profile/);
  await expect(page.getByRole("heading", { name: "Your profile", exact: true })).toBeVisible();
  const sidebar = page.getByRole("navigation", { name: "Main", exact: true });
  await expect(sidebar.getByRole("link", { name: "Settings", exact: true })).toBeVisible();
  await expect(sidebar.getByRole("link", { name: "Credits", exact: true })).toHaveCount(0);
  for (const [tab, heading] of [["Password", "Change password"], ["Referral", "Invite a business. Earn a credit."], ["Billing", "Credits and billing"]]) {
    await page.getByRole("navigation", { name: "Settings tabs" }).getByRole("link", { name: tab, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  }
  await page.goto("/billing?returnTo=%2Fdistribution%2Frequest%3Fdraft%3Dexample");
  await expect(page).toHaveURL(/settings\/billing\?returnTo=/);
  await expect(page.getByRole("link", { name: "Return to your saved distribution request" })).toHaveAttribute("href", "/distribution/request?draft=example");
  for (const [old, tab] of [["account", "profile"], ["security", "password"], ["referrals", "referral"]]) {
    await page.goto(`/${old}`); await expect(page).toHaveURL(new RegExp(`settings/${tab}$`));
  }
  await page.getByRole("navigation", { name: "Settings tabs" }).getByRole("link", { name: "Password", exact: true }).click();
  await page.getByRole("button", { name: "Go back", exact: true }).click();
  await expect(page).toHaveURL(/settings\/referral$/);
  await page.screenshot({ path: "/tmp/cf-settings-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.goto("/billing/transfer/purchase");
  await page.getByRole("button", { name: "I have paid", exact: true }).click();
  const submit = page.getByRole("button", { name: "Submit receipt for approval" });
  await expect(submit).toBeDisabled();
  await page.getByLabel("Payment receipt", { exact: true }).setInputFiles({ name: "receipt.txt", mimeType: "text/plain", buffer: Buffer.from("invalid") });
  await expect(page.getByRole("alert")).toContainText("PNG, JPEG or PDF");
  await expect(submit).toBeDisabled();
  await page.getByLabel("Payment receipt", { exact: true }).setInputFiles({ name: "receipt.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF receipt") });
  await expect(page.getByText("receipt.pdf", { exact: true })).toBeVisible();
  await expect(submit).toBeEnabled();
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(submit).toBeDisabled();
  await page.getByLabel("Payment receipt", { exact: true }).setInputFiles({ name: "receipt.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF receipt") });
  await expect(submit).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/cf-receipt-upload-mobile.png", fullPage: true });
  await submit.click();
  await expect(page.getByRole("heading", { name: "Receipt submitted — awaiting approval" })).toBeVisible();
});

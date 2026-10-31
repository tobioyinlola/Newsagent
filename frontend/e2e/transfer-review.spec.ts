import { expect, test } from "@playwright/test";
const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("USD and NGN transfers require receipts and admin approval before wallet credits", async ({ page, request, browser }) => {
  test.skip(process.env.BANK_TRANSFER_REVIEW_ENABLED !== "true", "Run with BANK_TRANSFER_REVIEW_ENABLED=true");
  for (const currency of ["USD", "NGN"]) {
    const configured = await request.put(`${API}/v1/admin/bank-transfer-accounts/${currency}`, { headers: OPS, data: { bank_name: "Test transfer bank", beneficiary_name: "Test Cover Founder", account_number: currency === "USD" ? "1111222233" : "4444555566", routing_number: currency === "USD" ? "021000021" : "" } });
    expect(configured.ok()).toBeTruthy();
  }
  const email = `transfer${Date.now()}@example.com`;
  const invited = await (await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: "Transfer Journey", credits: "0", spend_cap: "100" } })).json();
  await request.post(`${API}/v1/auth/signup/start`, { data: { invite_code: invited.code, password: "correct horse battery" } });
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  const signup = await (await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: invited.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } })).json();
  const headers = { Authorization: `Bearer ${signup.token}` };
  await page.addInitScript(t => localStorage.setItem("newsagent.token", t), signup.token);
  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  await admin.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  let expectedCredits = 0;
  for (const currency of ["USD", "NGN"] as const) {
    await page.goto("/billing");
    await page.getByRole("radio", { name: currency === "USD" ? "US dollars (USD)" : "Nigerian naira (NGN)" }).check();
    await expect(page.getByText(/Card.*coming soon/i).first()).toBeVisible();
    await page.getByLabel("Credits to buy").fill("220");
    await page.getByRole("button", { name: "Buy custom credits" }).click();
    await expect(page.getByRole("heading", { name: "Pay by bank transfer" })).toBeVisible();
    const id = page.url().split("/").pop()!;
    await expect(page.getByText(currency === "USD" ? "$594.00" : "₦831,600.00", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "I have paid", exact: true }).click();
    await expect(page.getByRole("button", { name: "Submit receipt for approval" })).toBeDisabled();
    await page.getByLabel("Payment receipt", { exact: true }).setInputFiles({ name: `${currency}-receipt.png`, mimeType: "image/png", buffer: Buffer.concat([PNG, Buffer.from(currency)]) });
    await expect(page.getByText(`${currency}-receipt.png`, { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Submit receipt for approval" }).click();
    await expect(page.getByRole("heading", { name: "Receipt submitted — awaiting approval" })).toBeVisible();
    expect(Number((await (await request.get(`${API}/v1/billing/summary`, { headers })).json()).credit_balance)).toBe(expectedCredits);
    const alert = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: "ops@example.com" } })).json();
    expect(alert.subject).toContain("Action required");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/${currency.toLowerCase()}-transfer-pending-mobile.png`, fullPage: true });
    await admin.goto("/admin/revenue");
    const row = admin.locator("details").filter({ has: admin.locator("summary", { hasText: `Transfer Journey · ${currency}` }) }).first();
    await row.locator("summary").first().click();
    await row.getByLabel("Confirmed bank transaction reference").fill(`LIVE-TEST-${currency}-${Date.now()}`);
    await row.getByLabel("Verification note").fill("Verified exact funds in the test receiving bank statement.");
    await row.getByRole("checkbox", { name: /I verified that the correct funds/ }).check();
    await row.getByRole("button", { name: "Approve and add credits" }).click();
    await expect(admin.getByRole("status")).toContainText("Payment approved");
    await page.getByRole("button", { name: "Check approval status" }).click();
    await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible();
    expectedCredits += 220;
    expect(Number((await (await request.get(`${API}/v1/billing/summary`, { headers })).json()).credit_balance)).toBe(expectedCredits);
    expect((await (await request.get(`${API}/v1/billing/transfer/${id}`, { headers })).json()).status).toBe("paid");
    await page.getByRole("link", { name: "View wallet and history" }).click();
    await expect(page.getByText("Approved / paid", { exact: true }).first()).toBeVisible();
  }
  await adminContext.close();
});

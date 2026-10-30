import { generateKeyPairSync } from "node:crypto";
import { expect, test } from "@playwright/test";
const { publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048, publicKeyEncoding: { type: "spki", format: "pem" }, privateKeyEncoding: { type: "pkcs8", format: "pem" } });
const fields = [["First name on card", "Ada"], ["Last name on card", "Obi"], ["Card number", "4111 1111 1111 1111"], ["Expiry date (MM/YY)", "12/35"], ["Security code", "123"], ["Billing address", "1 Main Street"], ["City", "Lagos"], ["State / province / region", "Lagos"], ["Country code", "NG"]];

test("card failure permits fresh details only after server-authorized recovery", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:ops@example.com"));
  let attempts = 0;
  let payment = { checkout_id: "recover", amount_usd: "1", credits: "0.37", currency: "USD", amount: "1", status: "pending", provider_status: "requires_action", can_retry_confirmation: true, public_key: publicKey, sandbox: true, next_action_url: null, payment_error: null as { code: string; message: string } | null };
  await page.route("**/v1/billing/card/recover", route => route.fulfill({ json: payment }));
  await page.route("**/v1/billing/card/recover/confirm", async route => {
    attempts++; expect(route.request().postData()).not.toContain("4111111111111111");
    if (attempts === 1) { payment = { ...payment, payment_error: { code: "error_validation_error", message: "Provider rejected payment details." } }; await route.fulfill({ status: 503, json: { detail: "Provider rejected payment details." } }); }
    else { payment = { ...payment, status: "paid", provider_status: "completed", can_retry_confirmation: false }; await route.fulfill({ json: payment }); }
  });
  await page.goto("/billing/card/recover");
  for (const [label, value] of fields) await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByRole("button", { name: "Pay $1.00", exact: true }).click();
  await expect(page.getByText(/Please re-enter your card details/)).toBeVisible();
  await expect(page.getByLabel("Card number", { exact: true })).toHaveValue("");
  for (const [label, value] of fields) await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByRole("button", { name: "Pay $1.00", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible(); expect(attempts).toBe(2);
});

test("customer bank claim, finance matching and customer payment confirmation", async ({ page, browser }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:ops@example.com"));
  const id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"; const reference = "100004261030154115175873657637";
  let claimed = false; let matched = false; let matches = 0;
  const purchase = () => ({ checkout_id: id, amount_usd: "1", amount_ngn: "1400", ngn_per_usd: "1400", credits: "0.37", status: matched ? "paid" : "pending", reference: "CF" + id, claim: claimed ? { status: matched ? "matched" : "pending_review", reference } : null, bank: { bank_name: "Test bank", account_number: "0000000000", account_label: "Test merchant", beneficiary_name: null } });
  await page.route(`**/v1/billing/bank/${id}`, route => route.fulfill({ json: purchase() }));
  await page.route(`**/v1/billing/bank/${id}/claim`, async route => { expect(route.request().postDataJSON()).toEqual({ reference }); claimed = true; await route.fulfill({ json: { status: "pending_review" } }); });
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto(`/billing/bank/${id}`);
  await page.getByLabel("Bank transaction reference", { exact: true }).fill(reference);
  await page.getByRole("button", { name: "Submit transfer for review" }).click();
  await expect(page.getByText(/Our team is reviewing the payment match/)).toBeVisible();
  const admin = await browser.newContext(); const ap = await admin.newPage();
  await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  const report = () => ({ receipts: [{ id: "receipt", transfer_id: "transfer", amount_ngn: "1400", reference, narration: "Bank changed narration", status: matched ? "matched" : "unmatched", checkout_id: matched ? id : null, matched_by: matched ? "ops@example.com" : null }], checkouts: [{ id, company: "Receipt Test", provider: "nuvion_bank", status: matched ? "paid" : "pending", currency: "NGN", amount: "1400", credits: "0.37", claim: { transfer_id: "transfer", status: matched ? "matched" : "pending_review" } }] });
  await ap.route("**/v1/admin/payment-reconciliation", route => route.fulfill({ json: report() }));
  await ap.route("**/v1/admin/payment-reconciliation/receipts/receipt/match", async route => { const body = route.request().postDataJSON(); expect(body.checkout_id).toBe(id); expect(body.ownership_confirmed).toBe(true); expect(body.reason.length).toBeGreaterThan(10); matched = true; matches++; await route.fulfill({ json: { result: "granted", status: "paid" } }); });
  await ap.goto("/admin/revenue"); const receipt = ap.locator("details").filter({ hasText: reference }); await receipt.locator("summary").click();
  await expect(receipt.getByRole("button", { name: "Match transfer and apply credits" })).toBeDisabled();
  await receipt.getByLabel("Assign to purchase", { exact: true }).selectOption(id);
  await receipt.getByLabel("Matching reason", { exact: true }).fill("Verified the payer receipt and purchase ownership.");
  await receipt.getByLabel("I verified this transfer belongs to the selected customer and purchase.").check();
  await receipt.getByRole("button", { name: "Match transfer and apply credits" }).click();
  await expect(ap.getByRole("status")).toContainText("wallet credits applied once");
  await page.getByRole("button", { name: "Check transfer status" }).click();
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible(); expect(matches).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy(); await admin.close();
});

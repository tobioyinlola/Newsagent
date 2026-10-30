import { constants, generateKeyPairSync, privateDecrypt } from "node:crypto";
import { expect, test } from "@playwright/test";

const { publicKey, privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048, publicKeyEncoding: { type: "spki", format: "pem" }, privateKeyEncoding: { type: "pkcs8", format: "pem" } });
const details = { checkout_id: "card-test", amount_usd: "10", credits: "3.70", currency: "USD", status: "pending", provider_status: "requires_action", public_key: publicKey, sandbox: true, next_action_url: null };

test("card details are encrypted before the API request and verified payment shows wallet confirmation", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:ops@example.com"));
  let payment = { ...details };
  let confirmations = 0;
  await page.route("**/v1/billing/card/card-test", route => route.fulfill({ json: payment }));
  await page.route("**/v1/billing/card/card-test/confirm", async route => {
    confirmations++;
    const body = route.request().postDataJSON();
    const raw = route.request().postData()!;
    expect(raw).not.toContain("4111111111111111");
    expect(body).not.toHaveProperty("number");
    expect(body).not.toHaveProperty("cvv");
    const decrypted = JSON.parse(privateDecrypt({ key: privateKey, padding: constants.RSA_PKCS1_OAEP_PADDING, oaepHash: "sha256" }, Buffer.from(body.encrypted_data, "base64")).toString());
    expect(decrypted).toEqual({ card_number: "4111111111111111", expiration_month: "12", expiration_year: "2035", cvv: "123", card_holder_name: "Ada Obi" });
    expect(body.billing_address.country).toBe("NG");
    payment = { ...payment, status: "paid", provider_status: "completed" };
    await route.fulfill({ json: payment });
  });
  await page.goto("/billing/card/card-test");
  await expect(page.getByText("Sandbox payment: no real money will be charged.")).toBeVisible();
  await page.getByRole("button", { name: "Pay $10.00" }).click();
  await expect(page.getByLabel("Card number", { exact: true })).toHaveAttribute("aria-invalid", "true");
  expect(confirmations).toBe(0);
  for (const [label, value] of [["First name on card", "Ada"], ["Last name on card", "Obi"], ["Card number", "4111 1111 1111 1111"], ["Expiry date (MM/YY)", "12/35"], ["Security code", "123"], ["Billing address", "1 Main Street"], ["City", "Lagos"], ["State / province / region", "Lagos"], ["Country code", "ng"]]) await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByRole("button", { name: "Pay $10.00" }).click();
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible();
  expect(confirmations).toBe(1);
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(stored).not.toContain("4111");
  expect(stored).not.toContain("cvv");
});

test("a forged successful return URL does not show credit until the server verifies payment", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:ops@example.com"));
  let paid = false;
  await page.route("**/v1/billing/card/card-test", route => route.fulfill({ json: { ...details, status: paid ? "paid" : "pending", provider_status: paid ? "completed" : "processing" } }));
  await page.goto("/billing/card/card-test?status=completed&amount=1000&currency=USD");
  await expect(page.getByRole("heading", { name: "Payment verification" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Pay $10.00" })).toHaveCount(0);
  paid = true;
  await page.getByRole("button", { name: "Check payment status" }).click();
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible();
});

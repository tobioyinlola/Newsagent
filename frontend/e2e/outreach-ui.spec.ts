import { expect, test } from "@playwright/test";

// The conversation screen with a held draft and account details, drawn from stubbed API answers (the server's own behaviour is covered by its tests).
const thread = { id: "t1", request_id: "r1", placement_id: "p1", outlet_id: "2", outlet_name: "Techpoint Africa", contact_name: "Bayo Ade", contact_email: "bayo@example.com", status: "needs_approval", ai_paused: false, last_inbound_at: null, last_outbound_at: null, updated_at: "2026-11-05T10:00:00Z", last: { direction: "in", status: "received", snippet: "Our rate is $500" } };
const messages = [
  { id: "m1", direction: "out", kind: "template", status: "sent", subject: "Rates for a sponsored article on Techpoint Africa?", body: "Hello Bayo, what is your rate?", sender: "", actor: "system", ai: {}, created_at: "2026-11-05T09:00:00Z", sent_at: "2026-11-05T09:00:01Z" },
  { id: "m2", direction: "in", kind: "received", status: "received", subject: "Re: Rates", body: "Our rate is $500. Pay to account ••••6789.", sender: "Bayo <billing@other-company.example.org>", actor: "billing@other-company.example.org", ai: { sender_mismatch: true, has_account_details: true, suspicious: true }, created_at: "2026-11-05T09:30:00Z", sent_at: "2026-11-05T09:30:00Z" },
  { id: "m3", direction: "out", kind: "ai_draft", status: "pending_approval", subject: "Re: Rates", body: "Thank you for your details. We will confirm shortly.", sender: "", actor: "ai", ai: { step: "confirm_account_details", reasons: ["“Confirm account details” involves payment or account details, so a person always handles it.", "The reply came from a different company than the contact we wrote to."] }, created_at: "2026-11-05T09:31:00Z", sent_at: null },
];
const config = { config: { templates: [{ id: "intro", name: "Friendly introduction", subject: "Hi", body: "Hello" }], default_template: "intro", sender_name: "Ngozi", sender_title: "Partnerships", footer_address: "", mode: "policy", daily_cap: 200, ai_turn_limit: 6, paused: false, policy: {}, reply_delay_minutes: 10, new_gap_minutes: 3, new_daily_cap: 30, send_cap_per_day: 150 }, variables: ["headline"], steps: [{ id: "thanks", label: "Thank them", never_auto: false, default: "auto" }, { id: "discuss_price", label: "Talk about their price", never_auto: false, default: "approve" }, { id: "accept_offer", label: "Accept their offer (commit to pay)", never_auto: true, default: "approve" }], engine_on: true, reply_domain: "", sending: { via_mailbox: true, mailbox: "outreach@coverfounder.com", reads_replies: true, reply_address_example: "outreach+0123456789abcdef0123@coverfounder.com" } };

test("a held draft, a suspicious sender and account details are shown clearly", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.route("**/v1/admin/outreach/config", (r) => r.fulfill({ json: config }));
  await page.route("**/v1/admin/outreach/threads?**", (r) => r.fulfill({ json: { threads: [thread], counts: { needs_approval: 1 } } }));
  await page.route("**/v1/admin/outreach/threads/t1", (r) => r.fulfill({ json: { thread, messages, facts: { quoted_price: 500, currency: "$", has_account_details: true, account_masked: "GT Bank · ••••6789", account_verified: false }, request: { id: "r1", headline: "Acme opens", status: "submitted" }, placement: { id: "p1", internal_status: "not_started", status: "pending" } } }));
  await page.route("**/v1/admin/outreach/threads/t1/account-details", (r) => r.fulfill({ json: { details: { account_number: "0123456789", bank_name: "GT Bank" }, messages: [], verified: false } }));
  await page.goto("/admin/outreach");
  await page.getByRole("button", { name: /Techpoint Africa/ }).click();
  await expect(page.getByText("The agent wrote this reply and is waiting for you")).toBeVisible();
  await expect(page.getByText(/always handles it/)).toBeVisible();
  await expect(page.getByText(/different company than our contact/)).toBeVisible();
  await expect(page.getByText("They sent account details: GT Bank · ••••6789")).toBeVisible();
  await expect(page.getByText(/Never pay on an email alone/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve and send" })).toBeVisible();
  await page.getByRole("button", { name: "Show the full details (recorded)" }).click();
  await expect(page.getByText("0123456789")).toBeVisible();
  await page.screenshot({ path: "test-results/outreach-thread.png", fullPage: true });

  await page.getByRole("button", { name: "Templates and settings" }).click();
  await expect(page.getByRole("heading", { name: "Sending and pacing" })).toBeVisible();
  await expect(page.getByText(/Emails go out from the mailbox/)).toBeVisible();
  await expect(page.getByLabel("Wait before replying (minutes)")).toHaveValue("10");
  await expect(page.getByRole("button", { name: "Send test email" })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "What the AI agent may do" })).toBeVisible();
  await expect(page.getByLabel("Accept their offer (commit to pay): automatic or approval")).toBeDisabled(); // money steps are never automatic
  await expect(page.getByLabel("Thank them: automatic or approval")).toBeEnabled();
  await page.screenshot({ path: "test-results/outreach-settings.png", fullPage: true });
  await ctx.close();
});

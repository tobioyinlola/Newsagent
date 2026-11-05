import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };

// Back office: set up contacts and templates, then read and answer a conversation with an outlet.
test("the team imports outlet contacts, edits a template and replies in a conversation", async ({ browser, request }) => {
  const before = await (await request.get(`${API}/v1/admin/distribution/config`, { headers: OPS })).json();
  const techpoint = before.outlets.find((o: { name: string }) => o.name === "Techpoint Africa");
  const admin = await browser.newContext();
  const page = await admin.newPage();
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/outreach");
  await expect(page.getByRole("heading", { name: "Outreach to outlets" })).toBeVisible();
  await expect(page.getByText(/Outreach conversations are switched off/)).toBeVisible();

  // contacts: check first, then save
  await page.getByRole("button", { name: "Contacts" }).click();
  await page.getByLabel("Contacts", { exact: true }).fill("Techpoint Africa, Bayo Ade, bayo@example.com, rates\nNo Such Outlet, X, x@example.com\nTribune, Chi, not-an-email");
  await page.getByRole("button", { name: "Check the list" }).click();
  await expect(page.getByText("Will be saved")).toHaveCount(1);
  await expect(page.getByText("No outlet with that name")).toBeVisible();
  await expect(page.getByText("Not a valid email")).toBeVisible();
  await page.getByRole("button", { name: "Save 1 contacts" }).click();
  await expect(page.getByText("Saved 1 contacts.")).toBeVisible();
  const cfg = await (await request.get(`${API}/v1/admin/distribution/config`, { headers: OPS })).json();
  expect(cfg.outlets.find((o: { name: string }) => o.name === "Techpoint Africa").contact_email).toBe("bayo@example.com");

  // templates: edit the sender, preview
  await page.getByRole("button", { name: "Templates and settings" }).click();
  await page.getByLabel("Sender name").fill("Ngozi Eze");
  await page.getByRole("button", { name: "Preview with sample details" }).first().click();
  await expect(page.getByText(/Hello Ada/)).toBeVisible();
  await page.getByRole("button", { name: "Save outreach settings" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await page.getByRole("button", { name: "Conversations" }).click();
  await expect(page.getByText(/No conversations yet/)).toBeVisible();
  await page.screenshot({ path: "test-results/outreach-admin.png" });
  await request.put(`${API}/v1/admin/distribution/outlets/${techpoint.id}`, { headers: OPS, data: techpoint }); // leave the shared test data as it was
  await admin.close();
});

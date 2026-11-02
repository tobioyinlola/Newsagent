import { type APIRequestContext, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };

async function balance(request: APIRequestContext, workspace: string): Promise<number> {
  const list = await (await request.get(`${API}/v1/admin/workspaces`, { headers: OPS })).json();
  return Number(list.find((w: { id: string }) => w.id === workspace).credit_balance);
}

test("adding credit to a wallet asks for confirmation first, with the business, the amount and the new balance", async ({ page, request }) => {
  const name = `Credit Check ${Date.now()}`;
  const inv = await (await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: `credit${Date.now()}@customer.example.com`, workspace_name: name, credits: "3" } })).json();
  const workspace: string = inv.workspace_id;
  const start = await balance(request, workspace);

  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.goto("/admin/billing");
  await page.getByLabel("Workspace").selectOption({ label: name });
  await page.getByLabel("Credits").fill("12.5");
  await page.getByLabel("Reference (invoice or transfer id)").fill(`TRF-${Date.now()}`);
  await page.getByLabel("Note").fill("Bank transfer received");
  await page.getByRole("button", { name: "Add credits" }).click();

  // the summary: nothing is added yet
  const dialog = page.getByRole("alertdialog", { name: `Add 12.50 credits to ${name}?` });
  await expect(dialog).toBeVisible();
  const summary = dialog.getByLabel("Credit summary");
  await expect(summary).toContainText(name);
  await expect(summary).toContainText(`${start.toFixed(2)} credits`); // balance now
  await expect(summary).toContainText("+12.50 credits");
  await expect(summary).toContainText(`${(start + 12.5).toFixed(2)} credits`); // new balance
  await expect(summary).toContainText("Bank transfer received");
  expect(await balance(request, workspace)).toBe(start);

  // Cancel adds nothing
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  expect(await balance(request, workspace)).toBe(start);

  // confirming adds exactly the amount, once
  await page.getByRole("button", { name: "Add credits" }).click();
  await page.getByRole("button", { name: "Yes, add 12.50 credits" }).click();
  await expect(page.getByText("Credits added.")).toBeVisible();
  expect(await balance(request, workspace)).toBe(start + 12.5);
});

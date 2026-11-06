import { expect, test } from "@playwright/test";

// A finished video can be made again with the default presenter from the customer's page in the back office.
test("the back office offers to remake a finished video with the default presenter", async ({ page, request }) => {
  const API = "http://localhost:8000";
  const OPS = { Authorization: "Bearer dev:ops@example.com" };
  const list = await (await request.get(`${API}/v1/admin/workspaces`, { headers: OPS })).json();
  expect(list.length).toBeGreaterThan(0);
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await page.route("**/v1/admin/customers/*", async (route) => {
    const r = await route.fetch(); const body = await r.json();
    body.projects = [{ id: "abcdef0123456789", state: "final_ready", interview: "live", created_at: "2026-11-01T10:00:00Z", completed_at: "2026-11-01T10:20:00Z", vendor_cost: "1.00", published: true }, ...(body.projects ?? [])];
    await route.fulfill({ response: r, json: body });
  });
  let asked = "";
  await page.route("**/v1/admin/projects/abcdef0123456789/presenter", (route) => { asked = route.request().postData() ?? ""; return route.fulfill({ json: { ok: true } }); });
  await page.goto(`/admin/customers/${list[0].id}`);
  const btn = page.getByRole("button", { name: "Remake with the default presenter" }).first();
  await expect(btn).toBeVisible();
  page.once("dialog", (d) => { expect(d.message()).toContain("customer's credits"); void d.accept(); });
  await btn.click();
  await expect.poll(() => asked).toBe("{}");
});

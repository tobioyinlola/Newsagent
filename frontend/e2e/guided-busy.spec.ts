import { expect, test } from "@playwright/test";

// When the writing model is busy the customer is told to try again, and trying again must not make a second draft video.
test("a busy writing model gives a calm message, and retrying reuses the draft", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  let drafts = 0, starts = 0;
  await page.route(/\/v1\/projects$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    drafts++;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "busy-test-project", state: "draft", flow: "guided" }) });
  });
  await page.route(/\/v1\/projects\/busy-test-project\/guided\/start$/, async (route) => {
    starts++;
    if (starts === 1) return route.fulfill({ status: 503, headers: { "retry-after": "5" }, contentType: "application/json", body: JSON.stringify({ detail: "Our writing assistant is very busy right now. Nothing was lost or charged. Please try again in a minute." }) });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "busy-test-project", state: "interviewing", flow: "guided" }) });
  });
  await page.goto("/ai-newsroom/new");
  await page.getByLabel("Tell us the key details").fill("Acme Farms raised a seed round to help farmers in Kumasi sell their produce online and get paid by phone.");
  await page.getByLabel("First name").fill("Ada");
  await page.getByLabel("Last name").fill("Mensah");
  await page.getByLabel("Role").fill("CEO");
  await page.getByLabel("Company name").fill("Acme");
  await page.getByLabel("City", { exact: false }).first().fill("Kumasi");
  await page.getByLabel("Country").fill("Ghana");
  const submit = page.getByRole("button", { name: /Continue|Start|Next|Begin/i }).last();
  await submit.click();
  await expect(page.getByText("Our writing assistant is very busy right now")).toBeVisible();
  expect(drafts).toBe(1);
  await submit.click(); // try again
  await expect.poll(() => starts).toBe(2);
  expect(drafts).toBe(1); // still one draft: nothing was created twice
});

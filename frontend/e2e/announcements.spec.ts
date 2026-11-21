import { expect, test, type Page } from "@playwright/test";

// The team writes an announcement in Marketing; customers see it as a pop-up after signing in for as long as the team chose.
const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };
const shot = async (page: Page, name: string) => { if (process.env.SHOTS) { await page.waitForTimeout(300); await page.screenshot({ path: `${process.env.SHOTS}/${name}.png` }); } };
const TITLE = "Kenya outlets are now live";

async function endAll(request: import("@playwright/test").APIRequestContext) {
  const list = await (await request.get(`${API}/v1/admin/marketing/announcements?limit=50`, { headers: OPS })).json();
  for (const a of list.items) if (a.status !== "ended") await request.post(`${API}/v1/admin/marketing/announcements/${a.id}/end`, { headers: OPS });
}
const customer = async (browser: import("@playwright/test").Browser, viewport = { width: 1280, height: 800 }) => {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  return { ctx, page };
};

test("an announcement written in the back office pops up for customers, and closing it sticks", async ({ browser, request }) => {
  await endAll(request);
  try {
    const admin = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
    const ap = await admin.newPage();
    await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
    await ap.goto("/admin/marketing/announcements");
    await expect(ap.getByRole("heading", { name: "Announcements", level: 2 })).toBeVisible();
    await ap.getByRole("button", { name: "New announcement" }).first().click();
    await ap.getByLabel("Headline").fill(TITLE);
    await ap.getByLabel("Message").fill("Send your story to outlets in Kenya from today.");
    await ap.getByLabel("Button text (optional)").fill("Choose outlets");
    await ap.getByLabel("Where the button goes").fill("/distribution/request");
    await ap.getByLabel("Keep showing it for").fill("2");
    await ap.getByLabel("Hours or days").selectOption("days");
    await expect(ap.getByRole("complementary", { name: "Preview" })).toContainText(TITLE); // a live preview of the pop-up
    await expect(ap.getByRole("radio", { name: /In the app only/ })).toBeChecked(); // the choice is always there: app only, or app and email
    await expect(ap.getByRole("radio", { name: /In the app and by email/ })).toBeDisabled(); // (email is switched off on this server, and the page says why)
    await expect(ap.getByText(/Marketing email is switched off on the server/).first()).toBeVisible();
    await shot(ap, "1-admin-new-announcement");
    await ap.getByRole("button", { name: "Review and publish" }).click();
    await expect(ap.getByRole("alertdialog")).toContainText("for 2 days");
    await ap.getByRole("button", { name: "Publish", exact: true }).click();
    await expect(ap.getByText(TITLE)).toBeVisible();
    await expect(ap.getByText("live", { exact: true })).toBeVisible();
    await shot(ap, "2-admin-announcement-list");
    await admin.close();

    const a = await customer(browser);
    await a.page.goto("/dashboard");
    const popup = a.page.getByRole("dialog", { name: TITLE });
    await expect(popup).toBeVisible();
    await shot(a.page, "3-customer-popup-desktop");
    await popup.getByRole("button", { name: "Remind me later" }).click();
    await expect(popup).toHaveCount(0);
    await a.page.reload();
    await expect(a.page.getByRole("dialog", { name: TITLE })).toHaveCount(0); // later means: not again this visit
    await a.ctx.close();

    const b = await customer(browser); // signing in again later: it is back
    await b.page.goto("/dashboard");
    await expect(b.page.getByRole("dialog", { name: TITLE })).toBeVisible();
    await b.page.getByRole("button", { name: "Choose outlets" }).click(); // the button goes where the team said, and closes it for good
    await expect(b.page).toHaveURL(/distribution\/request/);
    await b.ctx.close();

    const c = await customer(browser);
    await c.page.goto("/dashboard");
    await expect(c.page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await expect(c.page.getByRole("dialog", { name: TITLE })).toHaveCount(0);
    await c.ctx.close();

    // the team sees how it did: one person saw it (however many times it appeared), pressed the button, and closed it for good
    const again = await browser.newContext({ viewport: { width: 1280, height: 1000 }, deviceScaleFactor: 2 });
    const rp = await again.newPage();
    await rp.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
    await rp.goto("/admin/marketing/announcements");
    const results = rp.getByRole("list").getByRole("term").first().locator("xpath=ancestor::dl");
    await expect(results).toContainText("Saw the pop-up");
    await expect(results.locator("div").nth(0).getByRole("definition").first()).toHaveText("1");
    await expect(results.locator("div").nth(1).getByRole("definition").first()).toHaveText("1");
    await expect(results.locator("div").nth(2).getByRole("definition").first()).toHaveText("1");
    await shot(rp, "7-announcement-results");
    await again.close();
  } finally { await endAll(request); }
});

test("on a phone the pop-up fits the screen and every button can be reached", async ({ browser, request }) => {
  await endAll(request);
  const created = await request.post(`${API}/v1/admin/marketing/announcements`, { headers: OPS, data: { title: TITLE, message: "A long message. ".repeat(60), button_label: "Choose outlets", button_url: "/distribution/request", show_for: 1, unit: "days", send_email: false } });
  expect(created.status()).toBe(201);
  try {
    const { ctx, page } = await customer(browser, { width: 390, height: 640 });
    await page.goto("/dashboard");
    const popup = page.getByRole("dialog", { name: TITLE });
    await expect(popup).toBeVisible();
    const box = (await popup.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.y + box.height).toBeLessThanOrEqual(640 + 1); // never taller than the screen: long text scrolls inside it
    await shot(page, "4-customer-popup-phone");
    for (const name of ["Choose outlets", "Got it", "Remind me later"]) await expect(popup.getByRole("button", { name }), name + " stays in reach however long the message is").toBeInViewport();
    await popup.getByRole("button", { name: "Got it" }).click();
    await expect(popup).toHaveCount(0);
    await ctx.close();
  } finally { await endAll(request); }
});

test("the wording of an announcement can be corrected after it has gone out, and the pop-up changes at once", async ({ browser, request }) => {
  await endAll(request);
  const created = await request.post(`${API}/v1/admin/marketing/announcements`, { headers: OPS, data: { title: "We launch on Dec 1st", message: "Cover Founder opens to everyone on Dec 1.", show_for: 2, unit: "days", send_email: false } });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id as string;
  const admin = await browser.newContext({ viewport: { width: 1280, height: 1000 }, deviceScaleFactor: 2 });
  const ap = await admin.newPage();
  await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  try {
    await ap.goto("/admin/marketing/announcements");
    await ap.getByRole("button", { name: "Edit the wording" }).first().click();
    await expect(ap.getByRole("heading", { name: "Edit announcement" })).toBeVisible();
    await expect(ap.getByText(/It wasn’t emailed, so there is no email to change/)).toBeVisible(); // it says what will and won't change
    await expect(ap.getByText("How long the pop-up shows")).toHaveCount(0); // only the wording is edited here
    await ap.getByLabel("Headline").fill("We launch publicly on December 1");
    await ap.getByRole("textbox", { name: /^Message/ }).fill("Cover Founder opens to everyone on December 1. Thank you for being here early.");
    await expect(ap.getByRole("complementary", { name: "Preview" })).toContainText("We launch publicly on December 1");
    await shot(ap, "8-edit-announcement");
    await ap.getByRole("button", { name: "Save changes" }).click();
    await expect(ap.getByText("We launch publicly on December 1")).toBeVisible();

    const c = await customer(browser);
    await c.page.goto("/dashboard");
    const popup = c.page.getByRole("dialog", { name: "We launch publicly on December 1" }); // customers see the corrected words straight away
    await expect(popup).toBeVisible();
    await expect(popup).toContainText("Thank you for being here early");
    await c.ctx.close();

    await request.post(`${API}/v1/admin/marketing/announcements/${id}/end`, { headers: OPS });
    await ap.reload();
    await expect(ap.getByRole("button", { name: "Edit the wording" }).first()).toBeVisible(); // and an ended one can still be corrected
  } finally { await admin.close(); await endAll(request); }
});

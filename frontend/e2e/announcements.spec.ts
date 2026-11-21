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
    await ap.getByRole("textbox", { name: /^Message/ }).fill("Send your story to outlets in Kenya from today.");
    await ap.getByRole("radio", { name: /Open a link/ }).check();
    await ap.getByLabel("Button text").fill("Choose outlets");
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

test("a launch announcement whose button lets customers share their referral link to their socials", async ({ browser, request }) => {
  await endAll(request);
  const admin = await browser.newContext({ viewport: { width: 1280, height: 1000 }, deviceScaleFactor: 2 });
  const ap = await admin.newPage();
  await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  try {
    await ap.goto("/admin/marketing/announcements");
    await ap.getByRole("button", { name: "New announcement" }).first().click();
    await ap.getByLabel("Headline").fill("We launch publicly on December 1");
    await ap.getByRole("textbox", { name: /^Message/ }).fill("Cover Founder opens to everyone on December 1. Thank you for being here early. Your account, videos and credits stay exactly as they are. Now's a great time to make your next story.");
    await ap.getByRole("radio", { name: /Let them share their referral link/ }).check();
    await expect(ap.getByLabel("Button text")).toHaveValue("Share with a friend"); // filled in for them
    await expect(ap.getByLabel("Where the button goes")).toHaveCount(0); // a share button needs no address
    await expect(ap.getByRole("complementary", { name: "Preview" })).toContainText("Share with a friend");
    await ap.getByRole("button", { name: "Review and publish" }).click();
    await ap.getByRole("button", { name: "Publish", exact: true }).click();
    await expect(ap.getByText("We launch publicly on December 1")).toBeVisible();
  } finally { await admin.close(); }
  try {
    const a = await customer(browser, { width: 390, height: 800 });
    await a.ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: "http://localhost:5173" });
    await a.page.goto("/dashboard");
    const popup = a.page.getByRole("dialog", { name: "We launch publicly on December 1" });
    await expect(popup).toBeVisible();
    await popup.getByRole("button", { name: "Share with a friend" }).click();
    const link = popup.getByLabel("Your referral link");
    await expect(link).toHaveValue(/signup\?ref=/); // their own personal link
    await shot(a.page, "6-share-panel-phone");
    for (const name of ["WhatsApp", "X", "LinkedIn", "Facebook", "Email", "Copy link"]) await expect(popup.getByRole("button", { name, exact: true })).toBeVisible();
    await a.page.evaluate(() => { (window as unknown as { opened: string[] }).opened = []; window.open = (u) => { (window as unknown as { opened: string[] }).opened.push(String(u)); return null; }; }); // (no real social sites in a test: note where each button would go)
    await popup.getByRole("button", { name: "WhatsApp" }).click();
    await popup.getByRole("button", { name: "LinkedIn" }).click();
    const opened = await a.page.evaluate(() => (window as unknown as { opened: string[] }).opened);
    expect(opened[0]).toMatch(/^https:\/\/wa\.me\//); expect(decodeURIComponent(opened[0])).toContain(await link.inputValue()); // the message that opens in WhatsApp carries their link
    expect(opened[1]).toContain("linkedin.com/sharing"); expect(decodeURIComponent(opened[1])).toContain(await link.inputValue());
    await popup.getByRole("button", { name: "Copy link" }).click();
    await expect(popup.getByText("Your link is copied")).toBeVisible();
    expect(await a.page.evaluate(() => navigator.clipboard.readText())).toBe(await link.inputValue());
    await popup.getByRole("button", { name: "Done" }).click();
    await expect(popup).toHaveCount(0);
    await a.ctx.close();
  } finally { await endAll(request); }
});

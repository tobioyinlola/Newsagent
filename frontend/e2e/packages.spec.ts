import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };

test("the distribution page shows the media packages with their prices, slots and quotes", async ({ page }) => {
  await page.goto("/press-distribution");
  const section = page.locator("#packages");
  await expect(section.getByRole("heading", { name: "Ready-made packages, one price." })).toBeVisible();
  await expect(section.getByRole("tab", { name: /Black Friday & Cyber Monday/ })).toBeVisible();
  const deal = section.getByRole("article", { name: "The International Founder Visibility Deal" });
  await expect(deal).toContainText("US$995");
  await expect(deal).toContainText("US$1,495"); // the usual price
  await expect(deal).toContainText("33% off");
  await expect(deal).toContainText(/of 10 slots left/);
  await section.getByRole("tab", { name: "Nigeria & West Africa" }).click();
  const launch = section.getByRole("article", { name: "The Nigeria Startup Launch Package" });
  await expect(launch).toContainText("US$651.57");
  await expect(launch).toContainText("₦912,203.49");
  await expect(launch).toContainText("Techpoint Africa");
  await section.getByRole("tab", { name: "Middle East" }).click();
  await expect(section.getByRole("article", { name: "The Middle East Startup Entry Package" }).getByRole("link", { name: "Get a quote" })).toHaveAttribute("href", /^mailto:/); // no dollar price yet
  await section.getByRole("tab", { name: "Organisations" }).click();
  await expect(section.getByRole("article", { name: "The Corporate Visibility Partnership" })).toContainText("US$10,000");
});

test("a visitor who chooses a package is sent to sign up, and a customer buys it from the wallet, taking a slot", async ({ page, request }) => {
  const list = async () => (await (await request.get(`${API}/v1/public/distribution/packages`)).json()).packages as { id: string; slug: string; slots_left: number | null; credits: string }[];
  const deal = (await list()).find((p) => p.slug === "bf-startup-visibility-deal")!;
  const left = deal.slots_left!;
  await page.goto("/press-distribution");
  await page.locator("#packages").getByRole("button", { name: "Choose this package: The Startup Visibility Deal" }).click();
  await expect(page).toHaveURL(/\/signup/);

  const email = `packages${Date.now()}@example.com`;
  const invited = await (await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: "Package Test", credits: "400", spend_cap: "1000" } })).json();
  await request.post(`${API}/v1/auth/signup/start`, { data: { accepted_terms: true, invite_code: invited.code, password: "correct horse battery" } });
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  const signup = await (await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: invited.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } })).json();
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), signup.token);
  await page.goto(`/distribution/request?package=${deal.id}`);
  await expect(page.getByText("You chose The Startup Visibility Deal")).toBeVisible();
  await page.getByRole("button", { name: "Start a distribution request" }).click();
  await expect(page.getByRole("heading", { name: "Your package" })).toBeVisible();
  await expect(page.getByText("The Startup Visibility Deal").first()).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Headline").fill("Acme launches in Lagos");
  await page.getByLabel("Press announcement").fill("Acme has launched a new logistics service for Nigerian businesses.");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Contact name").fill("Ada");
  await page.getByLabel("Contact email").fill("ada@example.com");
  await page.getByLabel("Primary phone number", { exact: true }).fill("+2348031234567");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("list", { name: "Distribution cost breakdown" })).toContainText("The Startup Visibility Deal");
  await page.getByRole("button", { name: "Pay and submit" }).click();
  await expect(page.getByRole("dialog", { name: "Distribution submitted" })).toBeVisible();
  expect(Number((await (await request.get(`${API}/v1/me`, { headers: { Authorization: `Bearer ${signup.token}` } })).json()).credit_balance)).toBeCloseTo(400 - Number(deal.credits), 1);
  expect((await list()).find((p) => p.slug === "bf-startup-visibility-deal")!.slots_left).toBe(left - 1);
});

test("an operator can add a package and change anything about one", async ({ browser, request }) => {
  const ap = await (await browser.newContext()).newPage();
  await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await ap.goto("/admin/distribution");
  await ap.getByRole("button", { name: "Packages", exact: true }).click();
  const all = async () => (await (await request.get(`${API}/v1/admin/distribution-packages`, { headers: OPS })).json()).packages as { id: string; slug: string; state: string; slots_left: number; name: string; outlets: string[]; held: string[]; includes: string[]; local_prices: Record<string, string> }[];

  // change the price, slots and wording of one that had no dollar price
  await ap.getByRole("button", { name: "Edit The Middle East Startup Entry Package" }).click();
  await ap.getByLabel("Price in USD for The Middle East Startup Entry Package").fill("495.70");
  await ap.getByLabel("Slots for The Middle East Startup Entry Package").fill("7");
  await ap.getByLabel("Note for The Middle East Startup Entry Package").fill("Limited this month.");
  await ap.getByRole("button", { name: "Save changes" }).click();
  await expect.poll(async () => (await all()).find((p) => p.slug === "middle-east-startup-entry")).toMatchObject({ state: "open", slots_left: 7 });

  // add a brand new package, with outlets, extras and a local price
  await ap.getByRole("button", { name: "Add a package" }).click();
  await ap.getByLabel("Name of new package").fill("Kenya Startup Spotlight");
  await ap.getByLabel("Price in USD for new package").fill("250");
  await ap.getByLabel("Outlets of new package").fill("Techbullion.com\nTech Cabal\nA Paper We Do Not Hold");
  await ap.getByLabel("Includes of new package").fill("A coverage report");
  await ap.getByLabel("Local prices of new package").fill("KES 32,000");
  await ap.getByRole("button", { name: "Add package" }).click();
  await expect(ap.getByText("Kenya Startup Spotlight")).toBeVisible();
  const made = (await all()).find((p) => p.slug === "kenya-startup-spotlight")!;
  expect(made).toMatchObject({ state: "open", includes: ["A coverage report"], local_prices: { KES: "32000" } });
  expect(made.outlets).toHaveLength(3);
  expect(made.held.sort()).toEqual(["Tech Cabal", "TechBullion"]); // the third is arranged by the team
  const pub = (await (await request.get(`${API}/v1/public/distribution/packages`)).json()).packages as { slug: string }[];
  expect(pub.some((p) => p.slug === "kenya-startup-spotlight")).toBe(true);

  // switch it off: customers no longer see it
  await ap.getByRole("listitem").filter({ hasText: "Kenya Startup Spotlight" }).getByRole("button", { name: "Switch off" }).click();
  await expect.poll(async () => ((await (await request.get(`${API}/v1/public/distribution/packages`)).json()).packages as { slug: string }[]).some((p) => p.slug === "kenya-startup-spotlight")).toBe(false);
  await request.patch(`${API}/v1/admin/distribution-packages/${(await all()).find((p) => p.slug === "middle-east-startup-entry")!.id}`, { headers: OPS, data: { clear_price: true, clear_slots: true, note: "" } }); // leave it as it was
});

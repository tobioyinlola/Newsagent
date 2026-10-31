import { expect, test } from "@playwright/test";

// Full pilot journey against the real API with mocked vendors: operator invites a startup, the startup
// signs up with a password and an emailed code, sets a brand kit, writes and approves a script (claims enforced), gets a video, and shares it.
test("invite to shared video", async ({ page, browser }) => {
  // --- operator prep: the back office is a separate app (see admin/), so the budgets and the invite are made through the API here
  const API = "http://localhost:8000";
  const OPS = { Authorization: "Bearer dev:ops@example.com" };
  for (const vendor of ["mock", "renderer"]) expect((await page.request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "100" } })).ok()).toBeTruthy();
  const inv = await (await page.request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email: "founder@startup.example.com", workspace_name: "Acme Farms", credits: "25", spend_cap: "100" } })).json();
  const inviteLink = `http://localhost:5173/login?invite=${inv.code}`;

  // --- startup founder signs up: invite link, a password, then a code sent to the invited address
  const founder = await browser.newContext();
  const fp = await founder.newPage();
  await fp.goto(inviteLink.replace(/^https?:\/\/[^/]+/, "http://localhost:5173"));
  await expect(fp.getByRole("heading", { name: "Create your workspace" })).toBeVisible();
  await expect(fp.getByText("Acme Farms")).toBeVisible();
  await fp.getByLabel("Password", { exact: true }).fill("correct horse battery");
  await fp.getByLabel("Confirm password", { exact: true }).fill("correct horse battery");
  await fp.getByRole("button", { name: "Continue" }).click();
  await expect(fp.getByLabel("6-digit code")).toBeVisible();
  const mail = await (await fp.request.get("http://localhost:8000/v1/dev/last-email", { params: { to: "founder@startup.example.com" } })).json();
  await fp.getByLabel("6-digit code").fill(/\b(\d{6})\b/.exec(mail.text)![1]);
  await fp.getByRole("button", { name: "Verify and create workspace" }).click();

  // --- signing up lands on the dashboard; then the brand kit
  await expect(fp.getByRole("heading", { name: "Welcome, Acme Farms" })).toBeVisible();
  await fp.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Brand kit" }).click();
  await fp.getByLabel("Accent color", { exact: true }).fill("#00AA66");
  // logo upload: verified, scanned, then usable; malware is refused
  const png = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(64)]);
  await fp.getByLabel("Logo for dark backgrounds").setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: png });
  await expect(fp.getByText("Uploaded and checked: logo light.")).toBeVisible();
  await expect(fp.getByText("in use")).toBeVisible();
  const eicar = "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*";
  await fp.getByLabel("Brand guide (PDF, optional)").setInputFiles({ name: "guide.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n" + eicar) });
  await expect(fp.getByRole("alert")).toContainText("blocked by our security scan");
  await fp.getByRole("button", { name: "Add a word" }).click();
  await fp.getByLabel("Word 1", { exact: true }).fill("Oyinlola");
  await fp.getByLabel("Pronounced 1", { exact: true }).fill("oh-yin-LOH-lah");
  await fp.getByRole("button", { name: "Save brand kit" }).click();
  await expect(fp.getByText("Saved as version 2.")).toBeVisible();

  // --- brief -> script
  await fp.getByRole("link", { name: "Videos" }).click();
  await fp.getByRole("link", { name: "New video" }).click();
  await fp.goto("/ai-newsroom/new-classic"); // the original script-first journey; the guided one has its own test
  await fp.getByLabel("Paste your announcement or news script").fill("Acme Farms helps farmers sell produce online. We have 5,000 users and we are the first of our kind in Ghana.");
  await fp.getByLabel("Your name").fill("Ada Obi");
  await fp.getByRole("button", { name: "Read it and write my script" }).click();
  await expect(fp.getByRole("heading", { name: /Script \(version 1\)/ })).toBeVisible();

  // the owner adds a claim to what the anchor will say; it must be confirmed before anything is rendered
  await fp.getByLabel("Intro").fill("Tonight we feature Acme Farms. They have 5,000 users and are the first in Ghana.");
  await fp.getByLabel("No interview").check(); // this journey is the presenter-only video; the interview has its own test
  await fp.getByRole("button", { name: "Approve and make my video" }).click();
  await expect(fp.getByRole("alert")).toContainText(/Please confirm the .*flagged claim/);
  await expect(fp.getByRole("group", { name: "Confirm these claims are accurate" })).toBeVisible();
  for (const box of await fp.getByRole("group", { name: "Confirm these claims are accurate" }).getByRole("checkbox").all()) await box.check();
  await fp.getByRole("button", { name: "Approve and make my video" }).click();

  // --- render completes (mock vendors), live status
  await expect(fp.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(fp.getByText("AI-generated anchor").first()).toBeVisible();
  await expect(fp.getByRole("link", { name: "Download" })).toHaveCount(4); // widescreen HD, widescreen light, thumbnail, captions (vertical only with RENDER_VERTICAL)
  await expect(fp.getByRole("heading", { name: "Suggested captions" })).toBeVisible();
  await expect(fp.locator("pre").first()).toContainText("AI-generated anchor");

  // --- the original script-first video has no written story, so there is nothing to publish on Latest Stories
  await expect(fp.getByRole("heading", { name: "Your story on Cover Founder" })).toBeVisible();
  await expect(fp.getByText("has no written story")).toBeVisible();

  // --- customers can't delete videos (only the back office can)
  await expect(fp.getByRole("button", { name: "Delete video" })).toHaveCount(0);
});

test("a wrong password gets one generic message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("stranger@example.com");
  await page.getByLabel("Password", { exact: true }).fill("not the password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("don't match");
  await expect(page).toHaveURL(/\/login/);
});

test("sign up with a password, verify the emailed code, sign out, sign back in, and mismatched passwords are caught", async ({ page, request }) => {
  const API = "http://localhost:8000";
  const email = `pw${Date.now()}@startup.example.com`;
  const pw = "correct horse battery";
  const OPS = { Authorization: "Bearer dev:ops@example.com" };
  const inv = await (await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: "Password Co", credits: "1" } })).json();

  await page.goto(`/login?invite=${inv.code}`);
  await page.getByLabel("Password", { exact: true }).fill(pw);
  await page.getByLabel("Confirm password", { exact: true }).fill(pw + "x");
  await expect(page.getByText("The passwords don’t match.")).toBeVisible();
  await page.getByLabel("Confirm password", { exact: true }).fill(pw);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByLabel("6-digit code")).toBeVisible();
  await page.getByLabel("6-digit code").fill("000000");
  await page.getByRole("button", { name: "Verify and create workspace" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  await page.getByLabel("6-digit code").fill(/\b(\d{6})\b/.exec(mail.text)![1]);
  await page.getByRole("button", { name: "Verify and create workspace" }).click();
  await expect(page.getByRole("heading", { name: /^Welcome, / })).toBeVisible(); // straight to the dashboard

  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Sign out" }).click(); // the confirmation
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(pw);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("link", { name: "Videos" })).toBeVisible();
});

test("an expired session sends you back to sign in", async ({ page }) => {
  await page.addInitScript(() => { if (!sessionStorage.getItem("seeded")) { sessionStorage.setItem("seeded", "1"); localStorage.setItem("newsagent.token", "nas_expired-or-revoked"); } });
  await page.goto("/ai-newsroom/videos");
  await expect(page).toHaveURL(/\/login\?expired=1/);
  await expect(page.getByText(/after an hour without activity/)).toBeVisible();
});

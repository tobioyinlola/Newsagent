import { expect, test } from "@playwright/test";

// Full pilot journey against the real API with mocked vendors: operator invites a startup, the startup
// redeems, sets a brand kit, writes and approves a script (claims enforced), gets a video, and shares it.
test("invite to shared video", async ({ page, browser }) => {
  // --- operator
  await page.goto("/login");
  await page.getByLabel("Email").fill("ops@example.com");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("link", { name: "Admin" }).click();
  for (const vendor of ["mock", "renderer"]) {
    await page.getByLabel("Vendor").selectOption(vendor);
    await page.getByLabel("Monthly limit").fill("100");
    await page.getByRole("button", { name: "Set budget" }).click();
    await expect(page.getByRole("cell", { name: vendor, exact: true })).toBeVisible();
  }
  await page.getByLabel("Invitee email").fill("founder@startup.example.com");
  await page.getByLabel("Startup name").fill("Acme Farms");
  await page.getByRole("button", { name: "Create invite" }).click();
  const inviteLink = await page.locator("code").innerText();
  expect(inviteLink).toContain("/login?invite=");

  // --- startup founder redeems the invite
  const founder = await browser.newContext();
  const fp = await founder.newPage();
  await fp.goto(inviteLink.replace(/^https?:\/\/[^/]+/, "http://localhost:5173"));
  await fp.getByLabel("Email").fill("founder@startup.example.com");
  await fp.getByRole("button", { name: "Continue" }).click();
  await expect(fp.getByRole("heading", { name: "Redeem your invite" })).toBeVisible();
  await fp.getByRole("button", { name: "Create my workspace" }).click();

  // --- brand kit
  await expect(fp.getByRole("heading", { name: /Brand kit/ })).toBeVisible();
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
  await fp.getByLabel("Tell us about your startup").fill("Acme Farms helps farmers sell produce online. We have 5,000 users and we are the first of our kind in Ghana.");
  await fp.getByRole("button", { name: "Write my script" }).click();
  await expect(fp.getByRole("heading", { name: /Script \(version 1\)/ })).toBeVisible();

  // the owner adds a claim to what the anchor will say; it must be confirmed before anything is rendered
  await fp.getByLabel("Intro").fill("Tonight we feature Acme Farms. They have 5,000 users and are the first in Ghana.");
  await fp.getByRole("button", { name: "Approve and make my video" }).click();
  await expect(fp.getByRole("alert")).toContainText("confirm each flagged claim");
  await expect(fp.getByRole("group", { name: "Confirm these claims are accurate" })).toBeVisible();
  for (const box of await fp.getByRole("checkbox").all()) await box.check();
  await fp.getByRole("button", { name: "Approve and make my video" }).click();

  // --- render completes (mock vendors), live status
  await expect(fp.getByRole("heading", { name: "Your video" })).toBeVisible({ timeout: 60_000 });
  await expect(fp.getByText("AI-generated anchor").first()).toBeVisible();
  await expect(fp.getByRole("link", { name: "Download" })).toHaveCount(4);
  await expect(fp.getByRole("heading", { name: "Suggested captions" })).toBeVisible();
  await expect(fp.locator("pre").first()).toContainText("AI-generated anchor");

  // --- share and revoke
  await fp.getByRole("button", { name: "Create share link" }).click();
  const shareUrl = await fp.getByLabel("Share link").inputValue();
  const viewer = await browser.newPage();
  await viewer.goto(shareUrl.replace(/^https?:\/\/[^/]+/, "http://localhost:5173"));
  await expect(viewer.getByRole("heading", { name: "Acme", exact: true })).toBeVisible();
  await expect(viewer.getByText("AI-generated anchor").first()).toBeVisible();
  await fp.getByRole("button", { name: "Revoke all links" }).click();
  await viewer.reload();
  await expect(viewer.getByText("This link is no longer available.")).toBeVisible();

  // --- owner deletes the video; it disappears from the list
  fp.on("dialog", (d) => d.accept());
  await fp.getByRole("button", { name: "Delete video" }).click();
  await expect(fp.getByText("No videos yet.")).toBeVisible();
});

test("uninvited email gets a clear message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("stranger@example.com");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Signup is invite-only")).toBeVisible();
});

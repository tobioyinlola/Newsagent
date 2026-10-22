import { createHmac } from "node:crypto";
import { expect, test } from "@playwright/test";

// Full pilot journey against the real API with mocked vendors: operator invites a startup, the startup
// signs up with an emailed code, sets a brand kit, writes and approves a script (claims enforced), gets a video, and shares it.
test("invite to shared video", async ({ page, browser }) => {
  // --- operator
  // operators normally enrol an authenticator; `dev:` tokens (local only) skip that so the suite can drive the console
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:ops@example.com"));
  await page.goto("/projects");
  await page.getByRole("link", { name: "Admin" }).click();
  await page.getByRole("tab", { name: "Setup" }).click();
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

  // --- startup founder signs up: invite link, then a code sent to the invited address
  const founder = await browser.newContext();
  const fp = await founder.newPage();
  await fp.goto(inviteLink.replace(/^https?:\/\/[^/]+/, "http://localhost:5173"));
  await expect(fp.getByRole("heading", { name: "Create your workspace" })).toBeVisible();
  await expect(fp.getByText("Acme Farms")).toBeVisible();
  await fp.getByRole("button", { name: "Email me a code" }).click();
  const mail = await (await fp.request.get("http://localhost:8000/v1/dev/last-email", { params: { to: "founder@startup.example.com" } })).json();
  await fp.getByLabel("Sign-in code").fill(/\b(\d{6})\b/.exec(mail.text)![1]);
  await fp.getByRole("button", { name: "Sign in" }).click();

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
  for (const box of await fp.getByRole("group", { name: "Confirm these claims are accurate" }).getByRole("checkbox").all()) await box.check();
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

test("sign-in never reveals whether an email has an account", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("stranger@example.com");
  await page.getByRole("button", { name: "Email me a code" }).click();
  await expect(page.getByText(/If stranger@example.com can sign in/)).toBeVisible();
  await page.getByLabel("Sign-in code").fill("123456");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

function totp(secret: string, stepOffset = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/=+$/, "")) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000) + stepOffset));
  const h = createHmac("sha1", key).update(msg).digest();
  const o = h[h.length - 1] & 15;
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

test("a user turns on an authenticator, then signing in needs the code", async ({ page, request }) => {
  const API = "http://localhost:8000";
  const email = `mfa${Date.now()}@startup.example.com`;
  const OPS = { Authorization: "Bearer dev:ops@example.com" };
  const inv = await (await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: "MFA Co", credits: "1" } })).json();
  const codeFor = async () => /\b(\d{6})\b/.exec((await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json()).text)![1];

  await page.goto(`/login?invite=${inv.code}`);
  await page.getByRole("button", { name: "Email me a code" }).click();
  await expect(page.getByLabel("Sign-in code")).toBeVisible();
  await page.getByLabel("Sign-in code").fill(await codeFor());
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Security" }).click();
  await page.getByRole("button", { name: "Set up" }).click();
  const secret = (await page.locator("code").innerText()).trim();
  await page.getByLabel("Authenticator code").fill(totp(secret));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByText(/Save these recovery codes/)).toBeVisible();

  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Sign out" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Email me a code" }).click();
  await expect(page.getByLabel("Sign-in code")).toBeVisible();
  await page.getByLabel("Sign-in code").fill(await codeFor());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Two-step verification" })).toBeVisible();
  await page.getByLabel("Authenticator code").fill(totp(secret, 1));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("link", { name: "Videos" })).toBeVisible();
});

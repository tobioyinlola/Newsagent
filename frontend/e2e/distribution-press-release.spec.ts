import { type APIRequestContext, expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function customer(request: APIRequestContext, name: string) {
  const email = `pr${Date.now()}${Math.floor(Math.random() * 1000)}@example.com`;
  const invited = await (await request.post(`${API}/v1/admin/invites`, { headers: OPS, data: { email, workspace_name: name, credits: "250", spend_cap: "100" } })).json();
  await request.post(`${API}/v1/auth/signup/start`, { data: { accepted_terms: true, invite_code: invited.code, password: "correct horse battery" } });
  const mail = await (await request.get(`${API}/v1/dev/last-email`, { params: { to: email } })).json();
  const signup = await (await request.post(`${API}/v1/auth/signup/verify`, { data: { invite_code: invited.code, code: /\b(\d{6})\b/.exec(mail.text)![1] } })).json();
  return { email, token: signup.token as string, headers: { Authorization: `Bearer ${signup.token}` } };
}

test("distribution without a video: details, a press release written for you, edits, pictures, then the usual funnel", async ({ page, request }) => {
  const c = await customer(request, "Press Release Co");
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), c.token);
  await page.goto("/distribution/request");

  // a direct way in, with no video: three ways to start
  await expect(page.getByRole("heading", { name: "How do you want to start?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start a distribution request" })).toBeVisible(); // the video route is still there
  await page.getByRole("button", { name: "Write my press release" }).first().click();

  // the same details a video starts with
  await expect(page.getByRole("heading", { name: "Tell us about your announcement" })).toBeVisible();
  const write = page.getByRole("button", { name: "Write my press release" });
  await expect(write).toBeDisabled();
  await page.getByRole("radio", { name: /Funding round/ }).click();
  await page.getByLabel("Tell us the key details").fill("Press Release Co raised a seed round to help small shops in Kumasi sell online and get paid by phone.");
  await page.getByLabel("First name").fill("Ada");
  await page.getByLabel("Last name").fill("Obi");
  await page.getByLabel("Role", { exact: true }).fill("ceo");
  await expect(page.getByLabel("Role", { exact: true })).toHaveValue("CEO");
  await page.getByLabel("Company name").fill("press release co");
  await page.getByLabel("City", { exact: true }).fill("Kumasi");
  await page.getByLabel("Country", { exact: true }).fill("Ghana");
  await write.click();

  // the press release arrives, ready to edit
  await expect(page.getByRole("heading", { name: "Your press release" })).toBeVisible({ timeout: 30_000 });
  const headline = page.getByLabel("Headline");
  const body = page.getByLabel("Press release", { exact: true });
  await expect(headline).not.toHaveValue("");
  await expect(body).toHaveValue(/^KUMASI, GHANA — /);
  await headline.fill("Press Release Co raises a seed round for Kumasi shops");
  await body.fill(`${await body.inputValue()}\n\nA closing line added by the founder.`);
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  // pictures are asked for
  await expect(page.getByRole("heading", { name: "Add pictures for your press release" })).toBeVisible();
  await page.getByLabel("Add a picture").setInputFiles({ name: "shop.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByText("1 picture added.")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Continue to choose outlets" }).click();

  // and the usual funnel takes over at the outlets
  await expect(page).toHaveURL(/distribution\/request\?draft=/);
  await page.getByRole("checkbox", { name: /^Tribune / }).check();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Choose your video and announcement" })).toBeVisible();
  await expect(page.getByLabel("Video (optional)")).toHaveValue("");
  await expect(page.getByLabel("Headline", { exact: true })).toHaveValue("Press Release Co raises a seed round for Kumasi shops");
  await expect(page.getByLabel("Press announcement", { exact: true })).toHaveValue(/A closing line added by the founder\.$/);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Contact name", { exact: true }).fill("Ada Obi");
  await page.getByLabel("Contact email", { exact: true }).fill(c.email);
  await page.getByLabel("Primary phone number", { exact: true }).fill("+2348031234567");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review your distribution request" })).toBeVisible();
  await page.getByRole("button", { name: "Pay and submit" }).click();
  await expect(page.getByRole("dialog", { name: "Distribution submitted" })).toBeVisible();

  const rows = (await (await request.get(`${API}/v1/distribution`, { headers: c.headers })).json()) as { paid: boolean; data: { headline: string; project_id: string | null; picture_keys: string[]; announcement_source: string } }[];
  const sent = rows.find((r) => r.paid);
  expect(sent?.data.headline).toBe("Press Release Co raises a seed round for Kumasi shops");
  expect(sent?.data.project_id).toBeNull();
  expect(sent?.data.picture_keys).toHaveLength(1);
  expect(sent?.data.announcement_source).toBe("custom");
});

test("distribution without a video: upload a press release, or paste it", async ({ page, request }) => {
  const c = await customer(request, "Upload Co");
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), c.token);
  await page.goto("/distribution/request");
  await page.getByRole("button", { name: "Upload my press release" }).click();

  // a file that can't be read says why, and nothing is lost
  await page.getByLabel("Press release file").setInputFiles({ name: "release.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
  await expect(page.getByRole("alert")).toContainText("Upload a Word (.docx), PDF, text (.txt) or Markdown (.md) file.");

  const text = "FOR IMMEDIATE RELEASE\n\nUpload Co opens in Accra\n\nACCRA, GHANA — Upload Co today opened its first office.\n\nIt will hire ten people.";
  await page.getByLabel("Press release file").setInputFiles({ name: "release.txt", mimeType: "text/plain", buffer: Buffer.from(text) });
  await expect(page.getByRole("heading", { name: "Your press release" })).toBeVisible();
  await expect(page.getByLabel("Headline")).toHaveValue("Upload Co opens in Accra");
  await expect(page.getByLabel("Press release", { exact: true })).toHaveValue(/^ACCRA, GHANA — Upload Co today opened its first office\.\n\nIt will hire ten people\.$/);
  await expect(page.getByRole("button", { name: "Write it again" })).toHaveCount(0); // that is only for one we wrote

  // it can be edited, and the pictures step can be skipped
  await page.getByLabel("Headline").fill("Upload Co opens its Accra office");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Add pictures for your press release" })).toBeVisible();
  await page.getByRole("button", { name: "Skip pictures and choose outlets" }).click();
  await expect(page).toHaveURL(/distribution\/request\?draft=/);
  const drafts = (await (await request.get(`${API}/v1/distribution`, { headers: c.headers })).json()) as { stage: string; data: { headline: string; picture_keys: string[] } }[];
  expect(drafts[0].data.headline).toBe("Upload Co opens its Accra office");
  expect(drafts[0].data.picture_keys).toEqual([]);
});

test("pasting a press release instead of uploading one", async ({ page, request }) => {
  const c = await customer(request, "Paste Co");
  await page.addInitScript((t) => localStorage.setItem("newsagent.token", t), c.token);
  await page.goto("/distribution/request");
  await page.getByRole("button", { name: "Upload my press release" }).click();
  await page.getByRole("button", { name: "Paste the text instead" }).click();
  await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeDisabled(); // nothing to send yet
  await page.getByLabel("Headline").fill("Paste Co launches");
  await page.getByLabel("Press release", { exact: true }).fill("Paste Co launched its app today.");
  await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeEnabled();
});

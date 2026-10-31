import { expect, test, type APIRequestContext } from "@playwright/test";
const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };

async function completedProject(request: APIRequestContext) {
  for (const vendor of ["mock", "renderer"]) await request.put(`${API}/v1/admin/vendor-budgets`, { headers: OPS, data: { vendor, limit: "1000" } });
  const project = await (await request.post(`${API}/v1/projects`, { headers: OPS, data: { brief_text: "Acme helps farmers sell fresh produce to businesses in Lagos." } })).json();
  const script = await (await request.post(`${API}/v1/projects/${project.id}/script/generate`, { headers: OPS })).json();
  await request.put(`${API}/v1/projects/${project.id}/script`, { headers: OPS, data: { segments: [{ kind: "intro", text: "Acme helps farmers sell produce." }], ticker_lines: script.ticker_lines, lower_thirds: script.lower_thirds, interview_questions: script.interview_questions } });
  const approved = await request.post(`${API}/v1/projects/${project.id}/script/approve`, { headers: OPS });
  expect(approved.ok()).toBeTruthy();
  await expect.poll(async () => (await (await request.get(`${API}/v1/projects/${project.id}`, { headers: OPS })).json()).state).toBe("final_ready");
  return (await request.get(`${API}/v1/projects/${project.id}`, { headers: OPS })).json();
}

test("closed event stream cannot leave a finished video on the creating step; existing project reopens Ready", async ({ page, request }) => {
  const project = await completedProject(request); let ready = false;
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:ops@example.com"));
  await page.route(`**/v1/projects/${project.id}`, route => route.fulfill({ json: { ...project, state: ready ? "final_ready" : "merging" } }));
  await page.route(`**/v1/projects/${project.id}/events`, route => route.fulfill({ body: "", contentType: "text/event-stream" }));
  // 100% alone is not enough: the confirmed project state must be final_ready.
  await page.route(`**/v1/projects/${project.id}/progress`, route => route.fulfill({ json: { state: "merging", percent: 100, stages: [], queue_ahead: 0, cancellable: false, retryable: false } }));
  await page.goto(`/ai-newsroom/${project.id}`);
  await expect(page.getByRole("heading", { name: "Progress: 100%" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toHaveCount(0);
  ready = true;
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByRole("navigation", { name: "Progress", exact: true }).locator('[aria-current="step"]')).toContainText("Ready");
  await expect(page.getByRole("heading", { name: "Progress: 100%" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible();
  const distribution = page.getByRole("region", { name: "Media outlet logos" });
  await expect(distribution.getByRole("img").first()).toBeVisible();
  expect(await distribution.getByRole("img").first().evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(distribution.getByRole("button")).toHaveCount(0);
  await expect(distribution.locator("ul").first()).toHaveCSS("animation-play-state", "running");
  await page.setViewportSize({ width: 1440, height: 1000 });
  const section = page.locator('section[aria-labelledby="ready-distribution-heading"]');
  await section.screenshot({ path: "/tmp/ready-distribution-desktop.png", animations: "disabled" });
  await page.screenshot({ path: "/tmp/ready-full-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await section.screenshot({ path: "/tmp/ready-distribution-mobile.png", animations: "disabled" });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(distribution.locator("ul").first()).toHaveCSS("animation-name", "none");
});

test("completed progress refreshes the parent project immediately without an event", async ({ page, request }) => {
  const project = await completedProject(request); let refreshed = false;
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:ops@example.com"));
  await page.route(`**/v1/projects/${project.id}`, route => route.fulfill({ json: { ...project, state: refreshed ? "final_ready" : "merging" } }));
  await page.route(`**/v1/projects/${project.id}/events`, route => route.abort());
  await page.route(`**/v1/projects/${project.id}/progress`, route => { refreshed = true; return route.fulfill({ json: { state: "final_ready", percent: 100, stages: [], queue_ahead: 0, cancellable: false, retryable: false } }); });
  await page.goto(`/ai-newsroom/${project.id}`);
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible({ timeout: 4000 });
  await expect(page.getByRole("link", { name: "Choose distribution outlets" })).toHaveAttribute("href", `/distribution/request?project=${project.id}`);
});

import { expect, test } from "@playwright/test";

const id = "a".repeat(32), image = "b".repeat(32);
const article = "This technology development is being reported by the original publisher and reviewed by Cover Founder News. ".repeat(14).trim();
const script = "This is a concise technology report with information attributed to the original source. ".repeat(6).trim();

test("admin sign-in uses the team portal and the refreshed layout", async ({ page }) => {
  let portal = "";
  await page.route("**/v1/auth/login", async route => { portal = route.request().postDataJSON().portal; await route.fulfill({ status: 403, json: { detail: "This is a customer account. Please sign in on the main site." } }); });
  await page.goto("/admin/login");
  await expect(page.getByRole("navigation", { name: "Back office public navigation" })).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill("customer@example.com");
  await page.getByLabel("Password", { exact: true }).fill("A password for a customer");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText(/This is a customer account/)).toBeVisible();
  expect(portal).toBe("admin");
  await page.screenshot({ path: "/tmp/cf-admin-signin-updated.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("News Desk requires short copy, explicit cover and a separate video job", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "test"));
  let current = { id, slug: "tech-story", status: "draft", revision: 1, updated_by: "editor@example.com", updated_at: "2026-10-31T09:00:00Z", published_at: null, data: { source_name: "Example publisher", source_url: "https://example.com/story", source_text: "A source article for editorial review.", headline: "A technology update for growing businesses", summary: "A concise introduction to the latest technology story.", body: article, presenter_script: script, cover_image_id: null as string | null, pictures: [{ id: image, caption: "Editorial cover", credit: "Example photographer" }], scenes: [] }, images: [{ id: image, url: "/newsroom-hero.webp", filename: "cover.webp" }], video: null as null | { id: string; status: string; progress: number; revision: number; matches_draft: boolean; url: null; error: string; duration_s: null } };
  let videoRequests = 0;
  await page.route("**/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/me") return route.fulfill({ json: { email: "editor@example.com", workspace_name: "Editorial", workspace_id: "workspace", is_operator: true, is_owner: false, staff_role: "Content", permissions: ["overview.view", "customers.view", "review.manage"], credit_balance: "0" } });
    if (path === "/v1/admin/news-desk") return route.fulfill({ json: [{ id, headline: current.data.headline, status: current.status, updated_at: current.updated_at }] });
    if (path.endsWith("/generate-video")) { videoRequests++; current = { ...current, video: { id: "video", status: "queued", progress: 0, revision: current.revision, matches_draft: true, url: null, error: "", duration_s: null } }; return route.fulfill({ json: current }); }
    if (path === `/v1/admin/news-desk/${id}`) { if (route.request().method() === "PUT") current = { ...current, data: route.request().postDataJSON(), revision: current.revision + 1 }; return route.fulfill({ json: current }); }
    if (path === "/v1/admin/overview") return route.fulfill({ json: { attention: { pending_reviews: 0, failed_videos: 0 } } });
    return route.fulfill({ json: {} });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/admin/news-desk");
  await page.getByRole("button", { name: /A technology update for growing businesses/ }).click();
  const generate = page.getByRole("button", { name: "Generate breaking-news video", exact: true });
  await expect(generate).toBeDisabled();
  await page.getByRole("button", { name: "Use as cover", exact: true }).click();
  await expect(generate).toBeEnabled();
  await page.getByLabel("Written story", { exact: true }).fill("word ".repeat(199));
  await expect(generate).toBeDisabled();
  await page.getByLabel("Written story", { exact: true }).fill("word ".repeat(300));
  await expect(generate).toBeEnabled();
  await page.getByLabel("Presenter script", { exact: true }).fill("word ".repeat(96));
  await expect(generate).toBeDisabled();
  await page.getByLabel("Presenter script", { exact: true }).fill(script);
  await generate.click();
  await expect.poll(() => videoRequests).toBe(1);
  await expect(page.getByText("Video: queued · 0%")).toBeVisible();
  await expect(generate).toBeDisabled();
  await page.getByRole("heading", { name: "News Desk", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/tmp/cf-news-desk-updated.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("ready projects show the distribution prompt once and preserve the video", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "test"));
  await page.route("**/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/me") return route.fulfill({ json: { email: "customer@example.com", workspace_name: "Acme", workspace_id: "workspace", is_operator: false, credit_balance: "25" } });
    if (path === "/v1/projects/ready") return route.fulfill({ json: { id: "ready", state: "final_ready", flow: "classic", interview_enabled: false, created_at: "2026-10-31T09:00:00Z" } });
    if (path.endsWith("/costs")) return route.fulfill({ json: { lines: [], total: "0" } });
    if (path.endsWith("/downloads")) return route.fulfill({ json: { items: [], disclosure: "AI-generated presenter" } });
    if (path.endsWith("/publication")) return route.fulfill({ json: { published: false } });
    if (path.endsWith("/captions")) return route.fulfill({ json: { captions: {} } });
    if (path.includes("/outlets")) return route.fulfill({ json: { outlets: [], coming_soon: [], quote_version: "test" } });
    if (path === "/v1/capabilities") return route.fulfill({ json: { demo_mode: false } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/ai-newsroom/ready");
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/cf-ready-distribution-prompt.png" });
  await page.getByRole("button", { name: "Maybe later", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your video", exact: true })).toBeVisible();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await page.evaluate(() => localStorage.removeItem("cf.distribution-ready.workspace.ready"));
  await page.reload();
  await page.getByRole("button", { name: "Yes, choose outlets", exact: true }).click();
  await expect(page).toHaveURL(/distribution\/request\?project=ready$/);
});

test("the admin overview uses the refreshed dashboard and real toolbar shortcuts", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "test"));
  await page.route("**/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/me") return route.fulfill({ json: { email: "ada@example.com", workspace_name: "Cover Founder", workspace_id: "team", is_operator: true, is_owner: true, staff_role: "Owner", credit_balance: "0", permissions: ["overview.view", "customers.view", "operations.view", "finance.view", "review.manage"] } });
    if (path === "/v1/admin/overview") return route.fulfill({ json: { kpis: { customers: 12, active_30d: 8, signups_7d: 3, signups_30d: 6, paying_companies: 4, revenue_usd_30d: "450", revenue_usd_total: "900", videos_30d: 8, videos_ready: 6, videos_total: 12, vendor_cost_usd_30d: "120", credits_outstanding: "400" }, attention: { paused: false, pending_reviews: 2, failed_videos: 1, suspended_workspaces: 0 }, funnel: { invites_sent: 12, accepted: 8, pending: 2, expired: 2 }, signups_by_day: [], revenue_by_day: [], videos_by_state: { final_ready: 6, interviewing: 2 }, recent_signups: [], top_customers: [] } });
    if (path === "/v1/admin/customers") return route.fulfill({ json: { total: 1, items: [{ workspace_id: "acme", company: "Acme", email: "customer@example.com" }] } });
    return route.fulfill({ json: [] });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: /Welcome back, ada/ })).toBeVisible();
  await page.keyboard.press("/");
  await page.getByRole("textbox", { name: "Search the back office" }).fill("Acme");
  await expect(page.getByRole("region", { name: "Back office toolbar panel" }).getByRole("link", { name: /Acme/ })).toHaveAttribute("href", "/admin/customers/acme");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Team notifications" }).click();
  await expect(page.getByRole("link", { name: /Content waiting for review/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("textbox", { name: "Search the back office" }).fill("");
  await page.keyboard.press("Escape");
  await page.getByRole("heading", { name: /Welcome back, ada/ }).click();
  await page.screenshot({ path: "/tmp/cf-admin-overview-updated.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("while a video is being made the distribution pop-up shows once, and shows again when the video is finished", async ({ page }) => {
  let state = "rendering_anchor";
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "test"));
  await page.route("**/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/me") return route.fulfill({ json: { email: "customer@example.com", workspace_name: "Acme", workspace_id: "workspace", is_operator: false, credit_balance: "25" } });
    if (path === "/v1/projects/making/progress") return route.fulfill({ json: { state, percent: state === "final_ready" ? 100 : 45, stages: [{ key: "render", label: "Making your video", status: state === "final_ready" ? "done" : "working" }], retryable: false, cancellable: true, vendor_jobs_in_flight: 0, queue_ahead: 0 } });
    if (path === "/v1/projects/making") return route.fulfill({ json: { id: "making", state, flow: "classic", interview_enabled: false, created_at: "2026-10-31T09:00:00Z" } });
    if (path.endsWith("/costs")) return route.fulfill({ json: { lines: [], total: "0" } });
    if (path.endsWith("/downloads")) return route.fulfill({ json: { items: [], disclosure: "AI-generated presenter" } });
    if (path.endsWith("/publication")) return route.fulfill({ json: { published: false } });
    if (path.endsWith("/captions")) return route.fulfill({ json: { captions: {} } });
    if (path.includes("/outlets")) return route.fulfill({ json: { outlets: [], coming_soon: [], quote_version: "test" } });
    if (path === "/v1/capabilities") return route.fulfill({ json: { demo_mode: false } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/ai-newsroom/making");
  const popup = page.getByRole("alertdialog", { name: "Take your story to over 25,000 media outlets?" });
  await expect(popup).toBeVisible();
  await expect(popup.getByText("Your video is being made.")).toBeVisible();
  await page.screenshot({ path: "/tmp/cf-making-distribution-prompt.png" });
  await popup.getByRole("button", { name: "Not now", exact: true }).click(); // dismissed for this video
  await expect(popup).toHaveCount(0);
  await page.reload();
  await expect(popup).toHaveCount(0);
  state = "final_ready"; // the video finishes: the pop-up comes back, saying it is ready
  await page.reload();
  await expect(popup).toBeVisible();
  await expect(popup.getByText("Your video is ready.")).toBeVisible();
  await popup.getByRole("button", { name: "Yes, choose outlets", exact: true }).click();
  await expect(page).toHaveURL(/distribution\/request\?project=making$/);
});

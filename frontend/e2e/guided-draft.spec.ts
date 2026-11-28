import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";
const H = { Authorization: "Bearer dev:customer@example.com" };
const DETAILS = { brief_text: "Acme Farms raised a seed round to help farmers in Kumasi sell their produce online.\n\nAnnouncement type: Funding round.", founder_name: "Ada Mensah", founder_title: "CEO, Acme", founder_location: "Kumasi, Ghana", flow: "guided", announcement_type: "funding_round", region: "NG", voice_accent: "british" };

// A video whose interview never opened (the writing assistant was busy when the person pressed start) used to open as a blank page.
test("a draft video opens its interview by itself instead of showing a blank page", async ({ page, request }) => {
  const made = await (await request.post(`${API}/v1/projects`, { headers: H, data: DETAILS })).json();
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  await page.goto(`/ai-newsroom/${made.id}`);
  await expect(page.getByText(/Step 2 of 5: AI interview/)).toBeVisible({ timeout: 20000 }); // it opened without a click
});

test("if the interview still cannot open, it says so, nothing is lost, and Try again works", async ({ page, request }) => {
  const made = await (await request.post(`${API}/v1/projects`, { headers: H, data: DETAILS })).json();
  let calls = 0;
  await page.route(new RegExp(`/v1/projects/${made.id}/guided/start$`), (route) => {
    calls++;
    if (calls === 1) return route.fulfill({ status: 503, headers: { "retry-after": "30" }, contentType: "application/json", body: JSON.stringify({ detail: "Our writing assistant is very busy right now. Nothing was lost or charged. Please try again in a minute." }) });
    return route.continue();
  });
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:customer@example.com"));
  await page.goto(`/ai-newsroom/${made.id}`);
  await expect(page.getByText("Our writing assistant is very busy right now")).toBeVisible();
  await expect(page.getByText(/Your details are saved and nothing was charged/)).toBeVisible();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText(/Step 2 of 5: AI interview/)).toBeVisible({ timeout: 20000 });
  expect(calls).toBe(2);
});

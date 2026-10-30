import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
const API = "http://localhost:8000";
const OPS = { Authorization: "Bearer dev:ops@example.com" };

test("public measurement, publisher reports, customer analytics and mobile CSV", async ({ page, request, browser }) => {
  const seeded = JSON.parse(execFileSync(".venv/bin/python", ["-c", `
import asyncio,json
from app.models import Workspace,User,Project,ScriptVersion,Asset,DistributionRequest,DistributionPlacement
from app.models.base import utcnow
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
async def seed():
    engine=create_async_engine('sqlite+aiosqlite:///./e2e.db')
    async with async_sessionmaker(engine,expire_on_commit=False)() as db:
        w=Workspace(name='Audience Browser Test');db.add(w);await db.flush()
        db.add(User(email='audience-browser@example.com',workspace_id=w.id))
        p=Project(workspace_id=w.id,state='final_ready',story_slug='audience-browser-story',published_at=utcnow());db.add(p);await db.flush()
        db.add(ScriptVersion(project_id=p.id,story={'headline':'Audience browser launch','sections':[{'heading':'The story','text':'An announcement for reporting.'}],'social_post':'Launch'}))
        db.add(Asset(project_id=p.id,type='render',format='16x9',storage_key='e2e/audience.mp4',duration=12))
        r=DistributionRequest(workspace_id=w.id,created_by='audience-browser@example.com',paid_at=utcnow(),email_sent_at=utcnow(),status='submitted',data={'project_id':p.id,'headline':'Audience browser launch','contact_email':'audience-browser@example.com'});db.add(r);await db.flush()
        o=DistributionPlacement(request_id=r.id,outlet_id='1',data={'name':'Empire Magazine Africa','credits':'0'},status='published',published_url='https://example.com/audience-story',contact_email='audience-editor@example.com');db.add(o);await db.commit()
        print(json.dumps({'project':p.id,'placement':o.id}))
    await engine.dispose()
asyncio.run(seed())
`], { cwd: "../backend", encoding: "utf8" }));
  await page.goto("/latest-stories/audience-browser-story");
  await expect(page.getByRole("heading", { name: "Audience browser launch" })).toBeVisible();
  await expect.poll(async () => (await (await request.get(`${API}/v1/admin/analytics?project_id=${seeded.project}`, { headers: OPS })).json()).platform.story_visits).toBe(1);
  await page.reload(); await expect(page.getByRole("heading", { name: "Audience browser launch" })).toBeVisible();
  await page.goto("/latest-stories");
  await page.getByRole("link").filter({ hasText: "Audience browser launch" }).first().scrollIntoViewIfNeeded();
  await expect.poll(async () => (await (await request.get(`${API}/v1/admin/analytics?project_id=${seeded.project}`, { headers: OPS })).json()).platform.impressions).toBe(1);
  const admin = await browser.newContext(); const ap = await admin.newPage();
  await ap.addInitScript(() => sessionStorage.setItem("newsagent.admin.token", "dev:ops@example.com"));
  await ap.goto(`/admin/analytics?project=${seeded.project}`);
  await expect(ap.getByLabel("Story visits count", { exact: true })).toHaveText("1");
  await ap.getByLabel("Select published outlet").selectOption(seeded.placement);
  await ap.getByLabel("Cumulative views", { exact: true }).fill("1234");
  await ap.getByLabel("Cumulative impressions", { exact: true }).fill("9000");
  await ap.getByLabel("Source / customer-visible note").fill("Publisher monthly report");
  await ap.getByRole("button", { name: "Save publisher figures" }).click();
  await expect(ap.getByRole("status")).toHaveText("Publisher figures saved and visible to the customer.");
  await expect(ap.getByLabel("Reported channel views count", { exact: true })).toHaveText("1,234");
  await ap.getByRole("button", { name: "Request figures from publisher" }).click();
  await expect(ap.getByRole("status")).toContainText("Performance report request queued");
  await expect.poll(async () => (await request.get(`${API}/v1/dev/last-email`, { params: { to: "audience-editor@example.com" } })).status()).toBe(200);
  await page.addInitScript(() => localStorage.setItem("newsagent.token", "dev:audience-browser@example.com"));
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto(`/analytics?project=${seeded.project}`);
  await expect(page.getByRole("heading", { name: "Reports and analytics" })).toBeVisible();
  await expect(page.getByLabel("Reported channel views count", { exact: true })).toHaveText("1,234");
  await expect(page.getByLabel("Reported channel impressions count", { exact: true })).toHaveText("9,000");
  await expect(page.getByRole("heading", { name: "Publisher reports", exact: true })).toHaveCount(0);
  await expect(page.getByText("ops@example.com", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "View post" })).toHaveAttribute("href", "https://example.com/audience-story");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  const download = page.waitForEvent("download"); await page.getByRole("button", { name: "Download CSV" }).click();
  const file = await download; expect(await readFile((await file.path())!, "utf8")).toContain("9000");
  await page.screenshot({ path: "/tmp/analytics-mobile.png", fullPage: true });
  await ap.screenshot({ path: "/tmp/analytics-admin.png", fullPage: true });
  await admin.close();
});

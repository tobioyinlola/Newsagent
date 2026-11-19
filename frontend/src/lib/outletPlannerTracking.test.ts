import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { planBody, planRef, trackPlan, type Plan } from "./outletPlanner";

const plan: Plan = { key: "balanced", name: "Balanced", summary: "", total_credits: "136.2", outlets: [1, 2, 3, 4, 5].map((i) => ({ id: String(i), name: `O${i}`, topic: "General News", country: "Nigeria", region: "Africa", credits: "20", reasons: [] })), countries: [], topics: [] };

describe("what a plan request says about where it came from", () => {
  it("names the screen and whether it was made on its own", () => {
    expect(planBody({ budget: "", countries: [], goal: "credibility" })).toMatchObject({ source: "public", auto: false });
    expect(planBody({ budget: "", countries: [], goal: "credibility", source: "ready_prompt", auto: true })).toMatchObject({ source: "ready_prompt", auto: true });
  });
});

describe("telling the server a plan was used", () => {
  const fetchMock = vi.fn();
  beforeEach(() => { fetchMock.mockReset().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetchMock); });
  afterEach(() => vi.unstubAllGlobals());

  it("sends only the plan: never who the visitor is", () => {
    trackPlan("used", "public", planRef(plan), null);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/v1/public/distribution/plan/event");
    expect(JSON.parse(init.body)).toEqual({ kind: "used", source: "public", plan_key: "balanced", outlets: 5, credits: "136.2" });
    expect(init.headers.Authorization).toBeUndefined();
    expect(init.credentials).toBeUndefined(); // no cookies
  });

  it("uses the signed-in route, with the token, when there is one", () => {
    trackPlan("continued", "email", planRef(plan), "tok");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/v1/distribution/plan/event");
    expect(String(url)).not.toContain("/public/");
    expect(init.headers.Authorization).toBe("Bearer tok");
  });

  it("never breaks the screen, even when the request fails or fetch itself throws", async () => {
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    expect(() => trackPlan("used", "public", planRef(plan), null)).not.toThrow();
    fetchMock.mockImplementationOnce(() => { throw new Error("blocked"); });
    expect(() => trackPlan("used", "public", planRef(plan), null)).not.toThrow();
    await Promise.resolve();
  });
});

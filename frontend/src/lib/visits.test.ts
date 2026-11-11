import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => new Response(null, { status: 204 }));
const bodies = () => fetchMock.mock.calls.map((c) => JSON.parse(String(c[1]?.body)));

async function load() {
  vi.resetModules();
  return import("./visits");
}
beforeEach(() => { fetchMock.mockClear(); vi.stubGlobal("fetch", fetchMock); Object.defineProperty(navigator, "doNotTrack", { value: "0", configurable: true }); Object.defineProperty(document, "referrer", { value: "", configurable: true }); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("our own cookie-free visit counter", () => {
  it("sends the page name, never the raw address, and sets no cookie", async () => {
    const { recordVisit } = await load();
    recordVisit("/ai-newsroom/0123456789abcdef0123456789abcdef", "?token=secret&code=123456");
    expect(bodies()).toEqual([{ path: "/ai-newsroom/:id", referrer_host: "", utm_source: "", utm_medium: "", utm_campaign: "" }]);
    expect(fetchMock.mock.calls[0][0]).toBe("/v1/public/visit");
    expect(fetchMock.mock.calls[0][1]?.credentials).toBe("omit");
    expect(document.cookie).toBe("");
  });
  it("says where they came from only on arrival, and only the other site's name", async () => {
    Object.defineProperty(document, "referrer", { value: "https://www.google.com/search?q=secret+query", configurable: true });
    const { recordVisit } = await load();
    recordVisit("/", "?utm_source=cover_founder&utm_medium=email&utm_campaign=welcome");
    recordVisit("/signup", "?utm_source=again");
    expect(bodies()).toEqual([
      { path: "/", referrer_host: "www.google.com", utm_source: "cover_founder", utm_medium: "email", utm_campaign: "welcome" },
      { path: "/signup", referrer_host: "", utm_source: "", utm_medium: "", utm_campaign: "" },
    ]);
  });
  it("does not treat a move within our own site as arriving from somewhere", async () => {
    Object.defineProperty(document, "referrer", { value: `${location.origin}/pricing`, configurable: true });
    const { recordVisit } = await load();
    recordVisit("/", "");
    expect(bodies()[0].referrer_host).toBe("");
  });
  it("counts nobody who sent Do Not Track or Global Privacy Control, and never the private pages or the back office", async () => {
    const { recordVisit } = await load();
    for (const p of ["/admin/marketing", "/i/abc", "/s/abc"]) recordVisit(p, "");
    expect(fetchMock).not.toHaveBeenCalled();
    Object.defineProperty(navigator, "doNotTrack", { value: "1", configurable: true });
    recordVisit("/", "");
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("never gets in the way if counting fails", async () => {
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    const { recordVisit } = await load();
    expect(() => recordVisit("/", "")).not.toThrow();
    await Promise.resolve();
  });
});

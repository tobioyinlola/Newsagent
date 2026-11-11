import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
const visits = () => fetchMock.mock.calls.filter((c) => String((c as unknown[])[0]).includes("/v1/public/visit")).map((c) => JSON.parse(String((c as unknown as [string, { body: string }])[1].body)));

async function mount(path = "/", id = "G-L3JSNEQF7K") {
  vi.resetModules();
  vi.stubEnv("VITE_GA_MEASUREMENT_ID", id);
  const { TrackingConsent } = await import("./Analytics");
  const consent = await import("../lib/consent");
  render(<MemoryRouter initialEntries={[path]}><TrackingConsent /></MemoryRouter>);
  return consent;
}
const script = () => document.querySelector("script[src*=googletagmanager]");

beforeEach(() => { fetchMock.mockClear(); vi.stubGlobal("fetch", fetchMock); localStorage.clear(); sessionStorage.clear(); document.head.innerHTML = ""; window.dataLayer = undefined; window.gtag = undefined; Object.defineProperty(navigator, "doNotTrack", { value: "0", configurable: true }); });
afterEach(() => { cleanup(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("the cookie notice", () => {
  it("asks first, with Accept and Decline equally easy, and explains what is counted before anyone chooses", async () => {
    await mount();
    expect(screen.getByRole("region", { name: "Cookie choices" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Accept" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Decline" })).toBeTruthy();
    expect(screen.getByText(/without cookies/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /how we use cookies/i }).getAttribute("href")).toBe("/privacy#storage");
  });
  it("counts the visit straight away, without cookies, before anyone has chosen", async () => {
    await mount("/signup?token=secret&utm_source=cover_founder&utm_medium=email&utm_campaign=welcome");
    expect(visits()).toEqual([{ path: "/signup", referrer_host: "", utm_source: "cover_founder", utm_medium: "email", utm_campaign: "welcome" }]); // the secret is not sent
    expect(script()).not.toBeNull(); // Google counts it too, with analytics cookies denied
    const consentDefault = (window.dataLayer ?? []).map((e) => Array.from(e as ArrayLike<unknown>)).find((e) => e[0] === "consent" && e[1] === "default");
    expect(consentDefault?.[2]).toMatchObject({ analytics_storage: "denied" });
    expect(document.cookie).not.toContain("_ga");
  });
  it("accepting lets Google use cookies, remembers the choice, goes away, and doesn't count the page twice", async () => {
    const consent = await mount();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(consent.getConsent()).toBe("granted");
    const updates = (window.dataLayer ?? []).map((e) => Array.from(e as ArrayLike<unknown>)).filter((e) => e[0] === "consent" && e[1] === "update");
    expect(updates.at(-1)?.[2]).toEqual({ analytics_storage: "granted" });
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
    expect(visits()).toHaveLength(1);
    expect((window.dataLayer ?? []).map((e) => Array.from(e as ArrayLike<unknown>)).filter((e) => e[1] === "page_view")).toHaveLength(1);
  });
  it("declining switches Google off for them, but our own cookie-free count carries on", async () => {
    const consent = await mount();
    fireEvent.click(screen.getByRole("button", { name: "Decline" }));
    expect(consent.getConsent()).toBe("denied");
    expect(window[`ga-disable-G-L3JSNEQF7K`]).toBe(true);
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
    expect(visits()).toHaveLength(1);
  });
  it("after a remembered Decline, Google never loads and the visit is still counted by us; Cookie settings brings the question back", async () => {
    localStorage.setItem("newsagent.analytics-consent", "denied");
    const consent = await mount();
    expect(script()).toBeNull();
    expect(visits()).toHaveLength(1);
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
    act(() => { consent.openCookieSettings(); });
    expect(screen.getByRole("region", { name: "Cookie choices" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(script()).not.toBeNull();
  });
  it("is never shown, and nothing is counted, on private links", async () => {
    await mount("/i/sometoken");
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
    expect(visits()).toEqual([]);
    expect(script()).toBeNull();
  });
  it("when Google Analytics isn't set up: no banner, no Google, but our own count still works", async () => {
    await mount("/", "");
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
    expect(script()).toBeNull();
    expect(visits()).toHaveLength(1);
  });
  it("respects a browser's privacy signal: no question, nothing sent to Google, nothing counted", async () => {
    Object.defineProperty(navigator, "doNotTrack", { value: "1", configurable: true });
    const consent = await mount();
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
    expect(script()).toBeNull();
    expect(visits()).toEqual([]);
    act(() => { consent.openCookieSettings(); });
    expect(screen.getByText(/Do Not Track/)).toBeTruthy();
  });
});

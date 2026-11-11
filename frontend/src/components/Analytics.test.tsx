import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

async function mount(path = "/", id = "G-L3JSNEQF7K") {
  vi.resetModules();
  vi.stubEnv("VITE_GA_MEASUREMENT_ID", id);
  const { TrackingConsent } = await import("./Analytics");
  const consent = await import("../lib/consent");
  render(<MemoryRouter initialEntries={[path]}><TrackingConsent /></MemoryRouter>);
  return consent;
}
const script = () => document.querySelector("script[src*=googletagmanager]");

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); document.head.innerHTML = ""; window.dataLayer = undefined; window.gtag = undefined; Object.defineProperty(navigator, "doNotTrack", { value: "0", configurable: true }); });
afterEach(() => { cleanup(); vi.unstubAllEnvs(); });

describe("the cookie notice", () => {
  it("asks first, with Accept and Decline equally easy, and loads nothing yet", async () => {
    await mount();
    expect(screen.getByRole("region", { name: "Cookie choices" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Accept" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Decline" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /how we use cookies/i }).getAttribute("href")).toBe("/privacy#storage");
    expect(script()).toBeNull();
  });
  it("accepting starts analytics, remembers the choice and goes away", async () => {
    const consent = await mount();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(consent.getConsent()).toBe("granted");
    expect(script()).not.toBeNull();
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
  });
  it("declining loads nothing and goes away", async () => {
    const consent = await mount();
    fireEvent.click(screen.getByRole("button", { name: "Decline" }));
    expect(consent.getConsent()).toBe("denied");
    expect(script()).toBeNull();
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
  });
  it("does not ask again once they have chosen, but Cookie settings brings it back", async () => {
    localStorage.setItem("newsagent.analytics-consent", "denied");
    const consent = await mount();
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
    act(() => { consent.openCookieSettings(); });
    expect(screen.getByRole("region", { name: "Cookie choices" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(script()).not.toBeNull();
  });
  it("sends the first page view as soon as they accept, with a cleaned address", async () => {
    await mount("/ai-newsroom/0123456789abcdef0123456789abcdef?token=secret");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    const pageViews = (window.dataLayer ?? []).map((e) => Array.from(e as ArrayLike<unknown>)).filter((e) => e[1] === "page_view");
    expect(pageViews).toHaveLength(1);
    expect((pageViews[0][2] as { page_location: string }).page_location).toBe(`${location.origin}/ai-newsroom/:id`);
  });
  it("is never shown on private links, and not at all when analytics isn't set up", async () => {
    await mount("/i/sometoken");
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
    cleanup();
    await mount("/", "");
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
  });
  it("tells people their browser's privacy signal is respected, instead of asking", async () => {
    Object.defineProperty(navigator, "doNotTrack", { value: "1", configurable: true });
    const consent = await mount();
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
    act(() => { consent.openCookieSettings(); });
    expect(screen.getByText(/Do Not Track/)).toBeTruthy();
    expect(script()).toBeNull();
  });
});

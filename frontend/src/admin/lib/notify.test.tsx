import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "../components/Toaster";
import { announceSaves, messageFor, notify } from "./notify";

describe("what gets announced", () => {
  it("announces saves and removals on our own API", () => {
    expect(messageFor("PUT", "http://localhost:8000/v1/admin/outreach/config", true)).toBe("Saved");
    expect(messageFor("PATCH", "/v1/admin/distribution/1/placements/2", true)).toBe("Saved");
    expect(messageFor("POST", "/v1/admin/invites", true)).toBe("Saved");
    expect(messageFor("DELETE", "/v1/admin/outreach/mailbox", true)).toBe("Removed");
  });
  it("stays quiet for reads, failures, sign-in, previews, tests and uploads to storage", () => {
    expect(messageFor("GET", "/v1/admin/outreach/config", true)).toBeNull();
    expect(messageFor("PUT", "/v1/admin/outreach/config", false)).toBeNull();
    expect(messageFor("POST", "/v1/auth/login", true)).toBeNull();
    expect(messageFor("POST", "/v1/admin/outreach/preview", true)).toBeNull();
    expect(messageFor("POST", "/v1/admin/outreach/mailbox/test", true)).toBeNull();
    expect(messageFor("POST", "/v1/admin/marketing/copies/test", true)).toBeNull();
    expect(messageFor("PUT", "https://storage.example.com/bucket/file.png?sig=1", true)).toBeNull();
  });
});

describe("the pop-up", () => {
  afterEach(() => { vi.useRealTimers(); });
  it("shows a message, then goes away", () => {
    vi.useFakeTimers();
    render(<Toaster />);
    expect(screen.queryByRole("status")).toBeNull();
    act(() => notify("Saved"));
    expect(screen.getByRole("status").textContent).toContain("Saved");
    act(() => { vi.advanceTimersByTime(4000); });
    expect(screen.queryByRole("status")).toBeNull();
  });
  it("draws only one pop-up even when two are mounted", () => {
    render(<><Toaster /><Toaster /></>);
    act(() => notify("Saved"));
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });
  it("pops up after a successful save request, and not after a failed one", async () => {
    const calls = [new Response("{}", { status: 200 }), new Response("{}", { status: 500 })];
    vi.stubGlobal("fetch", vi.fn(async () => calls.shift()!));
    window.fetch = globalThis.fetch;
    announceSaves();
    render(<Toaster />);
    await act(async () => { await window.fetch("/v1/admin/outreach/config", { method: "PUT" }); });
    expect(screen.getByRole("status").textContent).toContain("Saved");
    act(() => notify(""));
    await act(async () => { await window.fetch("/v1/admin/outreach/config", { method: "PUT" }); });
    expect(screen.queryByText("Saved")).toBeNull();
  });
});

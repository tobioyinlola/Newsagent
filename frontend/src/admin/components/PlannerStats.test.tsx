import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PlannerStats } from "./PlannerStats";
import { distributionApi } from "../../lib/distribution";

let canManage = true;
vi.mock("../lib/can", () => ({ useCan: () => (...wanted: string[]) => wanted.includes("operations.manage") ? canManage : true }));
vi.mock("../../lib/distribution", async (orig) => ({ ...(await orig<typeof import("../../lib/distribution")>()), distributionApi: vi.fn() }));

const block = (o: object = {}) => ({ shown: 0, asked: 0, used: 0, continued: 0, submitted: 0, unchanged: 0, credits_submitted: "0", rates: { use_of_viewed: null, submitted_of_used: null, unchanged_of_submitted: null, average_credits: null }, ...o });
const stats = { days: 30, since: "2026-10-19T00:00:00Z", total: block({ shown: 6, asked: 4, used: 5, continued: 2, submitted: 2, unchanged: 1, rates: { use_of_viewed: 0.5, submitted_of_used: 0.4, unchanged_of_submitted: 0.5, average_credits: "80.0" } }), by_source: { public: block({ asked: 4, used: 3, continued: 2 }), ready_prompt: block({ shown: 6, used: 2, submitted: 2, unchanged: 1 }), request: block(), email: block() } };
const off = { enabled: false, source: "default", changed_by: null, changed_at: null };
const on = { enabled: true, source: "back office", changed_by: "ops@example.com", changed_at: "2026-11-19T08:00:00Z" };
let state: object = off;
const api = (statsOk = true) => vi.mocked(distributionApi).mockImplementation(async (path: string, _t: string | null, method = "GET", body?: unknown) => {
  if (path.startsWith("admin/planner-settings")) { if (method === "PUT") state = { ...on, enabled: (body as { enabled: boolean }).enabled }; return state as never; }
  if (!statsOk) throw new Error("no");
  return stats as never;
});
const wrap = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PlannerStats /></QueryClientProvider>);
beforeEach(() => { vi.mocked(distributionApi).mockReset(); state = off; canManage = true; });
afterEach(cleanup);

describe("the suggested-plans numbers", () => {
  it("shows the totals and rates in plain words", async () => {
    api(); wrap();
    expect(await screen.findByText("Plans viewed")).toBeTruthy();
    expect(screen.getByText("10")).toBeTruthy(); // 6 shown + 4 asked
    expect(screen.getByText("50%", { selector: "p" })).toBeTruthy(); // kept as suggested
    expect(screen.getByText(/1 of 2 paid requests were not changed/)).toBeTruthy();
    expect(screen.getByText(/80.0 credits/)).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
  });
  it("shows a dash, not a made-up zero, where there is nothing to divide", async () => {
    vi.mocked(distributionApi).mockImplementation(async (path: string) => (path.startsWith("admin/planner-settings") ? (off as never) : ({ ...stats, total: block() } as never)));
    wrap();
    expect((await screen.findAllByText("–")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/credits\./)).toBeNull();
  });
  it("says so when the numbers cannot be loaded", async () => {
    api(false); wrap();
    expect((await screen.findAllByRole("alert")).some((a) => a.textContent?.includes("could not load"))).toBe(true);
  });
});

describe("the on/off switch", () => {
  it("shows that it is off by default, in plain words", async () => {
    api(); wrap();
    const sw = await screen.findByRole("switch");
    await waitFor(() => expect(sw.getAttribute("aria-checked")).toBe("false"));
    expect(screen.getByText(/Off: nobody is offered plans/)).toBeTruthy();
    expect(screen.getByText(/This is the default setting/)).toBeTruthy();
  });
  it("turns it on straight away and says who did", async () => {
    api(); wrap();
    const sw = await screen.findByRole("switch");
    await waitFor(() => expect((sw as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(sw);
    await waitFor(() => expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true"));
    expect(vi.mocked(distributionApi).mock.calls.some((c) => c[0] === "admin/planner-settings" && c[2] === "PUT" && JSON.stringify(c[3]) === JSON.stringify({ enabled: true }))).toBe(true);
    expect(screen.getByText(/On: plans are offered/)).toBeTruthy();
    expect(screen.getByText(/Changed by ops@example.com/)).toBeTruthy();
  });
  it("can be seen but not changed without permission", async () => {
    canManage = false; api(); wrap();
    const sw = await screen.findByRole("switch");
    expect((sw as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/You can see this setting but not change it/)).toBeTruthy();
  });
  it("says so when a change does not go through", async () => {
    vi.mocked(distributionApi).mockImplementation(async (path: string, _t: string | null, method = "GET") => { if (path.startsWith("admin/planner-settings")) { if (method === "PUT") throw new Error("no"); return off as never; } return stats as never; });
    wrap();
    const sw = await screen.findByRole("switch");
    await waitFor(() => expect((sw as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(sw);
    expect((await screen.findAllByRole("alert")).some((a) => a.textContent?.includes("could not change"))).toBe(true);
    expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("false");
  });
});

import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PlannerStats } from "./PlannerStats";
import { distributionApi } from "../../lib/distribution";

vi.mock("../../lib/distribution", async (orig) => ({ ...(await orig<typeof import("../../lib/distribution")>()), distributionApi: vi.fn() }));
const block = (o: object = {}) => ({ shown: 0, asked: 0, used: 0, continued: 0, submitted: 0, unchanged: 0, credits_submitted: "0", rates: { use_of_viewed: null, submitted_of_used: null, unchanged_of_submitted: null, average_credits: null }, ...o });
const stats = { days: 30, since: "2026-10-19T00:00:00Z", total: block({ shown: 6, asked: 4, used: 5, continued: 2, submitted: 2, unchanged: 1, rates: { use_of_viewed: 0.5, submitted_of_used: 0.4, unchanged_of_submitted: 0.5, average_credits: "80.0" } }), by_source: { public: block({ asked: 4, used: 3, continued: 2 }), ready_prompt: block({ shown: 6, used: 2, submitted: 2, unchanged: 1 }), request: block(), email: block() } };
const wrap = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PlannerStats /></QueryClientProvider>);
afterEach(cleanup);

describe("the suggested-plans numbers", () => {
  it("shows the totals and rates in plain words", async () => {
    vi.mocked(distributionApi).mockResolvedValue(stats);
    wrap();
    expect(await screen.findByText("Plans viewed")).toBeTruthy();
    expect(screen.getByText("10")).toBeTruthy(); // 6 shown + 4 asked
    expect(screen.getByText("50%", { selector: "p" })).toBeTruthy(); // kept as suggested
    expect(screen.getByText(/1 of 2 paid requests were not changed/)).toBeTruthy();
    expect(screen.getByText(/80.0 credits/)).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
  });
  it("shows a dash, not a made-up zero, where there is nothing to divide", async () => {
    vi.mocked(distributionApi).mockResolvedValue({ ...stats, total: block() });
    wrap();
    expect((await screen.findAllByText("–")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/credits\./)).toBeNull();
  });
  it("says so when the numbers cannot be loaded", async () => {
    vi.mocked(distributionApi).mockRejectedValue(new Error("no"));
    wrap();
    expect((await screen.findByRole("alert")).textContent).toContain("could not load");
  });
});

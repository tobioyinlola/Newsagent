import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { DistributionReadyPrompt } from "./DistributionReadyPrompt";
import { distributionApi } from "../lib/distribution";
import { readPick } from "../lib/distributionFilters";
import { featuredPlan, outletSummary, type Plan, type PlanResult } from "../lib/outletPlanner";

vi.mock("../lib/distribution", async (orig) => ({ ...(await orig<typeof import("../lib/distribution")>()), distributionApi: vi.fn() }));

const outlet = (id: string, name: string) => ({ id, name, topic: "General News", country: "Nigeria", region: "Africa", credits: "20", reasons: ["Based in Nigeria"] });
const plan = (key: Plan["key"], name: string, ids: string[], total: string): Plan => ({ key, name, summary: "", total_credits: total, outlets: ids.map((i) => outlet(i, `Outlet ${i}`)), countries: ["Nigeria"], topics: ["General News"] });
const result = (balance: string, over: Partial<PlanResult> = {}): PlanResult => ({ plans: [plan("essential", "Essential", ["1", "2"], "40"), plan("balanced", "Balanced", ["1", "2", "3", "4"], "80"), plan("max", "Maximum reach", ["1", "2", "3", "4", "5"], "200")], suggested: {}, budget_presets: [], cheapest_credits: "20", notes: [], countries: ["Nigeria"], goal: "credibility", balance_credits: balance, ...over });
function Where() { const l = useLocation(); return <p data-testid="path">{l.pathname}{l.search}</p>; }

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) { this.setAttribute("open", ""); });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) { this.removeAttribute("open"); });
  vi.mocked(distributionApi).mockReset();
});
afterEach(() => { cleanup(); localStorage.clear(); });

describe("featuredPlan", () => {
  it("features the biggest plan the wallet covers", () => {
    const f = featuredPlan(result("100"))!;
    expect(f.plan.key).toBe("balanced"); expect(f.fits).toBe(true); expect(f.missing).toBe(0);
  });
  it("features the smallest plan, and what is missing, when the wallet covers none", () => {
    const f = featuredPlan(result("15"))!;
    expect(f.plan.key).toBe("essential"); expect(f.fits).toBe(false); expect(f.missing).toBe(25);
  });
  it("says nothing personal when there is no country to go on or no plan", () => {
    expect(featuredPlan(result("100", { countries: [] }))).toBeNull();
    expect(featuredPlan(result("100", { plans: [] }))).toBeNull();
  });
  it("lists a few outlet names and counts the rest", () => {
    expect(outletSummary(plan("max", "Max", ["1", "2", "3", "4", "5"], "1"))).toBe("Outlet 1, Outlet 2, Outlet 3 and 2 more");
    expect(outletSummary(plan("essential", "E", ["1", "2"], "1"))).toBe("Outlet 1, Outlet 2");
  });
});

describe("the recommendation on the video-ready prompt", () => {
  it("shows a plan made for this business and starts the request with its outlets chosen", async () => {
    vi.mocked(distributionApi).mockResolvedValue(result("100"));
    render(<MemoryRouter><DistributionReadyPrompt projectId="vid 1" workspaceId="w" /><Where /></MemoryRouter>);
    expect(await screen.findByText("Recommended for you")).toBeTruthy();
    expect(screen.getByText(/Balanced plan: 4 outlets for 80 credits/)).toBeTruthy();
    expect(screen.getByText("You have 100 credits, so it fits.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start with this plan" }));
    expect(screen.getByTestId("path").textContent).toBe("/distribution/request?project=vid%201&pick=1");
    expect(readPick()).toEqual(["1", "2", "3", "4"]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("says plainly how many credits are missing", async () => {
    vi.mocked(distributionApi).mockResolvedValue(result("15"));
    render(<MemoryRouter><DistributionReadyPrompt projectId="p" workspaceId="w" /></MemoryRouter>);
    expect(await screen.findByText(/You need 25 credits more for this plan/)).toBeTruthy();
  });

  it("stays exactly as it was when there is nothing personal to show", async () => {
    vi.mocked(distributionApi).mockResolvedValue(result("100", { countries: [] }));
    render(<MemoryRouter><DistributionReadyPrompt projectId="p" workspaceId="w" /><Where /></MemoryRouter>);
    await waitFor(() => expect(distributionApi).toHaveBeenCalled());
    expect(screen.queryByText("Recommended for you")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Yes, choose outlets" }));
    expect(screen.getByTestId("path").textContent).toBe("/distribution/request?project=p");
  });

  it("stays as it was when the plan cannot be fetched, and while the video is still being made", async () => {
    vi.mocked(distributionApi).mockRejectedValue(new Error("offline"));
    const { unmount } = render(<MemoryRouter><DistributionReadyPrompt projectId="p" workspaceId="w" /></MemoryRouter>);
    await waitFor(() => expect(distributionApi).toHaveBeenCalled());
    expect(screen.queryByText("Recommended for you")).toBeNull();
    expect(screen.getByRole("button", { name: "Yes, choose outlets" })).toBeTruthy();
    unmount();
    vi.mocked(distributionApi).mockReset().mockResolvedValue(result("100"));
    render(<MemoryRouter><DistributionReadyPrompt projectId="p" workspaceId="w" stage="making" /></MemoryRouter>);
    expect(distributionApi).not.toHaveBeenCalled();
  });
});

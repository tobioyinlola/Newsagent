import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OutletPlanner } from "./OutletPlanner";
import { planBody, type Plan, type PlanResult } from "../lib/outletPlanner";

const outlet = (id: string, name: string, credits: string) => ({ id, name, topic: "General News", country: "Nigeria", region: "Africa", credits, reasons: ["Based in Nigeria", "A general news audience"] });
const plan = (key: Plan["key"], name: string, ids: string[], total: string, shortfall?: string): Plan => ({ key, name, summary: `${name} summary`, total_credits: total, outlets: ids.map((i) => outlet(i, `Outlet ${i}`, "20")), countries: ["Nigeria"], topics: ["General News"], ...(shortfall ? { shortfall_credits: shortfall } : {}) });
const result = (over: Partial<PlanResult> = {}): PlanResult => ({ plans: [plan("essential", "Essential", ["1", "2"], "40"), plan("balanced", "Balanced", ["1", "2", "3"], "60", "20")], suggested: { "1": ["Based in Nigeria"], "2": ["Based in Nigeria"], "3": ["Based in Nigeria"] }, budget_presets: ["40", "60"], cheapest_credits: "20", notes: [], countries: ["Nigeria"], goal: "credibility", ...over });
const props = (over = {}) => ({ countries: ["Kenya", "Nigeria"], fetchPlan: vi.fn().mockResolvedValue(result()), onApply: vi.fn(), ...over });

describe("planBody", () => {
  it("treats a blank or invalid budget as no limit", () => {
    expect(planBody({ budget: "", countries: [], goal: "credibility" }).budget).toBeNull();
    expect(planBody({ budget: "abc", countries: [], goal: "credibility" }).budget).toBeNull();
    expect(planBody({ budget: "250", countries: ["Nigeria"], goal: "investors" })).toMatchObject({ budget: "250", countries: ["Nigeria"], goal: "investors" });
  });
});

describe("OutletPlanner", () => {
  afterEach(cleanup);
  it("asks the three questions and sends the answers", async () => {
    const p = props();
    render(<OutletPlanner {...p} />);
    fireEvent.click(screen.getByLabelText("Nigeria"));
    fireEvent.change(screen.getByLabelText(/how many credits/i), { target: { value: "300" } });
    fireEvent.click(screen.getByLabelText(/reach investors/i));
    fireEvent.click(screen.getByRole("button", { name: "Suggest outlets" }));
    await waitFor(() => expect(p.fetchPlan).toHaveBeenCalledTimes(1));
    expect(p.fetchPlan).toHaveBeenCalledWith(expect.objectContaining({ budget: "300", countries: ["Nigeria"], goal: "investors" }));
  });

  it("shows each plan with its price and the reasons, and applies the one chosen", async () => {
    const p = props();
    render(<OutletPlanner {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "Suggest outlets" }));
    expect(await screen.findByRole("heading", { name: "Essential" })).toBeTruthy();
    expect(screen.getAllByText("40 credits").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Based in Nigeria/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Use this plan" })[0]);
    expect(p.onApply).toHaveBeenCalledWith(expect.objectContaining({ key: "essential" }));
    expect(await screen.findByText(/Essential plan selected: 2 outlets/)).toBeTruthy();
  });

  it("passes the suggested outlets up so the full list can mark them", async () => {
    const onResult = vi.fn();
    render(<OutletPlanner {...props({ onResult })} />);
    fireEvent.click(screen.getByRole("button", { name: "Suggest outlets" }));
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(expect.objectContaining({ suggested: expect.objectContaining({ "1": ["Based in Nigeria"] }) })));
  });

  it("says how many credits are missing and offers to add them", async () => {
    const onTopUp = vi.fn();
    render(<OutletPlanner {...props({ onTopUp })} />);
    fireEvent.click(screen.getByRole("button", { name: "Suggest outlets" }));
    expect(await screen.findByText(/You need 20 credits more for this plan/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add credits" }));
    expect(onTopUp).toHaveBeenCalledWith(expect.objectContaining({ key: "balanced" }));
  });

  it("marks the plan already in use", async () => {
    render(<OutletPlanner {...props({ appliedIds: ["1", "2"] })} />);
    fireEvent.click(screen.getByRole("button", { name: "Suggest outlets" }));
    expect((await screen.findByRole("button", { name: "✓ In use" })).getAttribute("aria-pressed")).toBe("true");
  });

  it("explains when nothing fits, and when something goes wrong", async () => {
    const empty = props({ fetchPlan: vi.fn().mockResolvedValue(result({ plans: [], suggested: {}, empty: "That budget is below our lowest price." })) });
    const { unmount } = render(<OutletPlanner {...empty} />);
    fireEvent.click(screen.getByRole("button", { name: "Suggest outlets" }));
    expect(await screen.findByText("That budget is below our lowest price.")).toBeTruthy();
    unmount();
    render(<OutletPlanner {...props({ fetchPlan: vi.fn().mockRejectedValue(new Error("Too many tries. Please wait a moment.")) })} />);
    fireEvent.click(screen.getByRole("button", { name: "Suggest outlets" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Too many tries");
  });

  it("starts from what we know when asked to run straight away", async () => {
    const p = props({ autoRun: true, fetchPlan: vi.fn().mockResolvedValue(result({ countries: ["Nigeria"] })) });
    render(<OutletPlanner {...p} />);
    await waitFor(() => expect(p.fetchPlan).toHaveBeenCalledTimes(1));
    expect(((await screen.findByLabelText(/Nigeria/)) as HTMLInputElement).checked).toBe(true); // the country the server started from is shown as picked
  });

  it("never promises publication", async () => {
    render(<OutletPlanner {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "Suggest outlets" }));
    expect(await screen.findByText(/not guaranteed/)).toBeTruthy();
  });
});

import { beforeEach, describe, expect, it } from "vitest";
import { ALL, counts, emptyReason, isAllowedAfter, matches, peekAfterAuth, readPick, savePick, setAfterAuth, takeAfterAuth, clearPick } from "./distributionFilters";

const outlets = [
  { id: "1", topic: "Technology", region: "Africa", country: "Nigeria" },
  { id: "2", topic: "General News", region: "Africa", country: "Nigeria" },
  { id: "3", topic: "Gossip Blogs", region: "Africa", country: "Nigeria" },
  { id: "4", topic: "General News", region: "Africa", country: "Kenya" },
  { id: "5", topic: "General News", region: "North America", country: "United States" },
];
const filters = { topics: ["Technology", "General News", "Gossip Blogs"], locations: [{ region: "Africa", countries: ["Nigeria", "Ghana", "Kenya", "Uganda"] }, { region: "North America", countries: ["Canada", "United States"] }, { region: "Europe", countries: ["United Kingdom"] }] };

beforeEach(() => localStorage.clear());

describe("filtering", () => {
  it("shows everything when nothing is chosen and narrows by topic, region and country", () => {
    expect(outlets.filter((o) => matches(o, ALL))).toHaveLength(5);
    expect(outlets.filter((o) => matches(o, { ...ALL, topic: "General News" })).map((o) => o.id)).toEqual(["2", "4", "5"]);
    expect(outlets.filter((o) => matches(o, { ...ALL, region: "Africa" }))).toHaveLength(4);
    expect(outlets.filter((o) => matches(o, { topic: "General News", region: "Africa", country: "Kenya" })).map((o) => o.id)).toEqual(["4"]);
  });
  it("counts what each choice would show, given the others", () => {
    const c = counts(outlets, { ...ALL, region: "Africa" }, filters);
    expect(c.topic).toEqual({ Technology: 1, "General News": 2, "Gossip Blogs": 1 });
    expect(c.all).toBe(4);
    expect(counts(outlets, ALL, filters).country.Ghana).toBe(0);
  });
  it("explains an empty result", () => {
    expect(emptyReason(outlets, ALL)).toBeNull();
    expect(emptyReason(outlets, { ...ALL, country: "Ghana" })).toMatch(/no outlets in Ghana yet/);
    expect(emptyReason(outlets, { topic: "Technology", region: "Africa", country: "Kenya" })).toMatch(/No outlets match/);
  });
});

describe("the saved choice", () => {
  it("is kept, and forgotten after a week or when cleared", () => {
    savePick(["2", "5"]);
    expect(readPick()).toEqual(["2", "5"]);
    expect(readPick(Date.now() + 8 * 24 * 3600 * 1000)).toEqual([]);
    expect(readPick()).toEqual([]); // the expired one was removed
    savePick(["1"]); clearPick();
    expect(readPick()).toEqual([]);
  });
  it("ignores damaged storage", () => {
    localStorage.setItem("newsagent.distribution.pick", "{not json");
    expect(readPick()).toEqual([]);
    localStorage.setItem("newsagent.distribution.pick", JSON.stringify({ ids: [1, "2"], at: Date.now() }));
    expect(readPick()).toEqual(["2"]);
  });
  it("only ever sends people to the distribution request page after sign-in", () => {
    expect(isAllowedAfter("/distribution/request?pick=1")).toBe(true);
    expect(isAllowedAfter("/distribution/request")).toBe(true);
    for (const bad of ["https://evil.test", "//evil.test", "/dashboard", "/distribution/requestx", "/distribution/request/../../admin"]) expect(isAllowedAfter(bad)).toBe(false);
    setAfterAuth("https://evil.test");
    expect(peekAfterAuth()).toBeNull();
    setAfterAuth("/distribution/request?pick=1");
    expect(peekAfterAuth()).toBe("/distribution/request?pick=1");
    expect(takeAfterAuth()).toBe("/distribution/request?pick=1");
    expect(takeAfterAuth()).toBeNull(); // used once
  });
});

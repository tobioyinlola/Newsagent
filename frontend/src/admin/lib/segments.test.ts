import { describe as suite, expect, it } from "vitest";
import { blankCondition, type Condition, cleanRules, countRules, describe, describeRules, type FieldDef } from "./segments";

const joined: FieldDef = { key: "joined_days_ago", label: "Days since they joined", group: "When", kind: "number", ops: ["gte", "lte", "eq", "between"], unit: "days", options: [] };
const dates: FieldDef = { key: "joined_dates", label: "Joined between dates", group: "When", kind: "dates", ops: ["between"], unit: "", options: [] };
const bought: FieldDef = { key: "has_bought_credits", label: "Has bought credits", group: "Money", kind: "bool", ops: ["is"], unit: "", options: [] };

suite("segment rules in the editor", () => {
  it("sends typed numbers as numbers, ranges included, and leaves dates and yes/no alone", () => {
    const out = cleanRules({ match: "all", conditions: [
      { field: "joined_days_ago", op: "between", value: ["3", "7"] },
      { field: "videos_started", op: "eq", value: "0" },
      { field: "joined_dates", op: "between", value: ["2026-01-01", "2026-01-31"] },
      { field: "has_bought_credits", op: "is", value: false },
    ] });
    expect(out.conditions.map((c) => (c as Condition).value)).toEqual([[3, 7], 0, ["2026-01-01", "2026-01-31"], false]);
  });
  it("keeps an empty box empty so the server can ask for it", () => {
    expect((cleanRules({ match: "all", conditions: [{ field: "joined_days_ago", op: "gte", value: "" }] }).conditions[0] as Condition).value).toBe("");
  });
  it("starts each kind of rule with a value its input can show", () => {
    expect(blankCondition(joined)).toEqual({ field: "joined_days_ago", op: "gte", value: "" });
    expect(blankCondition(dates).value).toEqual(["", ""]);
    expect(blankCondition(bought).value).toBe(true);
  });
  it("reads a rule back as a sentence", () => {
    expect(describe({ field: "joined_days_ago", op: "between", value: [3, 7] }, [joined])).toBe("Days since they joined between 3 and 7 days");
    expect(describe({ field: "has_bought_credits", op: "is", value: false }, [bought])).toBe("Has bought credits: no");
  });
  it("cleans, counts and reads back groups inside groups", () => {
    const rules = { match: "all" as const, conditions: [
      { field: "joined_days_ago", op: "gte", value: "30" },
      { match: "any" as const, conditions: [{ field: "videos_started", op: "gte", value: "1" }, { field: "has_bought_credits", op: "is", value: true }] },
    ] };
    const out = cleanRules(rules);
    expect(((out.conditions[1] as typeof rules).conditions[0] as Condition).value).toBe(1);
    expect(countRules(rules)).toBe(3);
    expect(describeRules(rules, [joined, { ...bought, key: "videos_started", label: "Videos started", kind: "number", ops: ["gte"], unit: "videos" }, bought])).toBe("Days since they joined at least 30 days AND (Videos started at least 1 videos OR Has bought credits: yes)");
  });
});

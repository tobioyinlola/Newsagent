import { describe, expect, it } from "vitest";
import { type TourDef, stepsSeen } from "./tourTypes";
import { toursFor } from "../../admin/lib/adminTours";

const def: TourDef = { id: "t", title: "T", summary: "", steps: [{ title: "a", body: "" }, { title: "b", body: "" }, { title: "c", body: "" }] };

describe("tour progress", () => {
  it("counts the steps seen, and all of them once finished", () => {
    expect(stepsSeen(def, undefined)).toBe(0);
    expect(stepsSeen(def, { step: 2 })).toBe(2);
    expect(stepsSeen(def, { step: 9 })).toBe(3);
    expect(stepsSeen(def, { step: 1, done: true })).toBe(3);
  });
});

describe("back office tours follow the person's permissions", () => {
  it("shows an owner everything", () => {
    const all = () => true;
    const ids = toursFor(all, true).map((t) => t.id);
    expect(ids).toEqual(["admin-platform", "admin-customers", "admin-distribution", "admin-outreach", "admin-team"]);
    expect(toursFor(all, true)[0].steps.length).toBeGreaterThan(15);
  });
  it("leaves out sections the role cannot open, and tours with nothing left", () => {
    const supportOnly = (...p: string[]) => p.includes("customers.view");
    const tours = toursFor(supportOnly, true);
    expect(tours.map((t) => t.id)).toEqual(["admin-platform", "admin-customers"]);
    const targets = tours[0].steps.map((s) => s.target);
    expect(targets).toContain("nav-customers");
    expect(targets).toContain("nav-security"); // open to every team member
    expect(targets).not.toContain("nav-revenue");
    expect(targets).not.toContain("nav-team");
  });
  it("drops the outreach steps when the section is hidden", () => {
    const all = () => true;
    const tours = toursFor(all, false);
    expect(tours.map((t) => t.id)).not.toContain("admin-outreach");
    expect(tours[0].steps.map((s) => s.target)).not.toContain("nav-outreach");
  });
});

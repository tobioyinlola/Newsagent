import { describe, expect, it } from "vitest";
import { validateDistributionStep } from "./distributionValidation";
import type { Draft } from "./distribution";

const complete: Draft = { stage: "review", outlet_ids: ["1"], project_id: "video", headline: "A headline", announcement: "Our story.", contact_name: "Ada", contact_email: "ada@example.com", phone: "+2348012345678", whatsapp: "+2348012345678", logo_key: "checked-logo", picture_keys: [] };
describe("distribution step validation", () => {
  it("requires outlet selection before advancing", () => {
    expect(validateDistributionStep({ ...complete, outlet_ids: [] }, "outlets").outlet_ids).toBeTruthy();
  });
  it("requires a completed video and nonblank announcement fields", () => {
    expect(Object.keys(validateDistributionStep({ ...complete, project_id: null, headline: "  ", announcement: "\n" }, "content"))).toEqual(["project_id", "headline", "announcement"]);
  });
  it("requires explicit story selection in platform mode but permits custom text", () => {
    expect(validateDistributionStep({ ...complete, announcement_source: "platform" }, "content").story_project_id).toBeTruthy();
    expect(validateDistributionStep({ ...complete, announcement_source: "platform", story_project_id: "story" }, "content")).toEqual({});
    expect(validateDistributionStep({ ...complete, announcement_source: "custom" }, "content")).toEqual({});
  });
  it("requires usable contact details and a checked logo, while pictures stay optional", () => {
    expect(Object.keys(validateDistributionStep({ ...complete, contact_name: "", contact_email: "wrong", phone: "abc1234567", whatsapp: "123", logo_key: "" }, "contact"))).toHaveLength(5);
    expect(validateDistributionStep(complete, "contact")).toEqual({});
  });
});

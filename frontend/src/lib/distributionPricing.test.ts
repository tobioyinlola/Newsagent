import { describe, expect, it } from "vitest";
import { priceOutlets, type Draft, type Outlet } from "./distribution";

const draft: Draft = { stage: "review", outlet_ids: ["1"], project_id: "video", headline: "Launch", announcement: "Announcement", contact_name: "Ada", contact_email: "ada@example.com", phone: "+2348031234567", whatsapp: "+2348031234567", logo_key: "logo.png", picture_keys: ["one.png", "two.png"] };
const outlet: Outlet = { id: "1", name: "Publication", region: "Africa", credits: "0.1", logo_credits: "0.2", picture_credits: "0.025", media_policy_configured: true, accepts_logo: true, accepts_images: true };
describe("distribution price shown before payment", () => {
  it("totals fractional placement, logo and per-picture fees without floating point residue", () => {
    expect(priceOutlets([outlet], draft)[0].credits).toBe("0.35");
  });
  it("does not charge for opted-out, unsupported or unconfirmed images", () => {
    expect(priceOutlets([outlet], { ...draft, media_options: { "1": { include_logo: false, include_pictures: false } } })[0].credits).toBe("0.1");
    expect(priceOutlets([{ ...outlet, accepts_logo: false, accepts_images: false }], draft)[0].credits).toBe("0.1");
    expect(priceOutlets([{ ...outlet, media_policy_configured: false }], draft)[0].credits).toBe("0.1");
  });
});

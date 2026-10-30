import type { Draft } from "./distribution";
export type DistributionErrors = Partial<Record<keyof Draft, string>>;
export function validateDistributionStep(d: Draft, step: string): DistributionErrors {
  const e: DistributionErrors = {};
  if (step === "outlets" && !d.outlet_ids.length) e.outlet_ids = "Choose at least one media outlet to continue.";
  if (step === "content") {
    if (!d.project_id) e.project_id = "Select a completed video.";
    if (d.announcement_source === "platform" && !d.story_project_id) e.story_project_id = "Select a story written on Cover Founder.";
    if (!d.headline.trim()) e.headline = "Add a headline for your announcement.";
    if (!d.announcement.trim()) e.announcement = "Choose a platform story or write your announcement.";
  }
  if (step === "contact") {
    if (!d.contact_name.trim()) e.contact_name = "Enter the primary contact’s name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(d.contact_email.trim())) e.contact_email = "Enter a valid contact email address.";
    for (const key of ["phone", "whatsapp"] as const) {
      if (!/^[+()0-9 .-]{7,40}$/.test(d[key]) || d[key].replace(/\D/g, "").length < 7) e[key] = `Enter a valid ${key === "phone" ? "phone" : "WhatsApp"} number, including the country code.`;
    }
    if (!d.logo_key) e.logo_key = "Upload your company logo before continuing.";
  }
  return e;
}

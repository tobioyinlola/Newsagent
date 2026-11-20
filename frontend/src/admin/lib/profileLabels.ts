// How the first-run answers read in the back office. The keys are what the server stores (see backend services/onboarding.py).
export const ROLE: Record<string, string> = { founder: "Founder or owner", marketing: "Marketing or communications", pr: "PR or media relations", agency: "Agency or consultant", executive: "Executive or manager", other: "Something else" };
export const SIZE: Record<string, string> = { solo: "Just them", "2-10": "2 to 10 people", "11-50": "11 to 50 people", "51-200": "51 to 200 people", "201-1000": "201 to 1,000 people", "1000+": "More than 1,000 people" };
export const GOAL: Record<string, string> = { credibility: "Look credible and established", customers: "Win more customers", investors: "Reach investors", hiring: "Attract talent and support hiring", launch: "Announce a launch or news", reputation: "Protect or improve reputation" };
export const HEARD: Record<string, string> = { search: "A web search", social: "Social media", friend: "A friend or colleague", event: "An event or conference", newsletter: "An email or newsletter", news: "An article or the news", ai: "An AI assistant", other: "Somewhere else" };
export const STATUS: Record<string, string> = { not_started: "Account from before the questions existed", pending: "Not answered yet", in_progress: "Partly answered", done: "Answered", skipped: "Skipped" };

export type CustomerProfile = { contact_name?: string; role?: string; phone?: string; website?: string; company_size?: string; goals?: string[]; heard_from?: string; heard_detail?: string };

/** The answers as label/value pairs, leaving out anything they did not answer. */
export function profileRows(p: CustomerProfile): [string, string][] {
  const rows: [string, string | undefined][] = [
    ["Goes by", p.contact_name],
    ["Role", p.role ? ROLE[p.role] ?? p.role : undefined],
    ["Phone", p.phone],
    ["Website", p.website],
    ["Team size", p.company_size ? SIZE[p.company_size] ?? p.company_size : undefined],
    ["Goals", p.goals?.length ? p.goals.map((g) => GOAL[g] ?? g).join(", ") : undefined],
    ["Heard about us from", p.heard_from ? HEARD[p.heard_from] ?? p.heard_from : undefined],
    ["In their words", p.heard_detail],
  ];
  return rows.filter((r): r is [string, string] => !!r[1]);
}

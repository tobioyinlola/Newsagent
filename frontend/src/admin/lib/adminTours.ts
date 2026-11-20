import type { TourDef, TourStep } from "../../components/tour/tourTypes";

// The back office's guided tours. Everyone gets the platform overview, which covers only the sections their role can open. The deeper
// tours appear for the people who can use that section. A step with `needs` is left out unless the person holds one of those permissions.
type AdminStep = TourStep & { needs?: string[] };
type AdminTour = Omit<TourDef, "steps"> & { steps: AdminStep[] };

const nav = (name: string, title: string, body: string, needs?: string[]): AdminStep => ({ target: `nav-${name}`, title, body, needs });

export const ADMIN_TOURS: AdminTour[] = [
  {
    id: "admin-platform",
    title: "Platform overview",
    summary: "Every section of the back office and what it is for.",
    steps: [
      { route: "/", title: "Welcome to the back office", body: "This is where the Cover Founder team runs the platform: customers and their money, the videos being made, press distribution and outreach, marketing, and the team itself. You only see the sections your role allows. This tour explains each one and what it is meant for." },
      nav("overview", "Overview", "Your control room. A quick read on sign-ups, revenue, videos in progress and anything that needs attention, such as content waiting for review or failed jobs.", ["overview.view"]),
      nav("customers", "Customers", "Every business that has signed up. Search by company or email, then open one to see their people, videos, payments and what they told us when they joined. Use it for support and to understand who is using the platform.", ["customers.view"]),
      nav("wallets", "Wallets", "Each customer's credit balance and its history. Use it to answer 'where did my credits go?' and to check balances.", ["customers.view"]),
      nav("revenue", "Revenue", "Money coming in: payments, who is paying and how much. Use it to track sales and spot who your paying customers are.", ["finance.view"]),
      nav("analytics", "Reports & analytics", "How the platform and customers' stories are performing, including visits and audience. Use it to see what is working.", ["operations.view"]),
      nav("distribution", "Distribution", "Press distribution requests that customers have paid for. See each request, which outlets it is going to, and mark outlets as published. Also where outlet prices, contacts and email wording are set.", ["operations.view"]),
      nav("outreach", "Outreach", "The email conversations with news outlets about paid distributions. Connect the Gmail it sends from, add outlet contacts, edit the email templates and approve replies the AI agent has drafted.", ["operations.view"]),
      nav("operations", "Operations", "Safety controls for the platform: the emergency stop for paid steps, and fallbacks when a vendor has an incident. Use it when something goes wrong with a provider or spending.", ["operations.view"]),
      nav("review", "Review queue", "Content held for a person to check before it goes any further. Approve or reject it here.", ["review.manage"]),
      nav("jobs", "Jobs", "The video-making steps running behind the scenes. See what is stuck or has failed and retry it.", ["operations.view"]),
      nav("costs", "Costs", "What vendors such as the AI presenter and rendering are costing, against their budgets. Use it to keep spend under control.", ["finance.view"]),
      nav("news-desk", "News Desk", "Where the team prepares original reporting for Cover Founder News: source, rewrite, review, publish.", []),
      nav("marketing", "Marketing", "Email marketing: choose audiences (segments), write the copy, send campaigns and set up automatic welcome and follow-up sequences. People who opted out are never emailed.", ["marketing.view"]),
      nav("presenter", "Presenter clips", "The library of AI-presenter clips used in customers' videos. Add, check and manage them.", ["presenter.manage"]),
      nav("billing", "Credits", "Add credits to a customer's wallet by hand, for example after a bank transfer, and review pending transfers.", ["finance.view"]),
      nav("setup", "Setup", "Platform settings: vendor budgets, spending limits, invites for new customers and suspensions.", ["customers.manage", "finance.view"]),
      nav("team", "Team", "Who can use this back office, and exactly what each person can do. Invite people and give them a role.", ["team.manage"]),
      nav("audit", "Audit log", "A permanent record of every team action, newest first. It cannot be edited. Use it to see who changed what and when.", ["audit.view"]),
      nav("security", "Security", "Your own password and sign-in protection. Every team member has this.", []),
      { target: "tours-menu", title: "Tours are always here", body: "Open Guided tours any time to replay this overview or take a closer look at a section. Your progress is saved." },
    ],
  },
  {
    id: "admin-customers",
    title: "Working with customers",
    summary: "Find a customer and understand their account.",
    needs: ["customers.view"],
    steps: [
      { route: "/customers", target: "page", title: "The customer list", body: "Newest sign-ups first. Click a company name to open it. The search box finds companies by name or email." },
      { target: "customers-search", title: "Search", body: "Type part of a company name or an email address to narrow the list." },
      { target: "page", title: "Inside a customer", body: "Opening a customer shows their credits and spending, their people, their videos and their payments. It also shows what they told us when they signed up: their role, business, goals and how they heard about us, if they chose to answer." },
    ],
  },
  {
    id: "admin-distribution",
    title: "Distribution, step by step",
    summary: "How a paid request becomes a placement.",
    needs: ["operations.view"],
    steps: [
      { route: "/distribution", target: "page", title: "Paid requests land here", body: "When a customer pays to distribute their story, it appears here with the outlets they chose, the total charged, and the materials they submitted." },
      { target: "page", title: "Tell the team and the outlets", body: "In Notification and outlet settings, set who in the team is emailed about each sale, and each outlet's price, logo and picture rules, and contact email. Outlets with a contact are emailed automatically through Outreach." },
      { target: "page", title: "Follow each placement", body: "Open a request to update each outlet's status as it moves along, and to see the emails that were sent. When an outlet publishes, mark it so the customer sees it." },
    ],
  },
  {
    id: "admin-outreach",
    title: "Outreach to outlets",
    summary: "Connect Gmail, add contacts, edit the emails.",
    needs: ["operations.view"],
    steps: [
      { route: "/outreach", target: "outreach-tab-inbox", title: "Conversations", body: "Every email thread with an outlet. Replies land here, and anything the AI agent has drafted waits for your approval before it is sent." },
      { target: "outreach-tab-mailbox", title: "Mailbox", body: "Connect the Gmail address everything is sent from and replies come back to. Nothing is sent until a mailbox is connected." },
      { target: "outreach-tab-settings", title: "Templates and settings", body: "Edit the email templates, with a sample preview, and choose how fast the emails go out and what the AI agent may do on its own." },
      { target: "outreach-tab-contacts", title: "Contacts", body: "Add contact emails for outlets. Outlets with a paid request but no contact appear here so you can fill them in, and their conversations then start by themselves." },
    ],
  },
  {
    id: "admin-team",
    title: "Your team and access",
    summary: "Invite people and control what they can do.",
    needs: ["team.manage"],
    steps: [
      { route: "/team", target: "page", title: "Who has access", body: "Everyone who can use the back office, with their role. Owners always have full access." },
      { target: "page", title: "Invite and set roles", body: "Invite someone by email and choose a role, or build a custom role by ticking exactly what it may do. You cannot give out more access than you hold. Changes apply straight away." },
    ],
  },
];

/** The tours this person can take, with the steps their role allows. */
export function toursFor(can: (...permissions: string[]) => boolean, showOutreach: boolean): TourDef[] {
  const allowed = (needs?: string[]) => !needs || needs.length === 0 || can(...needs);
  return ADMIN_TOURS.filter((t) => allowed(t.needs) && (showOutreach || t.id !== "admin-outreach"))
    .map((t) => ({ ...t, steps: t.steps.filter((s) => allowed(s.needs) && (showOutreach || s.target !== "nav-outreach")) }))
    .filter((t) => t.steps.length > 0);
}

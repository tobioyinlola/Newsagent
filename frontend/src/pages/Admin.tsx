import { useState } from "react";
import { Audit } from "../components/admin/Audit";
import { BillingAdmin } from "../components/admin/BillingAdmin";
import { Costs } from "../components/admin/Costs";
import { JobsTab } from "../components/admin/JobsTab";
import { Overview } from "../components/admin/Overview";
import { Review } from "../components/admin/Review";
import { Setup } from "../components/admin/Setup";

const TABS = [
  { id: "overview", label: "Overview", el: <Overview /> },
  { id: "review", label: "Review queue", el: <Review /> },
  { id: "jobs", label: "Jobs", el: <JobsTab /> },
  { id: "costs", label: "Costs", el: <Costs /> },
  { id: "billing", label: "Billing", el: <BillingAdmin /> },
  { id: "setup", label: "Setup", el: <Setup /> },
  { id: "audit", label: "Audit log", el: <Audit /> },
] as const;

export function Admin() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("overview");
  return (
    <>
      <h1 className="text-2xl font-bold">Operator console</h1>
      <div role="tablist" aria-label="Operator sections" className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <button key={t.id} role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} onClick={() => setTab(t.id)}
            className={`rounded-t px-3 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-purple ${tab === t.id ? "border-b-2 border-brand-purple text-ink" : "text-muted hover:bg-paper"}`}>{t.label}</button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="space-y-4">{TABS.find((t) => t.id === tab)!.el}</div>
    </>
  );
}

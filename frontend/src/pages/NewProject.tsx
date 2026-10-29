import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { OutOfCredits } from "../components/OutOfCredits";
import { PresenterPicker } from "../components/PresenterPicker";
import { Button, Card, ErrorBox, Field, inputCls } from "../components/ui";

const KINDS: [string, string, string][] = [
  ["product_launch", "Product launch", "A new product, feature or version is going live."],
  ["funding_round", "Funding round", "You raised money, or closed a round."],
  ["partnership", "Partnership", "A deal or collaboration with another company."],
  ["hiring", "Hiring", "You are growing the team."],
  ["milestone", "Milestone", "Customers, revenue, a launch in a new country."],
  ["other", "Something else", "Any other news about your business."],
];

// Step 1 of the guided flow: what you are announcing, who is presenting. Then the AI interview opens straight away.
export function NewProject() {
  const nav = useNavigate();
  const [kind, setKind] = useState("product_launch");
  const [details, setDetails] = useState("");
  const [founder, setFounder] = useState("");
  const [role, setRole] = useState("");
  const [site, setSite] = useState("");
  const [presenter, setPresenter] = useState("");
  const m = useMutation({
    mutationFn: async () => {
      const label = KINDS.find((k) => k[0] === kind)?.[1] ?? "Announcement";
      const p = await unwrap(api.POST("/v1/projects", { body: { brief_text: `${details.trim()}\n\nAnnouncement type: ${label}.`, website_url: site.trim() ? (/^https?:\/\//i.test(site.trim()) ? site.trim() : `https://${site.trim()}`) : null, region: "NG", voice_accent: "british", founder_name: founder.trim(), founder_title: role.trim(), anchor_id: presenter || null, flow: "guided", announcement_type: kind } }));
      await unwrap(api.POST("/v1/projects/{project_id}/guided/start", { params: { path: { project_id: p.id } } }));
      return p;
    },
    onSuccess: (p) => nav(`/ai-newsroom/${p.id}`),
  });
  const summary = useQuery({ queryKey: ["billing-summary"], queryFn: () => unwrap(api.GET("/v1/billing/summary")) });
  // out of credits: nothing to start. The popup explains and sends them to buy more.
  if (summary.data && summary.data.videos_left < 1) return <OutOfCredits forced />;
  return (
    <Card title="Tell us about your announcement">
      <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <fieldset className="space-y-2">
          <legend className="text-sm font-semibold">What are you announcing?</legend>
          <div role="radiogroup" aria-label="Announcement type" className="grid gap-2 sm:grid-cols-3">
            {KINDS.map(([id, label, hint]) => (
              <button key={id} type="button" role="radio" aria-checked={kind === id} onClick={() => setKind(id)}
                className={`rounded-sm border-2 p-3 text-left text-sm ${kind === id ? "border-brand-purple bg-lilac" : "border-ink bg-white"}`}>
                <span className="block font-bold">{label}</span><span className="text-muted">{hint}</span>
              </button>
            ))}
          </div>
        </fieldset>
        <Field label="Tell us the key details" hint="Who you are, what is happening, who it is for, and any facts you want featured (amounts, dates, names). A few sentences is enough. At least 20 characters.">
          {(id) => <textarea id={id} required minLength={20} maxLength={4000} rows={6} className={inputCls} value={details} onChange={(e) => setDetails(e.target.value)} />}
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Your name" hint="Our AI interviewer greets you by name.">{(id) => <input id={id} required maxLength={200} className={inputCls} value={founder} onChange={(e) => setFounder(e.target.value)} />}</Field>
          <Field label="Your role">{(id) => <input id={id} maxLength={200} className={inputCls} placeholder="CEO, Acme" value={role} onChange={(e) => setRole(e.target.value)} />}</Field>
        </div>
        <Field label="Website (optional)">{(id) => <input id={id} type="text" inputMode="url" autoComplete="url" className={inputCls} value={site} onChange={(e) => setSite(e.target.value)} placeholder="yourbusiness.com" />}</Field>
        <PresenterPicker value={presenter} onChange={setPresenter} />
        <p className="text-sm text-muted">Next, our AI interviewer asks you a few questions on camera (about 4 minutes). Then we write your news story and you check it. Nothing is made until you approve it.</p>
        <ErrorBox error={m.error} />
        <Button type="submit" disabled={m.isPending}>{m.isPending ? "Getting your interview ready…" : "Continue to the interview"}</Button>
      </form>
    </Card>
  );
}

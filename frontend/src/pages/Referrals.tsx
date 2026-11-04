import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox } from "../components/ui";

type Overview = { url: string; percent: string; completed_referrals: number; earned_credits: string; referrals: { id: string; business: string; credits: string; status: string; created_at: string }[] };
const credits = (n: number) => (n === 1 ? "credit" : "credits");
const money = (n: number) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function Referrals() {
  const q = useQuery({ queryKey: ["referrals"], queryFn: async () => unwrap(api.GET("/v1/referrals")) as Promise<Overview>, refetchInterval: 30000 });
  const qc = useQueryClient();
  useEffect(() => { if (q.dataUpdatedAt) void qc.invalidateQueries({ queryKey: ["me"] }); }, [q.dataUpdatedAt, qc]);
  const [message, setMessage] = useState("");
  const copy = async () => {
    if (!q.data) return;
    try { await navigator.clipboard.writeText(q.data.url); setMessage("Referral link copied."); }
    catch { setMessage("Select and copy your referral link from the field below."); }
  };
  const share = async () => {
    if (!q.data) return;
    try {
      if (navigator.share) await navigator.share({ title: "Join me on Cover Founder", text: "Tell your business story on Cover Founder.", url: q.data.url });
      else await copy();
    } catch (error) { if (!(error instanceof DOMException && error.name === "AbortError")) setMessage("Sharing is unavailable. You can copy your link instead."); }
  };
  return <div className="min-w-0 space-y-6">
    <header className="rounded-xl border-2 border-ink bg-lime-tint p-6 sm:p-8"><h1 className="text-3xl sm:text-4xl">Invite a business. Earn credits.</h1><p className="mt-4 max-w-2xl leading-relaxed">Share your personal referral link. Whenever a business that signed up through it buys credits, we add <strong>{q.data ? Number(q.data.percent) : 5}%</strong> of the credits they buy to your wallet. It happens on every purchase they make.</p><p className="mt-2 text-sm text-muted">For example, if they buy 100 credits you earn {q.data ? money(Number(q.data.percent)) : 5}. Use your credits like any other wallet credit for videos and distribution. What they buy is not reduced: you earn it on top.</p></header>
    <ErrorBox error={q.error} />
    {q.isLoading && <p role="status">Loading your referral link…</p>}
    {q.data && <>
      <div className="grid gap-4 sm:grid-cols-2"><Card title="Businesses referred"><p className="text-4xl font-bold">{q.data.completed_referrals}</p><p className="mt-2 text-sm text-muted">Businesses that signed up through your link</p></Card><Card title="Credits earned"><p className="text-4xl font-bold">{money(Number(q.data.earned_credits))}</p><p className="mt-2 text-sm text-muted">{q.data ? Number(q.data.percent) : 5}% of what they buy, added to your wallet</p></Card></div>
      <Card title="Your referral link"><label className="block text-sm font-semibold" htmlFor="referral-link">Share this link with another business</label><input id="referral-link" readOnly value={q.data.url} onFocus={e => e.target.select()} className="mt-2 min-h-12 w-full min-w-0 rounded-lg border border-ink bg-paper p-3 text-sm" /><div className="mt-4 flex flex-wrap gap-3"><Button onClick={() => void copy()}>Copy link</Button><Button variant="secondary" onClick={() => void share()}>Share link</Button></div>{message && <p role="status" className="mt-3 text-sm">{message}</p>}<p className="mt-3 text-xs text-muted">You earn on every purchase a referred business makes. Existing accounts, your own account, and workspace invitation links do not qualify.</p></Card>
      <Card title="Your referrals"><p className="mb-4 text-sm text-muted">Businesses appear here when they sign up. What each one has earned you grows with every purchase they make. Showing your latest 100.</p>{q.data.referrals.length ? <ul className="divide-y divide-line">{q.data.referrals.map(r => <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div className="min-w-0"><p className="break-words font-semibold">{r.business}</p><p className="mt-1 text-xs text-muted">{new Date(r.created_at).toLocaleDateString()} · Signed up</p></div><span className="rounded-full bg-lime-tint px-3 py-2 text-sm font-bold">{Number(r.credits) > 0 ? `+${money(Number(r.credits))} ${credits(Number(r.credits))} earned` : "No purchases yet"}</span></li>)}</ul> : <div className="rounded-lg border border-dashed border-line bg-paper p-6 text-center"><p className="font-semibold">Your first referral starts with a share.</p><p className="mt-2 text-sm text-muted">Send your link to a business owner who has a story to tell.</p></div>}</Card>
    </>}
  </div>;
}

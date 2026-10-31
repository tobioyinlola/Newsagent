import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox } from "../components/ui";

type Overview = { url: string; reward_credits: string; completed_referrals: number; earned_credits: string; referrals: { id: string; business: string; credits: string; status: string; created_at: string }[] };

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
    <header className="rounded-xl border-2 border-ink bg-lime-tint p-6 sm:p-8"><h1 className="text-3xl sm:text-4xl">Invite a business. Earn a credit.</h1><p className="mt-4 max-w-2xl leading-relaxed">Share your personal referral link. When a new business signs up through it and verifies its email, we'll add 1 credit to your workspace wallet.</p><p className="mt-2 text-sm text-muted">Use it like any other wallet credit for videos and other credit-based services. No purchase is required to earn the reward.</p></header>
    <ErrorBox error={q.error} />
    {q.isLoading && <p role="status">Loading your referral link…</p>}
    {q.data && <>
      <div className="grid gap-4 sm:grid-cols-2"><Card title="Businesses referred"><p className="text-4xl font-bold">{q.data.completed_referrals}</p><p className="mt-2 text-sm text-muted">Verified new business signups</p></Card><Card title="Credits earned"><p className="text-4xl font-bold">{Number(q.data.earned_credits)}</p><p className="mt-2 text-sm text-muted">Added to your shared workspace wallet</p></Card></div>
      <Card title="Your referral link"><label className="block text-sm font-semibold" htmlFor="referral-link">Share this link with another business</label><input id="referral-link" readOnly value={q.data.url} onFocus={e => e.target.select()} className="mt-2 min-h-12 w-full min-w-0 rounded-lg border border-ink bg-paper p-3 text-sm" /><div className="mt-4 flex flex-wrap gap-3"><Button onClick={() => void copy()}>Copy link</Button><Button variant="secondary" onClick={() => void share()}>Share link</Button></div>{message && <p role="status" className="mt-3 text-sm">{message}</p>}<p className="mt-4 text-xs leading-relaxed text-muted">Rewards apply once per new business after email verification. Existing accounts, your own account, and workspace invitation links do not qualify.</p></Card>
      <Card title="Your referrals"><p className="mb-4 text-sm text-muted">Completed referrals appear here after signup. Showing your latest 100 referrals.</p>{q.data.referrals.length ? <ul className="divide-y divide-line">{q.data.referrals.map(r => <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div className="min-w-0"><p className="break-words font-semibold">{r.business}</p><p className="mt-1 text-xs text-muted">{new Date(r.created_at).toLocaleDateString()} · Verified signup</p></div><span className="rounded-full bg-lime-tint px-3 py-2 text-sm font-bold">+{Number(r.credits)} credit · Added</span></li>)}</ul> : <div className="rounded-lg border border-dashed border-line bg-paper p-6 text-center"><p className="font-semibold">Your first referral starts with a share.</p><p className="mt-2 text-sm text-muted">Send your link to a business owner who has a story to tell.</p></div>}</Card>
    </>}
  </div>;
}

import { useState } from "react";
import { Link } from "react-router-dom";
import { type Distribution, distributionStatus } from "../lib/distribution";
import { downloadAuthed } from "../lib/download";
import { Button, Card, ErrorBox } from "./ui";

export function DistributionProgress({ request }: { request: Distribution }) {
  const [error, setError] = useState<unknown>(null);
  const placements = request.placements ?? [];
  const published = placements.filter(p => p.status === "published").length;
  return <div className="space-y-5">
    <Card title="Distribution request confirmed">
      <p>Your request is {distributionStatus(request.status).toLowerCase()}. Payment confirmed: {request.total_credits} credits.</p>
      <p className="mt-2">{request.status === "completed" ? "Your selected outlet placements are published. Use the links below to view each post." : request.status === "in_progress" ? "Our team is coordinating your selected publications. We'll email you as each post goes live." : "Someone from the Cover Founder team will reach out within the next 24 hours."}</p>
      <p className="mt-2 text-sm text-muted">{request.email_sent ? "Confirmation email sent. Your payment breakdown is included." : "Your request and payment are saved. You can download your receipt below while our team handles email delivery."}</p>
      <h3 className="mt-4 font-bold">{request.data.headline}</h3>
    </Card>
    <Card title="Outlet progress and published links">
      <p className="mb-4 text-sm text-muted">{published} of {placements.length} outlets published. Each publication is tracked separately.</p>
      <ul className="space-y-3">{placements.map(p => <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line p-4"><div><h3 className="font-semibold">{p.name}</h3><p className="mt-1 text-sm">{distributionStatus(p.status)} · {p.credits} credits</p>{p.published_at && <p className="text-xs text-muted">Published {new Date(p.published_at).toLocaleDateString()}</p>}</div>{p.published_url && <a className="min-h-11 rounded border-2 border-ink px-4 py-2 text-sm font-bold" href={p.published_url} target="_blank" rel="noopener noreferrer">View published post<span className="sr-only"> on {p.name}</span></a>}</li>)}</ul>
      {!placements.length && <p className="text-sm text-muted">Your team is preparing the outlet progress details.</p>}
    </Card>
    {request.invoice && <Card title="Payment receipt">
      <p className="break-all text-sm font-semibold">{request.invoice.number}</p><p className="mt-2 text-sm">{request.invoice.payment_method} · {request.invoice.status === "no_charge" ? "No credit charge" : "Paid"}</p>
      <ul className="my-4 space-y-3 text-sm">{request.invoice.items.map(i => <li key={i.id} className="flex flex-wrap justify-between gap-2 border-b border-line pb-2"><span>{i.name}<span className="block text-xs text-muted">Placement {i.base_credits ?? i.credits} · Logo {i.logo_fee ?? 0} · Pictures {i.picture_fee ?? 0} credits</span></span><strong>{i.credits} credits</strong></li>)}</ul>
      <p className="mb-4 font-bold">Total paid: {request.invoice.total_credits} credits</p><Button variant="secondary" onClick={() => { setError(null); void downloadAuthed(`/v1/distribution/${request.id}/invoice`, `${request.invoice!.number}.html`).catch(setError); }}>Download receipt</Button><ErrorBox error={error} />
    </Card>}
    <Link to="/distribution/request" className="inline-block min-h-11 py-2 underline">All requests</Link>
  </div>;
}

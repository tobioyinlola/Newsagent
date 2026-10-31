import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Notice } from "../components/ui";
import { DistributionReturnLink } from "../components/DistributionReturnLink";

export type TransferPayment = { id: string; status: string; currency: "USD" | "NGN"; amount: string; amount_usd: string; credits: string; ngn_per_usd: string | null; reference: string; review_status: string; reason: string; submitted_at: string | null; reviewed_at: string | null; payment_reference: string | null; bank: Record<string, string | boolean>; receipt: { id: string; filename: string; content_type: string; url: string } | null };
const money = (n: string, currency: string) => Number(n).toLocaleString(currency === "NGN" ? "en-NG" : undefined, { style: "currency", currency });

export function TransferCheckout() {
  const { checkoutId = "" } = useParams(); const qc = useQueryClient();
  const q = useQuery({ queryKey: ["transfer-checkout", checkoutId], queryFn: () => unwrap(api.GET("/v1/billing/transfer/{id}", { params: { path: { id: checkoutId } } })) as Promise<TransferPayment>, refetchInterval: query => query.state.data?.status === "pending_review" ? 15000 : false });
  const payment = q.data; const paid = payment?.status === "paid"; const pending = payment?.status === "pending_review";
  const [showUpload, setShowUpload] = useState(false); const [proofId, setProofId] = useState(""); const [filename, setFilename] = useState("");
  const [senderReference, setSenderReference] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [message, setMessage] = useState("");
  useEffect(() => { if (paid) for (const key of ["me", "billing-summary", "ledger", "payment-checkouts"]) void qc.invalidateQueries({ queryKey: [key] }); }, [paid, qc]);
  useEffect(() => { if (payment?.status === "rejected") { setProofId(""); setShowUpload(true); } }, [payment?.status]);
  const copy = async (value: string) => { try { await navigator.clipboard.writeText(value); setMessage("Copied."); } catch { setMessage("Select and copy the transfer details below."); } };
  const upload = async (file: File) => {
    setError(null); setProofId(""); setFilename("");
    if (!["image/png", "image/jpeg", "application/pdf"].includes(file.type) || !file.size || file.size > 5 * 1024 * 1024) { setError(new Error("Choose a PNG, JPEG or PDF receipt up to 5 MB.")); return; }
    setBusy(true);
    try {
      const signed = await unwrap(api.POST("/v1/billing/transfer/{id}/uploads", { params: { path: { id: checkoutId } }, body: { filename: file.name, content_type: file.type as "image/png" | "image/jpeg" | "application/pdf", size_bytes: file.size } })) as { proof_id: string; upload_url: string };
      const result = await fetch(signed.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
      if (!result.ok) throw new Error("Receipt upload failed. Please try again.");
      await unwrap(api.POST("/v1/billing/transfer/{id}/uploads/confirm", { params: { path: { id: checkoutId } }, body: { proof_id: signed.proof_id } }));
      setProofId(signed.proof_id); setFilename(file.name);
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const submit = async () => {
    if (!proofId || busy) return;
    setBusy(true); setError(null);
    try {
      await unwrap(api.POST("/v1/billing/transfer/{id}/submit", { params: { path: { id: checkoutId } }, body: { proof_id: proofId, sender_reference: senderReference } }));
      await q.refetch(); await qc.invalidateQueries({ queryKey: ["payment-checkouts"] });
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return <div className="mx-auto max-w-2xl space-y-5 pb-8"><h1 className="text-2xl font-bold">Pay by bank transfer</h1><ErrorBox error={q.error ?? error} />{!payment && <p>Loading your transfer purchase…</p>}{payment && <>
    <Card title={paid ? "Payment confirmed" : "Your credit purchase"}><p className="text-3xl font-bold">{money(payment.amount, payment.currency)}</p><p className="mt-2 font-semibold">{Number(payment.credits)} credits</p>{payment.currency === "NGN" && <p className="mt-2 text-sm text-muted">{money(payment.amount_usd, "USD")} USD equivalent · ₦{Number(payment.ngn_per_usd).toLocaleString()} per $1. Your purchase rate is fixed.</p>}{paid && <div className="mt-4"><Notice tone="ok">Your payment has been approved and {Number(payment.credits)} credits have been added to your wallet.</Notice>{payment.payment_reference && <p className="mt-3 break-all text-sm">Bank reference: {payment.payment_reference}</p>}{payment.reviewed_at && <p className="mt-1 text-xs text-muted">Approved {new Date(payment.reviewed_at).toLocaleString()}</p>}</div>}</Card>
    {pending ? <Card title="Receipt submitted — awaiting approval"><Notice tone="info">Your receipt has been submitted. Your credits will be added in a few minutes once our team confirms the transfer.</Notice><p className="mt-3 text-sm text-muted">We’ve notified the team. Please don’t pay again. You’ll receive an email when the payment is approved.</p><Button className="mt-4" variant="secondary" onClick={() => void q.refetch()} disabled={q.isFetching}>Check approval status</Button></Card> : !paid && <>
      {payment.status === "rejected" && <Notice tone="warn">We couldn’t approve this receipt: {payment.reason} No credits were added. Check the details and upload a corrected receipt; contact the team before sending another payment.</Notice>}
      <Card title="Transfer instructions"><p className="mb-4 text-sm text-muted">Transfer the amount shown above to this {payment.currency} account. Include your unique narration so the team can match your payment.</p><dl className="space-y-4 text-sm">{[["Bank", "bank_name"], ["Payment recipient", "recipient_display_name"], ["Bank beneficiary name", "beneficiary_name"], ["Account label", "account_label"], ["Account number", "account_number"], ["Routing number", "routing_number"], ["SWIFT / BIC", "swift_code"], ["IBAN", "iban"], ["Bank address", "bank_address"]].map(([label, key]) => payment.bank[key] ? <div key={key} className="flex items-start justify-between gap-3"><div className="min-w-0"><dt className="text-muted">{label}</dt><dd className="mt-1 break-words font-semibold">{String(payment.bank[key])}</dd></div>{["account_number", "routing_number", "iban"].includes(key) && <button type="button" className="min-h-10 shrink-0 rounded border border-line px-3 text-xs font-bold" onClick={() => void copy(String(payment.bank[key]))}>Copy {label.toLowerCase()}</button>}</div> : null)}<div className="rounded-lg border border-ink bg-paper p-4"><dt className="font-bold">Transfer narration / reference</dt><dd className="mt-2 break-all font-mono">{payment.reference}</dd><button type="button" className="mt-3 min-h-10 rounded border border-ink px-3 text-xs font-bold" onClick={() => void copy(payment.reference)}>Copy narration</button></div></dl>{payment.bank.instructions && <p className="mt-4 whitespace-pre-wrap text-sm">{String(payment.bank.instructions)}</p>}<p className="mt-4 text-xs text-muted">Bank fees may apply. Your receipt is reviewed before credits are added.</p><Button className="mt-5" onClick={() => setShowUpload(true)}>I have paid</Button></Card>
      {showUpload && <Card title="Upload your payment receipt"><form className="space-y-4" onSubmit={e => { e.preventDefault(); void submit(); }}><label className="block text-sm font-semibold">Payment receipt (PNG, JPEG or PDF, up to 5 MB)<input className="mt-2 block w-full rounded-lg border border-dashed border-ink bg-paper p-4 font-normal" type="file" accept="image/png,image/jpeg,application/pdf" disabled={busy} onChange={e => { if (e.target.files?.[0]) void upload(e.target.files[0]); }} /></label>{filename && <p role="status" className="text-sm">Receipt uploaded: {filename}</p>}<label className="block text-sm font-semibold">Bank transaction reference (optional)<input className="mt-2 min-h-12 w-full rounded-lg border border-ink px-3 font-normal" maxLength={200} value={senderReference} onChange={e => setSenderReference(e.target.value)} /></label><p className="text-sm text-muted">We’ll check the transfer and notify you when your credits are added.</p><Button type="submit" disabled={busy || !proofId}>{busy ? "Checking receipt…" : "Submit receipt for approval"}</Button></form></Card>}
    </>}
    {payment.receipt && <a className="flex min-h-11 w-fit items-center text-sm font-semibold underline" href={payment.receipt.url} target="_blank" rel="noopener noreferrer">View submitted receipt</a>}
    {paid && <DistributionReturnLink />}
  </>}{message && <p role="status" className="text-sm">{message}</p>}<Link className="inline-flex min-h-11 items-center font-semibold underline" to="/billing">{paid ? "View wallet and history" : "Back to billing"}</Link></div>;
}

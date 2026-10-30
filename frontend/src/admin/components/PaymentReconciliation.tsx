import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, ErrorBox } from "../../components/ui";
import { getToken } from "../lib/auth";
import { useCan } from "../lib/can";

type Receipt = { id: string; transfer_id: string; amount_ngn: string; reference: string; narration: string; status: string; checkout_id: string | null; matched_by: string | null };
type Purchase = { id: string; company: string; provider: string; status: string; currency: string; amount: string; credits: string; claim?: { transfer_id: string; status: string } | null; error?: { message: string; code: string; http_status?: number; request_id?: string } | null };
type Report = { receipts: Receipt[]; checkouts: Purchase[] };
const button = "min-h-11 rounded border-2 border-ink bg-brand-green px-3 py-2 text-sm font-bold text-ink disabled:opacity-50";
const input = "mt-2 min-h-12 w-full rounded border border-ink bg-white p-3";
async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/${path}`, { method, headers: { Authorization: `Bearer ${getToken() ?? ""}`, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to reconcile this payment. Review the receipt and selected purchase.");
  return data;
}

export function PaymentReconciliation() {
  const canManage = useCan()("finance.manage");
  const q = useQuery({ queryKey: ["payment-reconciliation", getToken()], queryFn: () => request<Report>("admin/payment-reconciliation"), refetchInterval: 15000 });
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [message, setMessage] = useState("");
  const run = async (fn: () => Promise<unknown>, success: string) => { setBusy(true); setError(null); setMessage(""); try { await fn(); await q.refetch(); setMessage(success); } catch (e) { setError(e); } finally { setBusy(false); } };
  return <Card title="Payment reconciliation">
    <p className="text-sm text-muted">Review pending purchases and verified bank receipts. A missing narration requires an explicit customer match. Card status checks do not submit another card charge.</p>
    <div className="mt-4 flex flex-wrap gap-3"><button className={button} disabled={busy || !canManage} onClick={() => void run(() => request("admin/payment-reconciliation/sync", "POST"), "Latest bank receipts verified with Nuvion.")}>Refresh bank receipts from Nuvion</button><button className={button} disabled={busy || q.isFetching} onClick={() => void q.refetch()}>Refresh payment list</button></div>
    <ErrorBox error={error ?? q.error} />{message && <p role="status" className="mt-3 text-sm">{message}</p>}
    <h3 className="mt-5 font-bold">Bank receipts</h3>
    <div className="mt-3 max-h-[38rem] space-y-3 overflow-y-auto">{q.data?.receipts.map(receipt => <details key={receipt.id} className="rounded border border-line p-4"><summary className="cursor-pointer break-words font-semibold">NGN {Number(receipt.amount_ngn).toLocaleString()} · {receipt.status === "matched" ? "Matched" : "Needs matching"} · {receipt.reference || receipt.transfer_id}</summary><p className="mt-3 break-words text-sm">Bank narration: {receipt.narration || "Not supplied"}</p><p className="mt-1 break-all text-xs text-muted">Provider transfer: {receipt.transfer_id}</p>{receipt.status === "matched" ? <p className="mt-3 text-sm">Purchase {receipt.checkout_id} · Matched by {receipt.matched_by}</p> : <MatchReceipt receipt={receipt} purchases={q.data?.checkouts ?? []} disabled={busy || !canManage} submit={(body) => run(() => request(`admin/payment-reconciliation/receipts/${receipt.id}/match`, "POST", body), "Transfer matched. Purchase marked paid and wallet credits applied once.")} />}</details>)}{!q.data?.receipts.length && <p className="text-sm text-muted">No verified receipts recorded yet. Refresh from Nuvion to recover earlier bank transfers.</p>}</div>
    <h3 className="mt-6 font-bold">Recent payment attempts</h3><div className="mt-3 max-h-96 overflow-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Customer / purchase</th><th className="p-2">Amount</th><th className="p-2">Status / issue</th><th className="p-2">Action</th></tr></thead><tbody>{q.data?.checkouts.map(p => <tr key={p.id} className="border-t border-line"><td className="p-2"><strong>{p.company}</strong><p className="break-all text-xs text-muted">{p.id}</p><p className="text-xs">{p.provider === "nuvion_bank" ? "Bank transfer" : "Card"}</p></td><td className="whitespace-nowrap p-2">{p.currency} {p.amount}<p className="text-xs">{p.credits} credits</p></td><td className="min-w-48 p-2">{p.status}{p.claim && <p>Receipt claim: {p.claim.status}</p>}{p.error && <><p>{p.error.message}</p><p className="mt-1 break-all text-xs text-muted">{p.error.code}{p.error.request_id ? ` · Support request: ${p.error.request_id}` : ""}</p></>}</td><td className="p-2">{p.status === "pending" && <button className={button} disabled={busy || !canManage} onClick={() => void run(() => request(`admin/payment-reconciliation/checkouts/${p.id}/recheck`, "POST"), "Payment status checked with Nuvion.")}>Recheck payment</button>}</td></tr>)}</tbody></table></div>
  </Card>;
}

function MatchReceipt({ receipt, purchases, disabled, submit }: { receipt: Receipt; purchases: Purchase[]; disabled: boolean; submit: (body: unknown) => Promise<void> }) {
  const [checkout, setCheckout] = useState(""); const [reason, setReason] = useState(""); const [confirmed, setConfirmed] = useState(false);
  const options = purchases.filter(p => p.provider === "nuvion_bank" && p.status === "pending" && p.currency === "NGN" && Number(p.amount) === Number(receipt.amount_ngn));
  return <form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); void submit({ checkout_id: checkout, ownership_confirmed: confirmed, reason: reason.trim() }); }}>
    <label className="block text-sm font-semibold">Assign to purchase<select aria-label="Assign to purchase" className={input} required disabled={disabled} value={checkout} onChange={e => { setCheckout(e.target.value); setConfirmed(false); }}><option value="">Select the verified customer and purchase</option>{options.map(p => <option key={p.id} value={p.id}>{p.company} · {p.credits} credits · {p.id.slice(-8)}{p.claim?.transfer_id === receipt.transfer_id ? " · Customer submitted this receipt" : ""}</option>)}</select></label>
    <label className="block text-sm font-semibold">Matching reason<textarea className={input} required minLength={10} maxLength={1000} disabled={disabled} value={reason} onChange={e => setReason(e.target.value)} placeholder="Explain how payer ownership and the purchase were confirmed." /></label>
    <label className="flex items-start gap-2 text-sm"><input type="checkbox" required checked={confirmed} disabled={disabled} onChange={e => setConfirmed(e.target.checked)} /><span>I verified this transfer belongs to the selected customer and purchase.</span></label>
    <button className={button} disabled={disabled || !checkout || !confirmed || reason.trim().length < 10}>Match transfer and apply credits</button>
  </form>;
}

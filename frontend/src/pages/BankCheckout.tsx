import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Notice } from "../components/ui";

type BankPayment = { checkout_id: string; amount_usd: string; amount_ngn: string; ngn_per_usd: string; credits: string; status: string; reference: string; claim?: { status: string; reference: string } | null;
  bank: { account_number: string; bank_name: string; beneficiary_name: string | null; account_label: string } };
const ngn = (value: string) => Number(value).toLocaleString("en-NG", { style: "currency", currency: "NGN" });

export function BankCheckout() {
  const { checkoutId = "" } = useParams();
  const qc = useQueryClient();
  const [claimReference, setClaimReference] = useState("");
  const [claimBusy, setClaimBusy] = useState(false);
  const [claimError, setClaimError] = useState<unknown>(null);
  const [copied, setCopied] = useState("");
  const [copyError, setCopyError] = useState(false);
  const query = useQuery({ queryKey: ["bank-checkout", checkoutId], queryFn: () => unwrap(api.GET("/v1/billing/bank/{id}", { params: { path: { id: checkoutId } } })) as Promise<BankPayment>, retry: false,
    refetchInterval: q => q.state.data?.status === "pending" ? 15000 : false });
  const payment = query.data;
  const paid = payment?.status === "paid";
  useEffect(() => {
    if (paid) for (const key of ["me", "billing-summary", "ledger", "payment-checkouts"]) void qc.invalidateQueries({ queryKey: [key] });
  }, [paid, qc]);
  const copy = async (label: string, value: string) => {
    setCopyError(false);
    try { await navigator.clipboard.writeText(value); setCopied(`${label} copied`); }
    catch { setCopyError(true); }
  };
  return <div className="mx-auto max-w-2xl space-y-5 pb-8">
    <h1 className="text-2xl font-bold">Pay by bank transfer</h1>
    <ErrorBox error={query.error} />
    {!payment && <p>{query.isFetching ? "Loading your transfer details…" : "We couldn't load this payment. Try checking its status again."}</p>}
    {payment && <>
      <Card title={paid ? "Payment confirmed" : "Your purchase"}>
        <p className="text-3xl font-bold">{ngn(payment.amount_ngn)}</p>
        <p className="mt-2">{payment.credits} credits · ${Number(payment.amount_usd).toFixed(2)} USD package</p>
        <p className="mt-2 text-sm text-muted">₦{Number(payment.ngn_per_usd).toLocaleString()} per $1. This checkout keeps that rate.</p>
        {paid && <div className="mt-4"><Notice tone="ok">Your transfer is verified and the credits have been added to your wallet.</Notice></div>}
      </Card>
      {!paid && <Card title="Transfer instructions">
        <ol className="mb-5 list-inside list-decimal space-y-2 text-sm"><li>Open your Nigerian banking app and transfer the exact amount below.</li><li>Copy the payment reference into the transfer narration or description, with no extra text.</li><li>Return here to check your payment. Credits appear after Nuvion verifies the matching transfer.</li></ol>
        <dl className="space-y-4">
          {[{ label: "Amount", value: ngn(payment.amount_ngn), copy: payment.amount_ngn }, { label: "Bank", value: payment.bank.bank_name }, { label: "Account number", value: payment.bank.account_number, copy: payment.bank.account_number },
            ...(payment.bank.beneficiary_name ? [{ label: "Account name", value: payment.bank.beneficiary_name }] : [{ label: "Receiving account label", value: payment.bank.account_label }]),
            { label: "Payment reference / narration", value: payment.reference, copy: payment.reference }].map(row => <div key={row.label} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line p-3"><div className="min-w-0"><dt className="text-sm text-muted">{row.label}</dt><dd className="mt-1 break-all font-semibold tabular-nums">{row.value}</dd></div>{row.copy && <Button variant="secondary" onClick={() => void copy(row.label, row.copy!)}>Copy {row.label.toLowerCase()}</Button>}</div>)}
        </dl>
        <p className="mt-3 text-sm text-muted">Confirm the beneficiary shown by your bank before sending. The receiving account label is not a bank name-verification result.</p>
        <div className="mt-4"><Notice tone="warn">If your bank cannot include the full reference, changes it, or you send a different amount, automatic crediting may not work. Keep your receipt and contact support. Do not send the payment again while it is being checked.</Notice></div>
        <p className="mt-3 text-sm" role="status" aria-live="polite">{copyError ? "Copy failed. Select and copy the value above manually." : copied}</p>
      </Card>}
    </>}
    {payment && !paid && <Card title="Already transferred but not credited?">
      {payment.claim?.status === "pending_review" ? <Notice tone="ok">We verified the bank transfer you submitted. Our team is reviewing the payment match. You do not need to pay again.</Notice> : <form className="space-y-4" onSubmit={e => { e.preventDefault(); setClaimBusy(true); setClaimError(null); void unwrap(api.POST("/v1/billing/bank/{id}/claim", { params: { path: { id: checkoutId } }, body: { reference: claimReference.trim() } })).then(() => query.refetch()).catch(setClaimError).finally(() => setClaimBusy(false)); }}>
        <p className="text-sm text-muted">If your bank changed the narration, enter the transaction reference from your bank receipt. We will verify the received transfer and send it to the team for matching.</p>
        <label className="block text-sm font-semibold">Bank transaction reference<input className="mt-2 min-h-12 w-full rounded border border-ink p-3" required minLength={10} maxLength={200} pattern="[A-Za-z0-9_-]+" value={claimReference} onChange={e => setClaimReference(e.target.value)} autoComplete="off" disabled={claimBusy} /></label>
        <Button type="submit" disabled={claimBusy}>{claimBusy ? "Verifying transfer…" : "Submit transfer for review"}</Button><ErrorBox error={claimError} />
      </form>}
    </Card>}
    {!paid && <Button variant="secondary" onClick={() => void query.refetch()} disabled={query.isFetching}>{query.isFetching ? "Checking…" : "Check transfer status"}</Button>}
    <Link className="block min-h-11 py-2 font-semibold underline" to="/billing">{paid ? "View wallet and continue" : "Back to billing"}</Link>
  </div>;
}

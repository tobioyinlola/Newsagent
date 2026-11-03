import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { DistributionReturnLink } from "../components/DistributionReturnLink";
import { Button, Card, ErrorBox, Notice } from "../components/ui";

const credits = (v: string) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money = (v: string) => Number(v).toLocaleString(undefined, { style: "currency", currency: "USD" });
const REVERSED: Record<string, string> = {
  refunded: "This payment was refunded. The refund goes back to the card you paid with, and the matching credits were taken off your wallet.",
  partially_refunded: "Part of this payment was refunded. The refund goes back to your card, and the matching credits were taken off your wallet.",
  disputed: "Your bank has opened a dispute on this payment, so the matching credits are on hold while it is reviewed.",
  charged_back: "Your bank reversed this payment, so the matching credits were removed from your wallet.",
};
const WAIT_MS = 120_000; // how long to keep checking before suggesting the customer look again later

type Payment = { checkout_id: string; amount_usd: string; credits: string; status: string; sandbox: boolean; credit_balance?: string | null };

/** The pop-up shown the moment a payment is confirmed. */
function PaymentSuccessModal({ payment, onClose }: { payment: Payment; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="pay-ok-title" className="w-full max-w-md rounded-md border-2 border-ink bg-white p-6 text-center shadow-xl">
        <div aria-hidden="true" className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border-2 border-ink bg-brand-green text-3xl font-bold">✓</div>
        <h2 id="pay-ok-title" className="mt-4 text-2xl font-bold">Your payment was successful</h2>
        <p className="mt-3 text-lg">You paid <strong>{money(payment.amount_usd)}</strong> for <strong>{credits(payment.credits)} credits</strong>.</p>
        {payment.credit_balance != null && <p className="mt-1 text-muted">Your balance is now {credits(payment.credit_balance)} credits.</p>}
        <p className="mt-3 text-sm text-muted">We've emailed you a confirmation and your invoice.</p>
        {payment.sandbox && <p className="mt-2 text-xs text-muted">Test mode: no real money was taken.</p>}
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link to="/ai-newsroom/new" className="rounded-sm border-2 border-ink bg-brand-green px-5 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green">Make a video</Link>
          <Button variant="secondary" autoFocus onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  );
}

/** Where Stripe sends the customer back to. The page never decides anything: it asks our server, which asks Stripe. */
export function StripeReturn() {
  const { checkoutId = "" } = useParams();
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const [startedAt] = useState(() => Date.now());
  const [dismissed, setDismissed] = useState(false);
  const [closing] = useState({ done: false }); // backing out closes the session once; after that this page only checks the status
  const cancelled = params.get("cancelled") === "1";
  const query = useQuery({
    queryKey: ["stripe-checkout", checkoutId],
    queryFn: () => unwrap(cancelled && !closing.done ? (closing.done = true, api.POST("/v1/billing/stripe/{id}/cancel", { params: { path: { id: checkoutId } } })) : api.GET("/v1/billing/stripe/{id}", { params: { path: { id: checkoutId } } })) as Promise<Payment>,
    retry: false,
    refetchInterval: q => (q.state.data?.status === "pending" && Date.now() - startedAt < WAIT_MS ? 2000 : false),
  });
  const payment = query.data;
  const paid = payment?.status === "paid";
  useEffect(() => {
    if (paid) for (const key of ["me", "billing-summary", "ledger", "payment-checkouts"]) void qc.invalidateQueries({ queryKey: [key] });
  }, [paid, qc]);
  const waited = Date.now() - startedAt >= WAIT_MS;
  const showSuccess = paid && !dismissed && payment;

  return (
    <div className="max-w-xl">
      {showSuccess && <PaymentSuccessModal payment={payment} onClose={() => setDismissed(true)} />}
      <h1 className="text-2xl font-bold">Your payment</h1>
      <Card title={paid ? "Payment received" : payment?.status === "pending" ? "Confirming your payment…" : payment && REVERSED[payment.status] ? "Payment update" : "Payment not completed"}>
        <ErrorBox error={query.error} />
        {query.isLoading && <p role="status">Checking with Stripe…</p>}
        {payment && paid && <>
          <p className="text-lg"><strong>{credits(payment.credits)} credits</strong> were added to your workspace for {money(payment.amount_usd)}.</p>
          {payment.credit_balance != null && <p className="mt-2 text-sm text-muted">Your balance is now {credits(payment.credit_balance)} credits.</p>}
          <div className="mt-5 flex flex-wrap gap-3"><Link to="/ai-newsroom/new"><Button>Make a video</Button></Link><Link className="self-center font-semibold underline" to="/billing">Back to billing</Link></div>
          <DistributionReturnLink />
        </>}
        {payment?.status === "pending" && !waited && <p role="status" className="text-sm text-muted">This usually takes a few seconds. Please keep this page open. Your credits are added automatically as soon as the payment is confirmed.</p>}
        {payment?.status === "pending" && waited && <Notice tone="warn">We haven't had confirmation yet. If you completed the payment, your credits will be added automatically within a few minutes, and we'll email you. You can also check your balance on the billing page.</Notice>}
        {payment && REVERSED[payment.status] && <>
          <p>{REVERSED[payment.status]}</p>
          <div className="mt-5"><Link to="/billing"><Button>Back to billing</Button></Link></div>
        </>}
        {payment && (payment.status === "expired" || payment.status === "failed") && <>
          <p>{cancelled || payment.status === "expired" ? "The payment was cancelled, and you have not been charged." : "The payment did not go through, and you have not been charged."}</p>
          <div className="mt-5"><Link to="/billing"><Button>Try again</Button></Link></div>
        </>}
        {payment?.sandbox && <p className="mt-4 text-xs text-muted">Test mode: no real money was taken.</p>}
      </Card>
    </div>
  );
}

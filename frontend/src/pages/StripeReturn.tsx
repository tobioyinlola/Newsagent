import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { DistributionReturnLink } from "../components/DistributionReturnLink";
import { Button, Card, ErrorBox, Notice } from "../components/ui";

const credits = (v: string) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
const money = (v: string) => Number(v).toLocaleString(undefined, { style: "currency", currency: "USD" });
const WAIT_MS = 120_000; // how long to keep checking before suggesting the customer look again later

/** Where Stripe sends the customer back to. The page never decides anything: it asks our server, which asks Stripe. */
export function StripeReturn() {
  const { checkoutId = "" } = useParams();
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const [startedAt] = useState(() => Date.now());
  const [closing] = useState({ done: false }); // backing out closes the session once; after that this page only checks the status
  const cancelled = params.get("cancelled") === "1";
  type Payment = { checkout_id: string; amount_usd: string; credits: string; status: string; sandbox: boolean; credit_balance?: string | null };
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

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold">Your payment</h1>
      <Card title={paid ? "Payment received" : payment?.status === "pending" ? "Confirming your payment…" : "Payment not completed"}>
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
        {payment && (payment.status === "expired" || payment.status === "failed") && <>
          <p>{cancelled || payment.status === "expired" ? "The payment was cancelled, and you have not been charged." : "The payment did not go through, and you have not been charged."}</p>
          <div className="mt-5"><Link to="/billing"><Button>Try again</Button></Link></div>
        </>}
        {payment?.sandbox && <p className="mt-4 text-xs text-muted">Test mode: no real money was taken.</p>}
      </Card>
    </div>
  );
}

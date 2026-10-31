import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { DistributionReturnLink } from "../components/DistributionReturnLink";
import { api, unwrap } from "../api/client";
import { cardErrors, emptyCard, encryptCard, type CardDetails } from "../lib/cardPayment";
import { Button, Card, ErrorBox, Notice } from "../components/ui";

type Payment = { card_payments_enabled?: boolean; checkout_id: string; amount_usd: string; credits: string; currency: "USD" | "NGN"; amount?: string; ngn_per_usd?: string | null; status: string; provider_status: string; public_key: string; sandbox: boolean; next_action_url: string | null; can_retry_confirmation?: boolean; payment_error?: { message: string; code: string } | null };
const money = (v: string, currency = "USD") => Number(v).toLocaleString(undefined, { style: "currency", currency });
export function CardCheckout() {
  const { checkoutId = "" } = useParams();
  const qc = useQueryClient();
  const [card, setCard] = useState<CardDetails>({ ...emptyCard });
  const [errors, setErrors] = useState<Partial<Record<keyof CardDetails, string>>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const query = useQuery({ queryKey: ["card-checkout", checkoutId], queryFn: () => unwrap(api.GET("/v1/billing/card/{id}", { params: { path: { id: checkoutId } } })) as Promise<Payment>, retry: false,
    refetchInterval: q => q.state.data?.status === "pending" && q.state.data.provider_status !== "requires_action" ? 10000 : false,
  });
  const payment = query.data;
  useEffect(() => { if (payment?.can_retry_confirmation === true) setAttempted(false); }, [payment?.can_retry_confirmation, query.dataUpdatedAt]);
  const paid = payment?.status === "paid";
  useEffect(() => {
    if (paid) for (const key of ["me", "billing-summary", "ledger", "payment-checkouts"]) void qc.invalidateQueries({ queryKey: [key] });
  }, [paid, qc]);
  const change = (key: keyof CardDetails, value: string) => { setCard(c => ({ ...c, [key]: value })); setErrors(e => ({ ...e, [key]: undefined })); };
  const confirm = async () => {
    if (!payment || busy || attempted) return;
    const validation = cardErrors(card); setErrors(validation);
    if (Object.keys(validation).length) return;
    setBusy(true); setError(null);
    try {
      const encrypted_data = await encryptCard(card, payment.public_key);
      const body = { encrypted_data, first_name: card.first_name.trim(), last_name: card.last_name.trim(),
        billing_address: { address_line_one: card.address_line_one.trim(), city: card.city.trim(), state: card.state.trim(), country: card.country, zip: card.zip.trim() },
        browser_info: { language: navigator.language, screen_width: String(screen.width), screen_height: String(screen.height), color_depth: String(screen.colorDepth), timezone_offset: String(new Date().getTimezoneOffset()), java_enabled: false, javascript_enabled: true, channel: "browser" as const },
      };
      // No raw card details go to our API, local/session storage, analytics, or URLs.
      setCard({ ...emptyCard }); setAttempted(true);
      const result = await unwrap(api.POST("/v1/billing/card/{id}/confirm", { params: { path: { id: checkoutId } }, body })) as Payment;
      qc.setQueryData(["card-checkout", checkoutId], result);
      if (result.next_action_url) window.location.assign(result.next_action_url);
    } catch (e) { setError(e); if (attempted || card.number) await query.refetch(); } finally { setBusy(false); }
  };
  const cancel = async () => {
    setBusy(true); setError(null);
    try { const result = await unwrap(api.POST("/v1/billing/card/{id}/cancel", { params: { path: { id: checkoutId } } })) as Payment; qc.setQueryData(["card-checkout", checkoutId], result); }
    catch (e) { setError(e); } finally { setBusy(false); }
  };
  const canPay = payment?.card_payments_enabled !== false && payment?.status === "pending" && payment.provider_status === "requires_action" && payment.can_retry_confirmation !== false && !attempted;
  const fields: [keyof CardDetails, string, string, string][] = [["first_name", "First name on card", "text", "cc-given-name"], ["last_name", "Last name on card", "text", "cc-family-name"], ["number", "Card number", "text", "cc-number"], ["expiry", "Expiry date (MM/YY)", "text", "cc-exp"], ["cvv", "Security code", "password", "cc-csc"], ["address_line_one", "Billing address", "text", "address-line1"], ["city", "City", "text", "address-level2"], ["state", "State / province / region", "text", "address-level1"], ["country", "Country code", "text", "country"], ["zip", "Postal code (optional)", "text", "postal-code"]];
  return <div className="mx-auto max-w-2xl space-y-5 pb-8"><h1 className="text-2xl font-bold">Buy credits by card</h1><ErrorBox error={error ?? query.error} />
    {!payment && <><p>{query.isFetching ? "Preparing your secure payment…" : "We couldn't load this payment."}</p><Button variant="secondary" onClick={() => void query.refetch()} disabled={query.isFetching}>Check payment status</Button></>}
    {payment && <>
      {payment.sandbox && <Notice tone="warn">Sandbox payment: no real money will be charged.</Notice>}
      <Card title={paid ? "Payment confirmed" : "Your purchase"}><p className="text-3xl font-bold">{money(payment.amount ?? payment.amount_usd, payment.currency)}</p><p className="mt-2">{payment.credits} credits · Charged in {payment.currency}</p>{payment.currency === "NGN" && <p className="mt-2 text-sm text-muted">USD package: {money(payment.amount_usd)} · ₦{Number(payment.ngn_per_usd).toLocaleString()} per $1. Your checkout rate is fixed.</p>}{paid && <Notice tone="ok">Your payment is confirmed and the credits have been added to your wallet.</Notice>}</Card>
      {payment.card_payments_enabled === false && !paid && <Notice tone="info">Card payments are coming soon. Use bank transfer from billing. Check any existing pending payment before starting another purchase.</Notice>}
      {payment.payment_error && !paid && <Notice tone="warn">{payment.payment_error.message}{canPay ? " Please re-enter your card details to try again." : " Use Check payment status before starting another payment."}</Notice>}
      {canPay && <Card title="Card and billing details"><form className="grid gap-4 sm:grid-cols-2" onSubmit={e => { e.preventDefault(); void confirm(); }} noValidate>
        {fields.map(([key, label, type, autocomplete]) => <div key={key} className={key === "number" || key === "address_line_one" ? "sm:col-span-2" : ""}><label className="block text-sm font-semibold" htmlFor={`card-${key}`}>{label}</label><input id={`card-${key}`} name={key} type={type} autoComplete={autocomplete} inputMode={["number", "cvv"].includes(key) ? "numeric" : undefined} maxLength={key === "cvv" ? 4 : key === "number" ? 23 : key === "country" ? 2 : key === "expiry" ? 7 : key.includes("name") ? 30 : 200} placeholder={key === "country" ? "NG, CA, US…" : key === "expiry" ? "MM/YY" : undefined} value={card[key]} disabled={busy} aria-invalid={!!errors[key]} aria-describedby={errors[key] ? `error-${key}` : undefined} onChange={e => change(key, key === "country" ? e.target.value.toUpperCase() : e.target.value)} className="mt-2 min-h-12 w-full rounded-lg border border-ink p-3" />{errors[key] && <p id={`error-${key}`} role="alert" className="mt-1 text-sm text-red-800">{errors[key]}</p>}</div>)}
        <p className="text-sm text-muted sm:col-span-2">Card details are encrypted in your browser for Nuvion. Your bank may ask you to complete an additional verification step.</p><Button className="sm:col-span-2" type="submit" disabled={busy}>{busy ? "Processing…" : `Pay ${money(payment.amount ?? payment.amount_usd, payment.currency)}`}</Button>
      </form></Card>}
      {!paid && payment.status === "pending" && (!canPay || busy) && <Card title="Payment verification"><p>Your payment is being checked. Please don't start another payment while this one is pending.</p>{payment.next_action_url && <a className="mt-3 inline-block rounded border-2 border-ink bg-brand-green px-4 py-3 font-bold" href={payment.next_action_url}>Continue bank verification</a>}<Button className="mt-3" variant="secondary" onClick={() => void query.refetch()} disabled={query.isFetching || busy}>Check payment status</Button></Card>}
      {["failed", "expired"].includes(payment.status) && <Notice tone="warn">{payment.status === "failed" ? "This payment failed or was declined." : "This payment was cancelled."} No credits were added for this attempt. Return to billing to start a new checkout.</Notice>}
      {!paid && payment.status === "pending" && ["requires_action", "confirming"].includes(payment.provider_status) && <Button variant="secondary" disabled={busy} onClick={() => void cancel()}>Cancel this payment</Button>}
    </>}
    <Link className="inline-block min-h-11 py-2 font-semibold underline" to="/billing">{paid ? "View wallet and continue" : "Back to billing"}</Link>
  {paid && <DistributionReturnLink />}</div>;
}

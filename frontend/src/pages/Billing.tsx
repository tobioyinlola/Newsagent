import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Notice } from "../components/ui";
import { downloadAuthed } from "../lib/download";

const money = (v: string | number) => Number(v).toLocaleString(undefined, { style: "currency", currency: "USD" });
type Methods = { ngn_per_usd: string; usd_card: boolean; ngn_card: boolean; ngn_bank_transfer: boolean; usd_bank_transfer?: boolean; manual_review?: boolean };
const naira = (v: string | number) => Number(v).toLocaleString("en-NG", { style: "currency", currency: "NGN" });
function PaymentIcon({ bank }: { bank: boolean }) {
  return <svg aria-hidden="true" viewBox="0 0 32 24" className="mb-2 h-6 w-8" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{bank ? <><path d="M3 8 16 2l13 6H3Z" /><path d="M5 21h22M8 11v7m8-7v7m8-7v7" /></> : <><rect x="2" y="3" width="28" height="18" rx="3" /><path d="M2 9h28M6 16h6m8 0h6" /></>}</svg>;
}
const KIND: Record<string, string> = { grant: "Credits added", purchase: "Purchase", adjustment: "Adjustment", usage: "Used", usage_adjust: "Usage correction", usage_release: "Refunded (step didn't run)" };

export function Billing() {
  const qc = useQueryClient();
  const [customCredits, setCustomCredits] = useState("");
  const [quotedCredits, setQuotedCredits] = useState("");
  useEffect(() => { const timer = setTimeout(() => setQuotedCredits(customCredits), 350); return () => clearTimeout(timer); }, [customCredits]);
  const [currency, setCurrency] = useState<"USD" | "NGN">("USD");
  const [method, setMethod] = useState<"card" | "bank_transfer">("card");
  const methods = useQuery({ queryKey: ["payment-methods"], queryFn: () => unwrap(api.GET("/v1/billing/payment-methods")) as Promise<Methods>, staleTime: 0 });
  const rate = methods.data?.ngn_per_usd;
  const reviewMode = methods.data?.manual_review === true;
  const available = currency === "USD" ? reviewMode ? methods.data?.usd_bank_transfer : methods.data?.usd_card : method === "card" ? methods.data?.ngn_card : methods.data?.ngn_bank_transfer;
  useEffect(() => { if (reviewMode) setMethod("bank_transfer"); }, [reviewMode]);
  const [params] = useSearchParams();
  const candidate = params.get("returnTo");
  const [savedReturn] = useState(() => { try { return sessionStorage.getItem("distribution-return"); } catch { return null; } });
  const returnTo = candidate?.startsWith("/distribution/request?") ? candidate : savedReturn;
  useEffect(() => {
    if (candidate?.startsWith("/distribution/request?")) {
      try { sessionStorage.setItem("distribution-return", candidate); } catch { /* the URL still preserves the return path */ }
    }
  }, [candidate]);
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const summary = useQuery({ queryKey: ["billing-summary"], queryFn: () => unwrap(api.GET("/v1/billing/summary")) });
  const caps = useQuery({ queryKey: ["capabilities"], queryFn: () => unwrap(api.GET("/v1/capabilities")), staleTime: 600000, retry: false });
  const manual = (caps.data as { payments?: string } | undefined)?.payments === "manual" && !reviewMode;
  const options = useQuery({ queryKey: ["credit-options"], queryFn: () => unwrap(api.GET("/v1/billing/options")) });
  const checkouts = useQuery({ queryKey: ["payment-checkouts"], queryFn: () => unwrap(api.GET("/v1/billing/checkouts")) as Promise<{ id: string; amount_usd: string; credits: string; status: string; created_at: string; currency?: string; amount?: string; payment_method?: string; review_required?: boolean }[]> });
  const usage = useQuery({ queryKey: ["usage", month], queryFn: () => unwrap(api.GET("/v1/billing/usage", { params: { query: { month } } })) });
  const ledger = useQuery({ queryKey: ["ledger"], queryFn: () => unwrap(api.GET("/v1/billing/ledger", { params: { query: { limit_: 50 } } })) });
  const customValid = /^\d+(?:\.\d{1,2})?$/.test(quotedCredits) && Number(quotedCredits) > 0;
  const customQuote = useQuery({ queryKey: ["custom-credit-quote", quotedCredits], queryFn: () => unwrap(api.POST("/v1/billing/custom-quote", { body: { credits: quotedCredits } })), enabled: customValid && !manual, retry: false, staleTime: 0 });
  const buy = useMutation({
    mutationFn: (choice: { amount_usd: string; custom_credits?: string; custom_quote_version?: string; ngn_per_usd?: string }) => unwrap(api.POST("/v1/billing/checkout", { body: { ...choice, currency, payment_method: reviewMode ? "bank_transfer" : currency === "USD" ? "card" : method, ...(currency === "NGN" && (choice.ngn_per_usd ?? rate) ? { ngn_per_usd: choice.ngn_per_usd ?? rate } : {}) } })),
    onSuccess: (d) => { qc.invalidateQueries({ queryKey: ["me"] }); window.location.assign(d.url); },
    onError: () => { void methods.refetch(); void options.refetch(); if (customValid) void customQuote.refetch(); },
  });
  const [csvErr, setCsvErr] = useState<string | null>(null);
  const s = summary.data;
  useEffect(() => {
    const suggested = params.get("credits");
    if (suggested && /^\d+(?:\.\d{1,2})?$/.test(suggested) && Number(suggested) > 0 && s?.usd_per_credit) {
      const minimum = Math.ceil(10 / Number(s.usd_per_credit) * 100) / 100;
      setCustomCredits(String(Math.max(Number(suggested), minimum)));
    }
  }, [params, s?.usd_per_credit]);
  const low = s && Number(s.credit_balance) < Number(s.low_balance_threshold);

  return (
    <>
      <h1 className="text-2xl font-bold">Credits and billing</h1>
      {returnTo?.startsWith("/distribution/request?") && <Link className="underline" to={returnTo}>Return to your saved distribution request</Link>}
      <Card title="Your balance">
        <p className="text-4xl font-extrabold tabular-nums" aria-label="Credit balance">{s ? Number(s.credit_balance).toFixed(2) : "…"} <span className="text-lg font-medium text-muted">credits</span></p>
        {low && <div className="mt-3"><Notice tone="warn">You're running low. Add credits so your next video isn't paused.</Notice></div>}
        {s && <p className="mt-2 text-sm text-muted">1 credit = {money(s.usd_per_credit)}. Use your wallet for videos and press distribution.</p>}
      </Card>
      <Card title="Add credits">
        {!manual && <div className="mb-5 space-y-4">
          <fieldset><legend className="mb-2 text-sm font-semibold">Pay in</legend><div className="flex flex-wrap gap-3">{(["USD", "NGN"] as const).map(value => <label key={value} className={`flex min-h-12 cursor-pointer items-center gap-2 rounded-lg border-2 px-4 py-3 ${currency === value ? "border-ink bg-brand-green" : "border-line"}`}><input type="radio" name="payment-currency" value={value} checked={currency === value} disabled={buy.isPending} onChange={() => { setCurrency(value); setMethod(reviewMode ? "bank_transfer" : value === "NGN" && !methods.data?.ngn_card && methods.data?.ngn_bank_transfer ? "bank_transfer" : "card"); buy.reset(); }} />{value === "NGN" ? "Nigerian naira (NGN)" : "US dollars (USD)"}</label>)}</div></fieldset>
          {reviewMode ? <><fieldset><legend className="mb-2 text-sm font-semibold">Payment method</legend><div className="grid gap-3 sm:grid-cols-2"><label className="flex min-h-20 items-center gap-3 rounded-xl border-2 border-ink bg-paper p-4"><input type="radio" checked readOnly name="review-payment-method" /><span><PaymentIcon bank /><span className="block font-semibold">Bank transfer</span><span className="mt-1 block text-sm text-muted">Upload your receipt for team approval</span></span></label><div aria-disabled="true" className="rounded-xl border-2 border-line p-4 text-muted"><PaymentIcon bank={false} /><p className="font-semibold">Card payments · Coming soon</p><p className="mt-1 text-sm">Use bank transfer to buy credits.</p></div></div></fieldset><p className="text-sm text-muted">After transferring, upload your payment receipt. Credits are added once the team approves the payment.</p>{currency === "NGN" && rate && <p className="text-sm text-muted">₦{Number(rate).toLocaleString()} per $1 USD. Your exact amount is shown before you transfer.</p>}{!available && methods.data && <Notice tone="warn">Bank transfer details are not available for this currency yet. Please contact the team.</Notice>}</> : currency === "NGN" ? <>
            {rate && <p className="text-sm text-muted">₦{Number(rate).toLocaleString()} = $1 USD. Packages and credits stay the same; you pay the naira equivalent.</p>}
            <fieldset><legend className="mb-2 text-sm font-semibold">Payment method</legend><div className="grid gap-3 sm:grid-cols-2">{([{ value: "card", label: "Local card", help: "Pay in NGN with a supported card", enabled: methods.data?.ngn_card }, { value: "bank_transfer", label: "Bank transfer", help: "Transfer from your Nigerian banking app", enabled: methods.data?.ngn_bank_transfer }] as const).map(item => <label key={item.value} className={`flex min-h-20 items-start gap-3 rounded-xl border-2 p-4 ${method === item.value ? "border-ink" : "border-line"} ${!item.enabled ? "opacity-60" : "cursor-pointer"}`}><input className="mt-1" type="radio" name="payment-method" checked={method === item.value} disabled={!item.enabled || buy.isPending} onChange={() => { setMethod(item.value); buy.reset(); }} /><span><PaymentIcon bank={item.value === "bank_transfer"} /><span className="block font-semibold">{item.label}{!item.enabled ? " · Not available yet" : ""}</span><span className="mt-1 block text-sm text-muted">{item.help}</span></span></label>)}</div></fieldset>
            {methods.data && !methods.data.ngn_card && !methods.data.ngn_bank_transfer && <Notice tone="warn">Naira payments are being set up. You can still pay in USD with a card that supports international payments.</Notice>}
          </> : <p className="text-sm text-muted">Charged in USD. Nigerian cards must support international USD payments. Choose NGN for local payment options.</p>}
          <ErrorBox error={methods.error} />
          {methods.isError && <Button variant="secondary" onClick={() => void methods.refetch()}>Reload payment methods</Button>}
        </div>}

        {manual ? <p className="text-muted">Credits are added by our team. Contact us with the amount you need and we'll top up your workspace.</p> : options.data?.length ? (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {options.data.map((o) => (
              <li key={o.amount_usd} className="rounded-md border border-line p-4">
                <p className="text-2xl font-bold">{currency === "NGN" ? rate ? naira(Number(o.amount_usd) * Number(rate)) : "Loading price…" : money(o.amount_usd)}</p>
                {currency === "NGN" && <p className="mt-1 text-sm text-muted">{money(o.amount_usd)} package</p>}
                <p className="font-semibold">{Number(o.credits).toFixed(2)} credits</p>
                <p className="mb-3 mt-1 text-xs text-muted">Added to your wallet after payment</p>
                <Button onClick={() => buy.mutate({ amount_usd: o.amount_usd })} disabled={buy.isPending || !available} aria-label={`Buy ${currency === "NGN" && rate ? naira(Number(o.amount_usd) * Number(rate)) : money(o.amount_usd)} of credits`}>Buy</Button>
              </li>
            ))}
          </ul>
        ) : <p className="text-muted">Credits can't be bought right now. Contact us to add credits.</p>}
        {!manual && <section aria-labelledby="custom-credits-title" className="mt-6 rounded-xl border border-line bg-paper p-5 sm:p-6"><h3 id="custom-credits-title" className="text-lg font-bold">Choose a custom credit amount</h3><p className="mt-2 text-sm text-muted">Buy the credits you need. Custom purchases start at $10 USD or the naira equivalent.</p><form className="mt-4 space-y-4" onSubmit={e => { e.preventDefault(); if (!buy.isPending && available && customValid && !customQuote.isError && customQuote.data && customCredits === quotedCredits && !customQuote.isFetching) buy.mutate({ amount_usd: customQuote.data.amount_usd, custom_credits: customQuote.data.credits, custom_quote_version: customQuote.data.quote_version, ...(currency === "NGN" ? { ngn_per_usd: customQuote.data.ngn_per_usd } : {}) }); }}><label className="block text-sm font-semibold" htmlFor="custom-credits">Credits to buy<input id="custom-credits" type="number" inputMode="decimal" min="0.01" max="99999999.99" step="0.01" placeholder="For example, 220" required className="mt-2 block min-h-12 w-full rounded-lg border border-ink bg-white px-3 font-normal sm:max-w-sm" value={customCredits} disabled={buy.isPending} onChange={e => { setCustomCredits(e.target.value); buy.reset(); }} /></label>{s && <p className="text-xs text-muted">At {money(s.usd_per_credit)} per credit, the minimum custom amount is {Math.ceil(10 / Number(s.usd_per_credit) * 100) / 100} credits.</p>}{customCredits && (customCredits !== quotedCredits || customQuote.isFetching) && <p role="status" className="text-sm">Calculating your price…</p>}{customCredits && customCredits === quotedCredits && !customQuote.isFetching && customQuote.data && <div aria-label="Custom credit quote" className="rounded-lg border border-line bg-white p-4"><p className="text-sm font-semibold">{customQuote.data.credits} credits</p><p className="mt-2 text-2xl font-bold">{currency === "NGN" ? naira(customQuote.data.amount_ngn) : money(customQuote.data.amount_usd)}</p>{currency === "NGN" && <p className="mt-1 text-sm text-muted">{money(customQuote.data.amount_usd)} USD · ₦{Number(customQuote.data.ngn_per_usd).toLocaleString()} per $1</p>}</div>}{customCredits === quotedCredits && customValid && <ErrorBox error={customQuote.error} />}<Button type="submit" disabled={buy.isPending || !available || !customValid || customCredits !== quotedCredits || customQuote.isFetching || !customQuote.data || customQuote.isError}>Buy custom credits</Button></form></section>}
        <ErrorBox error={buy.error} />
      </Card>
      {!!checkouts.data?.length && <Card title="Payments"><ul className="space-y-3">{checkouts.data.map(co => <li key={co.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3 text-sm"><span>{co.currency === "NGN" ? naira(co.amount ?? "0") : money(co.amount_usd)} · {co.payment_method === "bank_transfer" ? "Bank transfer · " : ""}{co.credits} credits · <strong>{co.status === "pending_review" ? "Awaiting approval" : co.status === "rejected" ? "Receipt needs attention" : co.status === "paid" ? "Approved / paid" : co.status}</strong></span><Link className="font-semibold underline" to={`/billing/${co.review_required ? "transfer" : co.payment_method === "bank_transfer" ? "bank" : "card"}/${co.id}`}>{["pending", "pending_review", "rejected"].includes(co.status) ? "Resume / check payment" : "View payment"}</Link></li>)}</ul></Card>}
      <Card title="Usage" actions={
        <span className="flex flex-wrap items-center gap-2">
          <label className="text-sm" htmlFor="month">Month</label>
          <input id="month" type="month" className="rounded border border-ink px-2 py-1 text-sm" value={month} onChange={(e) => setMonth(e.target.value)} />
          <Button variant="secondary" onClick={() => downloadAuthed(`/v1/billing/usage.csv?month=${month}`, `usage-${month}.csv`).catch((e) => setCsvErr(e.message))}>Download CSV</Button>
        </span>}>
        {csvErr && <ErrorBox error={new Error(csvErr)} />}
        {usage.data && usage.data.lines.length ? (
          <table className="w-full text-sm"><caption className="sr-only">Usage by video and step</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">Video</th><th>Step</th><th className="text-right">Credits</th></tr></thead>
            <tbody>{usage.data.lines.map((l, i) => <tr key={i} className="border-t border-line"><td className="py-1">{l.project_id ? <Link className="underline" to={`/ai-newsroom/${l.project_id}`}>{l.project_id.slice(0, 6)}</Link> : "-"}</td><td>{l.stage ?? "-"}</td><td className="text-right tabular-nums">{Number(l.credits).toFixed(4)}</td></tr>)}
              <tr className="border-t border-ink font-semibold"><td className="py-1" colSpan={2}>Total for {usage.data.month}</td><td className="text-right tabular-nums">{Number(usage.data.total_credits).toFixed(4)}</td></tr></tbody></table>
        ) : <p className="text-muted">No usage in {month}.</p>}
      </Card>
      <Card title="History">
        <table className="w-full text-sm"><caption className="sr-only">Credit history</caption>
          <thead><tr className="text-left text-muted"><th className="py-1">When</th><th>What</th><th className="text-right">Credits</th><th className="text-right">Balance</th></tr></thead>
          <tbody>{ledger.data?.map((e) => <tr key={e.id} className="border-t border-line"><td className="py-1">{new Date(e.created_at).toLocaleString()}</td><td>{KIND[e.kind] ?? e.kind}{e.stage ? ` · ${e.stage}` : ""}</td><td className={`text-right tabular-nums ${Number(e.amount) < 0 ? "" : "text-ink"}`}>{Number(e.amount) > 0 ? "+" : ""}{Number(e.amount).toFixed(4)}</td><td className="text-right tabular-nums">{Number(e.balance_after).toFixed(2)}</td></tr>)}</tbody></table>
      </Card>
    </>
  );
}

// Local development only: stands in for the payment provider's hosted checkout page.
export function MockPay() {
  const { checkoutId = "" } = useParams();
  const nav = useNavigate();
  const pay = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/billing/dev/pay/{checkout_id}", { params: { path: { checkout_id: checkoutId } } })),
    onSuccess: () => nav("/billing"),
  });
  return (
    <div className="mx-auto max-w-md space-y-4 p-6">
      <Card title="Test payment">
        <Notice tone="warn">This is a test checkout for development. A real payment provider's page appears here in production.</Notice>
        <div className="mt-4 flex gap-2"><Button onClick={() => pay.mutate()} disabled={pay.isPending}>Pay now (test)</Button><Link className="px-3 py-2 text-sm underline" to="/billing">Cancel</Link></div>
        <ErrorBox error={pay.error} />
      </Card>
    </div>
  );
}

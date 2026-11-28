import { useEffect, useState } from "react";
import { defaultCurrency, endsText, inTab, optionsFor, priceIn, quoteMail, standardIn, tabsFor, type Currency, type MediaPackage } from "../lib/packages";

// The media packages, by region. Used on the public distribution page (dark) and inside the app (light).
type Props = { packages: MediaPackage[]; currencies?: Currency[]; theme: "dark" | "light"; onChoose: (p: MediaPackage) => void; chosenId?: string; chooseLabel?: string; busy?: boolean };

export function PackageCards({ packages, currencies = [], theme, onChoose, chosenId, chooseLabel = "Choose this package", busy }: Props) {
  const dark = theme === "dark";
  // The currency chosen on a card applies to every card in the same region tab, so one choice is enough; a tab opens in its own currencies.
  const [picked, setPicked] = useState<Record<string, string>>({});
  const tabs = tabsFor(packages);
  const [key, setKey] = useState("");
  useEffect(() => { if (!tabs.some((t) => t.key === key)) setKey(tabs[0]?.key ?? ""); }, [tabs.map((t) => t.key).join(), key]);
  const shown = inTab(packages, key);
  if (!tabs.length) return null;
  const ink = dark ? "text-white" : "text-ink", soft = dark ? "text-white/70" : "text-muted";
  return (
    <div>
      <div role="tablist" aria-label="Package regions" className="flex flex-wrap justify-center gap-2">
        {tabs.map((t) => (
          <button key={t.key} role="tab" type="button" aria-selected={key === t.key} onClick={() => setKey(t.key)}
            className={`min-h-11 rounded-sm border px-4 py-2 text-sm font-bold transition ${key === t.key ? (dark ? "border-brand-green bg-brand-green text-ink" : "border-ink bg-brand-green text-ink") : dark ? "border-white/25 text-white/85 hover:border-brand-green" : "border-line bg-white text-ink hover:border-ink"}`}>
            {t.key === "campaign" && <span aria-hidden="true">🔥 </span>}{t.label}
          </button>
        ))}
      </div>
      {key === "campaign" && <p className={`mx-auto mt-5 max-w-2xl text-center text-sm ${soft}`}><strong className={ink}>The year is almost over.</strong> Your business has done the work. Now it is time to make sure people know about it. Limited slots, 27 to 30 November.</p>}
      <div role="tabpanel" className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {shown.map((p) => <PackageCard key={p.id} p={p} dark={dark} chosen={chosenId === p.id} onChoose={onChoose} label={chooseLabel} busy={busy} currencies={currencies} currency={picked[key] ?? defaultCurrency(p)} onCurrency={(c) => setPicked((x) => ({ ...x, [key]: c }))} />)}
      </div>
    </div>
  );
}

function PackageCard({ p, dark, chosen, onChoose, label, busy, currency, currencies, onCurrency }: { p: MediaPackage; dark: boolean; chosen: boolean; onChoose: (p: MediaPackage) => void; label: string; busy?: boolean; currency: string; currencies: Currency[]; onCurrency: (code: string) => void }) {
  const ink = dark ? "text-white" : "text-ink", soft = dark ? "text-white/70" : "text-muted", line = dark ? "border-white/15" : "border-line";
  const scarce = p.slots_left !== null && p.slots_left > 0 && p.slots_left <= 5;
  const can = p.state === "open";
  return (
    <article aria-label={p.name} className={`cf-lift flex flex-col rounded-sm border p-5 ${chosen ? "border-brand-green" : line} ${dark ? "bg-white/5" : "bg-white"}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className={`text-lg font-bold leading-snug ${ink}`}>{p.name}</h3>
        {p.percent_off ? <span className="rounded-sm bg-brand-green px-2 py-1 text-xs font-bold text-ink">{p.percent_off}% off</span> : null}
      </div>
      <div className="mt-3">
        {(() => {
          const options = optionsFor(p, currencies);
          const shown = priceIn(p, currency, currencies);
          const was = standardIn(p, currency, currencies);
          const credits = p.credits ? `${Number(p.credits).toLocaleString("en-US", { maximumFractionDigits: 2 })} credits` : null;
          return (
            <>
              {options.length > 1 && (
                <select aria-label={`Currency for ${p.name}`} value={currency} onChange={(e) => onCurrency(e.target.value)}
                  className={`mb-2 min-h-9 rounded-sm border px-2 py-1 text-xs font-bold ${dark ? "border-white/30 bg-ink text-white" : "border-line bg-white text-ink"}`}>
                  {options.map((c) => <option key={c.code} value={c.code}>{c.code} · {c.name}</option>)}
                </select>
              )}
              {shown ? (
                <p className={`text-3xl font-bold ${ink}`}>{shown}{was && <span className={`ml-2 text-base font-normal line-through ${soft}`}>{was}</span>}</p>
              ) : <p className={`text-3xl font-bold ${ink}`}>Custom quote</p>}
              {credits && <p className={`mt-1 text-sm ${soft}`}>{credits}</p>}
              {!p.usd_price && <p className={`mt-1 text-sm ${soft}`}>Price on request</p>}
            </>
          );
        })()}
      </div>
      {p.slots_total !== null && (
        <p className={`mt-3 text-sm font-bold ${scarce ? "text-brand-peach" : soft}`} role="status">
          {p.state === "sold_out" ? "Sold out" : `${p.slots_left} of ${p.slots_total} slots left`}{p.ends_at && p.state === "open" ? ` · ${endsText(p.ends_at)}` : ""}
        </p>
      )}
      {p.outlets.length > 0 && <ul className={`mt-4 space-y-1.5 text-sm ${dark ? "text-white/85" : "text-ink"}`}>{p.outlets.map((o) => <li key={o} className="flex gap-2"><span className="text-brand-green" aria-hidden="true">✓</span>{o}</li>)}</ul>}
      {p.includes.length > 0 && <ul className={`mt-3 space-y-1.5 text-sm ${dark ? "text-white/85" : "text-ink"}`}>{p.includes.map((o) => <li key={o} className="flex gap-2"><span className="text-brand-aqua" aria-hidden="true">+</span>{o}</li>)}</ul>}
      {p.ideal_for && <p className={`mt-4 text-sm ${soft}`}><strong className={ink}>Ideal for:</strong> {p.ideal_for}</p>}
      {p.note && <p className={`mt-2 text-xs italic ${soft}`}>{p.note}</p>}
      <div className="mt-auto pt-5">
        {can ? (
          <button type="button" disabled={busy} onClick={() => onChoose(p)} aria-label={`${label}: ${p.name}`}
            className={`cf-cta min-h-12 w-full rounded-sm border-2 px-5 py-3 text-sm font-bold disabled:opacity-60 ${chosen ? "border-brand-green bg-transparent text-brand-green" : "border-brand-green bg-brand-green text-ink hover:bg-transparent hover:text-brand-green"}`}>{chosen ? "Chosen ✓" : label}</button>
        ) : p.state === "quote" ? (
          <a href={quoteMail(p)} className={`flex min-h-12 w-full items-center justify-center rounded-sm border-2 px-5 py-3 text-sm font-bold ${dark ? "border-white/60 text-white hover:border-brand-green hover:text-brand-green" : "border-ink text-ink hover:bg-paper"}`}>Get a quote</a>
        ) : (
          <button type="button" disabled className={`min-h-12 w-full rounded-sm border-2 px-5 py-3 text-sm font-bold opacity-60 ${dark ? "border-white/30 text-white" : "border-line text-ink"}`}>{p.state === "sold_out" ? "Sold out" : p.state === "ended" ? "Offer ended" : "Not open yet"}</button>
        )}
      </div>
    </article>
  );
}

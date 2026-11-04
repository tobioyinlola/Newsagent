import { useId } from "react";
import { ALL, counts, emptyReason, type Facets, type OutletFilters as FilterList } from "../lib/distributionFilters";

type Tagged = { topic?: string; region?: string; country?: string | null };

// Topic chips and place selects, shared by the public page and the signed-in picker. `dark` matches the public pages.
export function OutletFilters({ filters, outlets, value, onChange, dark = false }: { filters: FilterList; outlets: Tagged[]; value: Facets; onChange: (f: Facets) => void; dark?: boolean }) {
  const uid = useId();
  const c = counts(outlets, value, filters);
  const countries = filters.locations.find((l) => l.region === value.region)?.countries ?? filters.locations.flatMap((l) => l.countries);
  const reason = emptyReason(outlets, value);
  const chip = (on: boolean) => `min-h-11 rounded-full border-2 px-4 py-2 text-sm font-bold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple ${on ? (dark ? "border-brand-green bg-brand-green text-ink" : "border-ink bg-ink text-white") : dark ? "border-white/30 text-white hover:border-brand-green" : "border-line bg-white hover:border-ink"}`;
  const select = `mt-1 min-h-11 w-full rounded-lg border px-3 py-2 text-base font-normal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple ${dark ? "border-white/40 bg-ink text-white" : "border-ink bg-white text-ink"}`;
  const label = `block text-sm font-bold ${dark ? "text-white" : ""}`;
  return (
    <div className="space-y-4">
      <div role="group" aria-label="Topic" className="flex flex-wrap gap-2">
        <button type="button" aria-pressed={!value.topic} className={chip(!value.topic)} onClick={() => onChange({ ...value, topic: "" })}>All topics</button>
        {filters.topics.map((t) => (
          <button key={t} type="button" aria-pressed={value.topic === t} className={chip(value.topic === t)} onClick={() => onChange({ ...value, topic: value.topic === t ? "" : t })}>
            {t} <span className="font-normal opacity-70">({c.topic[t] ?? 0})</span>
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 sm:max-w-xl">
        <div><label htmlFor={`${uid}-region`} className={label}>Region</label>
          <select id={`${uid}-region`} className={select} value={value.region} onChange={(e) => onChange({ ...value, region: e.target.value, country: "" })}>
            <option value="">All regions</option>
            {filters.locations.map((l) => <option key={l.region} value={l.region}>{l.region} ({c.region[l.region] ?? 0})</option>)}
          </select>
        </div>
        <div><label htmlFor={`${uid}-country`} className={label}>Country</label>
          <select id={`${uid}-country`} className={select} value={value.country} onChange={(e) => onChange({ ...value, country: e.target.value })}>
            <option value="">{value.region ? `All of ${value.region}` : "All countries"}</option>
            {countries.map((n) => <option key={n} value={n}>{n} ({c.country[n] ?? 0})</option>)}
          </select>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <p role="status" aria-live="polite" className={dark ? "text-white/80" : "text-muted"}>{reason ?? `${c.all} ${c.all === 1 ? "outlet" : "outlets"} shown`}</p>
        {(value.topic || value.region || value.country) && <button type="button" className="underline" onClick={() => onChange(ALL)}>Clear filters</button>}
      </div>
    </div>
  );
}

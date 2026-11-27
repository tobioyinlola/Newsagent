import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { distributionApi } from "../../lib/distribution";
import { getToken } from "../lib/auth";
import type { MediaPackage } from "../../lib/packages";

type Row = MediaPackage & { active: boolean };
const field = "min-h-11 w-28 rounded border border-ink px-2 py-1";

// Set the price, the number of slots and the dates of each media package, or switch it off. A package with no price is a custom quote.
export function PackagesAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-packages"], queryFn: () => distributionApi<{ packages: Row[] }>("admin/distribution-packages", getToken()), refetchInterval: 20000 });
  return (
    <div className="space-y-4">
      <p className="text-sm">Prices are in US dollars and are charged from the customer's wallet as credits. Leave the price empty and the package becomes a custom quote. Slots are taken when a customer pays.</p>
      {q.error && <p role="alert">{String(q.error)}</p>}
      <ul className="space-y-3">{q.data?.packages.map(p => <PackageRow key={p.id} p={p} onSaved={() => void qc.invalidateQueries({ queryKey: ["admin-packages"] })} />)}</ul>
    </div>
  );
}

function PackageRow({ p, onSaved }: { p: Row; onSaved: () => void }) {
  const [price, setPrice] = useState(p.usd_price ?? "");
  const [slots, setSlots] = useState(p.slots_total === null ? "" : String(p.slots_total));
  const [ends, setEnds] = useState(p.ends_at ? p.ends_at.slice(0, 10) : "");
  const [msg, setMsg] = useState("");
  const save = async (extra: Record<string, unknown> = {}) => {
    setMsg("Saving…");
    try {
      await distributionApi(`admin/distribution-packages/${p.id}`, getToken(), "PATCH", {
        ...(price === "" ? { clear_price: true } : { usd_price: price }),
        ...(slots === "" ? { clear_slots: true } : { slots_total: Number(slots) }),
        ...(ends ? { ends_at: `${ends}T22:59:59Z` } : {}),
        ...extra,
      });
      setMsg("Saved"); onSaved();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Not saved"); }
  };
  return (
    <li className="rounded border border-line p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><strong>{p.name}</strong><span className="text-sm">{p.state === "off" ? "Switched off" : p.state === "open" ? "On sale" : p.state.replace("_", " ")}{p.slots_total !== null && ` · ${p.slots_left} of ${p.slots_total} slots left`}</span></div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-sm font-semibold">Price (USD)<input aria-label={`Price in USD for ${p.name}`} inputMode="decimal" className={`mt-1 block ${field}`} value={price} placeholder="Quote" onChange={e => setPrice(e.target.value)} /></label>
        <label className="text-sm font-semibold">Slots<input aria-label={`Slots for ${p.name}`} inputMode="numeric" className={`mt-1 block ${field}`} value={slots} placeholder="No limit" onChange={e => setSlots(e.target.value.replace(/\D/g, ""))} /></label>
        <label className="text-sm font-semibold">Last day<input aria-label={`Last day for ${p.name}`} type="date" className={`mt-1 block ${field} w-40`} value={ends} onChange={e => setEnds(e.target.value)} /></label>
        <button className="min-h-11 rounded border border-ink bg-brand-green px-3 py-2 text-sm font-semibold" onClick={() => void save()}>Save</button>
        <button className="min-h-11 rounded border border-ink px-3 py-2 text-sm font-semibold" onClick={() => void save({ active: !p.active })}>{p.active ? "Switch off" : "Switch on"}</button>
        <span role="status" className="text-sm">{msg}</span>
      </div>
      {p.usd_price === null && Object.keys(p.local_prices).length > 0 && <p className="mt-2 text-xs">No dollar price yet, so customers see "Get a quote". Set one above to put it on sale.</p>}
    </li>
  );
}

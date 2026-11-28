import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { distributionApi } from "../../lib/distribution";
import { getToken } from "../lib/auth";
import { PACKAGE_TABS, usd, type Currency, type MediaPackage } from "../../lib/packages";

type Row = MediaPackage & { active: boolean; held: string[]; starts_at: string | null };
const input = "mt-1 block min-h-11 w-full rounded border border-ink px-2 py-1 font-normal";
const lagosDay = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-CA", { timeZone: "Africa/Lagos" }) : "");
const startOf = (day: string) => new Date(new Date(`${day}T00:00:00Z`).getTime() - 3600_000).toISOString(); // 00:00 in Lagos (WAT is UTC+1)
const endOf = (day: string) => `${day}T22:59:59Z`; // 23:59:59 in Lagos
const regions = PACKAGE_TABS.filter((t) => !["campaign", "organisation"].includes(t.key));

// Add a package, or change anything about one: its name, outlets, what is included, prices, slots and dates; or switch it off.
export function PackagesAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-packages"], queryFn: () => distributionApi<{ packages: Row[] }>("admin/distribution-packages", getToken()), refetchInterval: 20000 });
  const [open, setOpen] = useState<string>(""); // a package id being edited, or "new"
  const saved = () => { setOpen(""); void qc.invalidateQueries({ queryKey: ["admin-packages"] }); };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm">Prices are in US dollars and are charged from the customer's wallet as credits. Leave the price empty and the package becomes a custom quote. Slots are taken when a customer pays.</p>
        <button className="min-h-11 rounded border border-ink bg-brand-green px-4 py-2 text-sm font-semibold" onClick={() => setOpen(open === "new" ? "" : "new")}>Add a package</button>
      </div>
      {q.error && <p role="alert">{String(q.error)}</p>}
      <RatesCard />
      {open === "new" && <PackageForm onSaved={saved} onCancel={() => setOpen("")} />}
      <ul className="space-y-3">{q.data?.packages.map((p) => (
        <li key={p.id} className="rounded border border-line p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div><strong>{p.name}</strong><span className="ml-2 text-sm">{p.usd_price ? usd(p.usd_price) : "Custom quote"}</span></div>
            <span className="text-sm">{p.state === "off" ? "Switched off" : p.state === "open" ? "On sale" : p.state.replace("_", " ")}{p.slots_total !== null && ` · ${p.slots_left} of ${p.slots_total} slots left`}</span>
          </div>
          <div className="mt-3 flex flex-wrap gap-3">
            <button className="min-h-11 rounded border border-ink px-3 py-2 text-sm font-semibold" aria-label={`Edit ${p.name}`} onClick={() => setOpen(open === p.id ? "" : p.id)}>{open === p.id ? "Close" : "Edit"}</button>
            <ToggleButton p={p} onSaved={saved} />
          </div>
          {open === p.id && <div className="mt-4"><PackageForm existing={p} onSaved={saved} onCancel={() => setOpen("")} /></div>}
        </li>
      ))}</ul>
    </div>
  );
}

function ToggleButton({ p, onSaved }: { p: Row; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  return <button disabled={busy} className="min-h-11 rounded border border-ink px-3 py-2 text-sm font-semibold" onClick={async () => { setBusy(true); try { await distributionApi(`admin/distribution-packages/${p.id}`, getToken(), "PATCH", { active: !p.active }); onSaved(); } finally { setBusy(false); } }}>{p.active ? "Switch off" : "Switch on"}</button>;
}

function PackageForm({ existing, onSaved, onCancel }: { existing?: Row; onSaved: () => void; onCancel: () => void }) {
  const e = existing;
  const [v, set] = useState({
    name: e?.name ?? "", kind: e?.kind ?? "regional", region: e?.region ?? "nigeria", campaign: e?.campaign ?? "",
    price: e?.usd_price ?? "", standard: e?.standard_usd ?? "", slots: e?.slots_total == null ? "" : String(e.slots_total),
    starts: lagosDay(e?.starts_at ?? null), ends: lagosDay(e?.ends_at ?? null),
    outlets: (e?.outlets ?? []).join("\n"), includes: (e?.includes ?? []).join("\n"),
    local: Object.entries(e?.local_prices ?? {}).map(([c, a]) => `${c} ${a}`).join("\n"), ideal: e?.ideal_for ?? "", note: e?.note ?? "",
  });
  const [msg, setMsg] = useState("");
  const [held, setHeld] = useState<string[] | null>(e ? e.held : null);
  const up = (k: keyof typeof v) => (ev: { target: { value: string } }) => set((x) => ({ ...x, [k]: ev.target.value }));
  const lines = (t: string) => t.split("\n").map((x) => x.trim()).filter(Boolean);
  const save = async () => {
    setMsg("Saving…");
    const local: Record<string, string> = {};
    for (const l of lines(v.local)) { const [code, ...rest] = l.split(/\s+/); local[code] = rest.join("").replace(/,/g, ""); }
    const body = {
      name: v.name.trim(), kind: v.kind, region: v.kind === "regional" ? v.region : v.kind === "campaign" ? "campaign" : "organisation", campaign: v.kind === "campaign" ? v.campaign : "",
      ideal_for: v.ideal, note: v.note, outlets: lines(v.outlets), includes: lines(v.includes), local_prices: local,
      ...(v.price === "" ? { clear_price: true } : { usd_price: v.price }),
      ...(v.standard !== "" ? { standard_usd: v.standard } : {}),
      ...(v.slots === "" ? { clear_slots: true } : { slots_total: Number(v.slots) }),
      ...(v.starts || v.ends ? { ...(v.starts ? { starts_at: startOf(v.starts) } : {}), ...(v.ends ? { ends_at: endOf(v.ends) } : {}) } : { clear_dates: true }),
    };
    try {
      const r = e ? await distributionApi<Row>(`admin/distribution-packages/${e.id}`, getToken(), "PATCH", body) : await distributionApi<Row>("admin/distribution-packages", getToken(), "POST", body);
      setHeld(r.held); setMsg("Saved"); onSaved();
    } catch (err) { setMsg(err instanceof Error ? err.message : "Not saved"); }
  };
  const label = "block text-sm font-semibold";
  const name = e?.name ?? "new package";
  return (
    <form className="space-y-4 rounded border-2 border-ink p-4" aria-label={e ? `Edit ${e.name}` : "Add a package"} onSubmit={(ev) => { ev.preventDefault(); void save(); }}>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={label}>Package name<input aria-label={`Name of ${name}`} className={input} value={v.name} maxLength={200} onChange={up("name")} /></label>
        <label className={label}>Type<select aria-label={`Type of ${name}`} className={input} value={v.kind} onChange={up("kind")}><option value="regional">Regional package</option><option value="organisation">Organisation partnership</option><option value="campaign">Campaign deal</option></select></label>
        {v.kind === "regional" && <label className={label}>Region<select aria-label={`Region of ${name}`} className={input} value={v.region} onChange={up("region")}>{regions.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}</select></label>}
        {v.kind === "campaign" && <label className={label}>Campaign<select aria-label={`Campaign of ${name}`} className={input} value={v.campaign} onChange={up("campaign")}><option value="">Not named</option><option value="black_friday">Black Friday</option><option value="cyber_monday">Cyber Monday</option></select></label>}
        <label className={label}>Price (USD)<input aria-label={`Price in USD for ${name}`} inputMode="decimal" className={input} value={v.price} placeholder="Empty means a custom quote" onChange={up("price")} /></label>
        <label className={label}>Usual price (USD), to show "% off"<input aria-label={`Usual price for ${name}`} inputMode="decimal" className={input} value={v.standard} onChange={up("standard")} /></label>
        <label className={label}>Slots<input aria-label={`Slots for ${name}`} inputMode="numeric" className={input} value={v.slots} placeholder="Empty means no limit" onChange={(ev) => set((x) => ({ ...x, slots: ev.target.value.replace(/\D/g, "") }))} /></label>
        <div className="grid grid-cols-2 gap-3"><label className={label}>First day<input aria-label={`First day for ${name}`} type="date" className={input} value={v.starts} onChange={up("starts")} /></label><label className={label}>Last day<input aria-label={`Last day for ${name}`} type="date" className={input} value={v.ends} onChange={up("ends")} /></label></div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={label}>Outlets promised (one per line)<textarea aria-label={`Outlets of ${name}`} rows={6} className={input} value={v.outlets} onChange={up("outlets")} /></label>
        <label className={label}>What else is included (one per line)<textarea aria-label={`Includes of ${name}`} rows={6} className={input} value={v.includes} onChange={up("includes")} /></label>
        <label className={label}>Prices in other currencies, for display (one per line, like NGN 912203.49)<textarea aria-label={`Local prices of ${name}`} rows={3} className={input} value={v.local} onChange={up("local")} /></label>
        <div className="space-y-4"><label className={label}>Ideal for<input aria-label={`Ideal for ${name}`} className={input} value={v.ideal} maxLength={400} onChange={up("ideal")} /></label><label className={label}>Note shown on the card<input aria-label={`Note for ${name}`} className={input} value={v.note} maxLength={600} onChange={up("note")} /></label></div>
      </div>
      {held && <p className="text-sm">We can write to {held.length ? held.join(", ") : "none of these outlets"} ourselves. The rest are arranged by your team by hand.</p>}
      <div className="flex flex-wrap items-center gap-3"><button type="submit" className="min-h-11 rounded border border-ink bg-brand-green px-4 py-2 text-sm font-semibold">{e ? "Save changes" : "Add package"}</button><button type="button" className="min-h-11 rounded border border-ink px-4 py-2 text-sm font-semibold" onClick={onCancel}>Cancel</button><span role="status" className="text-sm">{msg}</span></div>
    </form>
  );
}

// The rates package prices are converted at when shown in another currency. A price the document states in a currency is shown as written;
// these only decide the others. Customers are always charged in US dollars.
function RatesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-package-rates"], queryFn: () => distributionApi<{ currencies: Currency[] }>("admin/distribution-package-rates", getToken()) });
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const list = (q.data?.currencies ?? []).filter((c) => c.code !== "USD");
  const save = async () => {
    setMsg("Saving…");
    try {
      await distributionApi("admin/distribution-package-rates", getToken(), "PUT", { rates: edit });
      setEdit({}); setMsg("Saved. Customers see the new rates straight away.");
      await qc.invalidateQueries({ queryKey: ["admin-package-rates"] });
    } catch (e) { setMsg(e instanceof Error ? e.message : "Not saved"); }
  };
  return (
    <details className="rounded border border-line p-4">
      <summary className="cursor-pointer font-semibold">Exchange rates for showing prices in other currencies</summary>
      <p className="mt-3 text-sm">How many of each currency buy one US dollar. They only decide how prices are <em>shown</em>; customers are always charged in US dollars. A price the package document states in a currency is shown exactly as written.</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((c) => (
          <label key={c.code} className="block text-sm font-semibold">1 US dollar in {c.name} ({c.code})
            <input aria-label={`${c.code} per US dollar`} inputMode="decimal" className="mt-1 block min-h-11 w-full rounded border border-ink px-2 py-1 font-normal" value={edit[c.code] ?? c.per_usd} onChange={(e) => setEdit((x) => ({ ...x, [c.code]: e.target.value }))} />
          </label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3"><button className="min-h-11 rounded border border-ink bg-brand-green px-4 py-2 text-sm font-semibold" onClick={() => void save()}>Save rates</button><span role="status" className="text-sm">{msg}</span></div>
    </details>
  );
}

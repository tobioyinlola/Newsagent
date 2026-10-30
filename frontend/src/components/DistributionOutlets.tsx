import { useEffect, useRef, useState } from "react";
import type { Outlet } from "../lib/distribution";
import { mediaPolicy } from "./DistributionMediaOptions";
import { Button } from "./ui";

type PickerProps = { outlets: Outlet[]; selectedIds: string[]; onChange: (ids: string[]) => void; comingSoon: string[] };

export function DistributionOutlets({ outlets, selectedIds, onChange, comingSoon }: PickerProps) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const categories = [...new Set(outlets.map(o => o.category ?? "Media outlets"))];
  const [selectedOnly, setSelectedOnly] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const selected = outlets.filter(o => selectedIds.includes(o.id));
  const visible = outlets.filter(o => (!selectedOnly || selectedIds.includes(o.id)) && (!category || (o.category ?? "Media outlets") === category) && `${o.name} ${o.category ?? "Media outlets"}`.toLowerCase().includes(search.trim().toLowerCase()));
  const groups = categories.map(name => ({ name, items: visible.filter(o => (o.category ?? "Media outlets") === name) })).filter(group => group.items.length);
  const toggle = (id: string) => onChange(selectedIds.includes(id) ? selectedIds.filter(x => x !== id) : [...selectedIds, id]);
  useEffect(() => { list.current?.scrollTo({ top: 0 }); }, [search, selectedOnly, category]);
  return <section aria-labelledby="outlet-picker-title" className="overflow-hidden rounded-xl border-2 border-ink bg-white">
    <div className="border-b border-line p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-widest text-muted">Choose your reach</p><h2 id="outlet-picker-title" className="mt-1 text-xl font-bold sm:text-2xl">Where would you like to distribute?</h2><p className="mt-2 text-sm text-muted">Browse outlets by category and select the publications that fit your story.</p></div><span className="rounded-full bg-brand-green px-3 py-1 text-xs font-bold">Africa · Available</span></div>
      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative block flex-1"><span className="sr-only">Search media outlets</span><svg aria-hidden="true" className="pointer-events-none absolute left-3 top-3.5 h-5 w-5 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="10" cy="10" r="6" /><path d="m15 15 5 5" /></svg><input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search publications or categories…" className="min-h-12 w-full rounded-lg border border-ink bg-paper py-3 pl-10 pr-3 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple" /></label>
        <button type="button" aria-pressed={selectedOnly} onClick={() => setSelectedOnly(!selectedOnly)} className={`min-h-12 shrink-0 rounded-lg border-2 px-4 py-2 text-sm font-bold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple ${selectedOnly ? "border-ink bg-ink text-white" : "border-line bg-white text-ink"}`}>Selected only ({selected.length})</button>
      </div>
      <label className="mt-4 block text-sm font-bold sm:max-w-md">Outlet category<select aria-label="Outlet category" className="mt-2 min-h-12 w-full rounded-lg border border-ink bg-white px-3 py-2 text-base font-normal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple" value={category} onChange={e => setCategory(e.target.value)}><option value="">All categories ({outlets.length})</option>{categories.map(name => <option key={name} value={name}>{name} ({outlets.filter(o => (o.category ?? "Media outlets") === name).length})</option>)}</select></label>
    </div>
    <div className="grid lg:grid-cols-[minmax(0,1fr)_15rem]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-paper px-4 py-3 text-sm sm:px-6"><p role="status" aria-live="polite">{visible.length} {visible.length === 1 ? "outlet" : "outlets"}{search.trim() ? " found" : " available"}</p><button type="button" disabled={!visible.length || visible.every(o => selectedIds.includes(o.id))} onClick={() => onChange([...new Set([...selectedIds, ...visible.map(o => o.id)])])} className="min-h-10 rounded px-2 font-bold underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-brand-purple disabled:text-muted disabled:no-underline">Select all shown</button></div>
        <div ref={list} role="region" aria-label="Available media outlets" tabIndex={0} className="h-[min(55svh,32rem)] min-h-64 overflow-y-auto overscroll-y-contain p-3 [scrollbar-gutter:stable] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-purple sm:p-4 lg:h-[32rem]">
          {visible.length ? <div className="space-y-6">{groups.map((group, index) => <section key={group.name} aria-labelledby={`outlet-category-${index}`}><div className="sticky top-0 z-10 mb-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-paper px-3 py-3"><h3 id={`outlet-category-${index}`} className="text-sm font-bold">{group.name}</h3><p className="text-xs text-muted">{group.items.length} {group.items.length === 1 ? "outlet" : "outlets"} · {group.items.filter(o => selectedIds.includes(o.id)).length} selected</p></div><div className="grid content-start gap-2 sm:grid-cols-2">{group.items.map(o => {
            const checked = selectedIds.includes(o.id);
            return <label key={o.id} className={`group flex min-h-20 cursor-pointer items-center gap-3 rounded-lg border-2 p-3 transition-colors motion-reduce:transition-none focus-within:ring-2 focus-within:ring-brand-purple focus-within:ring-offset-2 ${checked ? "border-ink bg-brand-green/15" : "border-line bg-white hover:border-ink/50 hover:bg-paper"}`}><input type="checkbox" checked={checked} onChange={() => toggle(o.id)} className="h-5 w-5 shrink-0 accent-ink" /><span className="min-w-0 flex-1"><span className="block break-words text-sm font-bold leading-snug">{o.name}</span><span className="mt-1 block text-xs text-muted">{o.credits} credits</span><span className="mt-1 block text-xs text-muted">{mediaPolicy(o)}</span></span><span aria-hidden="true" className={`shrink-0 text-sm ${checked ? "text-ink" : "text-transparent"}`}>✓</span></label>;
          })}</div></section>)}</div> : <div className="flex min-h-56 flex-col items-center justify-center px-4 text-center"><h3 className="font-bold">{selectedOnly && !selected.length ? "Your selection starts here" : "No matching outlets"}</h3><p className="mt-2 max-w-xs text-sm text-muted">{selectedOnly && !selected.length ? "Browse the full list and choose the publications you want." : "Try another publication name, or reset your filters."}</p><button className="mt-4 min-h-11 rounded-lg border-2 border-ink px-4 py-2 text-sm font-bold" onClick={() => { setSearch(""); setSelectedOnly(false); setCategory(""); }}>Show all outlets</button></div>}
        </div>
        <p className="border-t border-line px-4 py-3 text-xs text-muted sm:px-6">Scroll inside the list to browse. Your selections stay saved across categories and searches.</p>
      </div>
      <aside aria-label="Selection overview" className="hidden min-w-0 border-l border-line bg-paper p-5 lg:block"><p className="text-xs font-bold uppercase tracking-widest text-muted">Your shortlist</p><p className="mt-3 text-3xl font-bold tabular-nums">{selected.length}<span className="ml-2 text-sm font-normal text-muted">selected</span></p><p className="mt-1 text-sm">{Number(selected.reduce((n, o) => n + Number(o.credits), 0).toFixed(4))} credits total</p>{selected.length ? <><ul className="mt-5 max-h-72 space-y-2 overflow-y-auto overscroll-contain pr-1 [scrollbar-gutter:stable]">{selected.map(o => <li key={o.id} className="flex items-center justify-between gap-2 rounded border border-line bg-white p-2"><span className="min-w-0 break-words text-xs">{o.name}</span><button type="button" aria-label={`Remove ${o.name}`} onClick={() => toggle(o.id)} className="flex h-10 w-10 shrink-0 items-center justify-center rounded text-lg hover:bg-paper focus-visible:outline-2 focus-visible:outline-brand-purple">×</button></li>)}</ul><button type="button" onClick={() => onChange([])} className="mt-4 min-h-11 text-sm font-bold underline underline-offset-4">Clear selection</button></> : <p className="mt-5 text-sm text-muted">Choose an outlet to start building your distribution list.</p>}</aside>
    </div>
    <div className="border-t border-line bg-paper/60 p-4 sm:px-6"><p className="text-xs font-bold uppercase tracking-widest text-muted">More regions on the way</p><div className="mt-3 flex flex-wrap gap-2">{comingSoon.map(region => <span key={region} className="rounded-full border border-line bg-white px-3 py-2 text-xs"><strong>{region}</strong><span className="ml-2 text-muted">Coming soon</span></span>)}</div></div>
  </section>;
}

export function DistributionSelection({ selected, onRemove, onClose }: { selected: Outlet[]; onRemove: (id: string) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    element?.showModal();
    document.body.style.overflow = "hidden";
    return () => { element?.close(); document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return <dialog ref={dialog} aria-labelledby="selection-title" aria-label="Your selected outlets" onCancel={e => { e.preventDefault(); onClose(); }} onClick={e => { if (e.target === e.currentTarget) onClose(); }} className="m-auto w-[calc(100%_-_1.5rem)] max-w-lg overflow-hidden rounded-xl border-0 bg-white p-0 text-ink shadow-2xl backdrop:bg-ink/60">
    <div className="flex max-h-[85svh] flex-col"><header className="flex items-start justify-between gap-3 border-b border-line p-5"><div><h2 id="selection-title" className="text-xl font-bold">Your selected outlets</h2><p className="mt-1 text-sm text-muted">Review your shortlist before continuing.</p></div><button autoFocus type="button" aria-label="Close selection" onClick={onClose} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-line text-xl focus-visible:outline-2 focus-visible:outline-brand-purple">×</button></header>
      <ul className="min-h-32 overflow-y-auto overscroll-contain p-4 [scrollbar-gutter:stable]">{selected.length ? selected.map(o => <li className="flex items-center justify-between gap-3 border-b border-line py-3 last:border-0" key={o.id}><span className="min-w-0"><span className="block break-words text-sm font-bold">{o.name}</span><span className="text-xs text-muted">{o.credits} credits</span></span><button type="button" aria-label={`Remove ${o.name} from selection`} onClick={() => onRemove(o.id)} className="min-h-11 shrink-0 rounded border border-line px-3 text-xs font-bold hover:bg-paper">Remove</button></li>) : <li className="py-8 text-center text-sm text-muted">No outlets selected. Close this view to browse the list.</li>}</ul>
      <footer className="border-t border-line bg-paper p-5"><p className="mb-4 flex justify-between gap-3 text-sm"><span>{selected.length} outlets</span><strong>Total {Number(selected.reduce((n, o) => n + Number(o.credits), 0).toFixed(4))} credits</strong></p><Button className="w-full" onClick={onClose}>Done reviewing</Button></footer>
    </div>
  </dialog>;
}

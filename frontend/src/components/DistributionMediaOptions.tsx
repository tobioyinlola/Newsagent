import type { Draft, Outlet } from "../lib/distribution";

export function mediaPolicy(outlet: Outlet) {
  if (outlet.media_policy_configured === false) return "Logo and picture options awaiting confirmation";
  const logo = outlet.accepts_logo === false ? "Logo not accepted" : Number(outlet.logo_credits ?? 0) ? `Logo +${outlet.logo_credits} credits` : "Logo included";
  const pictures = outlet.accepts_images === false ? "Pictures not accepted" : Number(outlet.picture_credits ?? 0) ? `Pictures +${outlet.picture_credits} credits each` : "Pictures included";
  return `${logo} · ${pictures}`;
}

export function DistributionMediaOptions({ outlets, draft, onChange }: { outlets: Outlet[]; draft: Draft; onChange: (value: Draft["media_options"]) => void }) {
  const update = (id: string, key: "include_logo" | "include_pictures", checked: boolean) => onChange({ ...draft.media_options, [id]: { include_logo: true, include_pictures: true, ...draft.media_options?.[id], [key]: checked } });
  return <section className="mt-5 rounded-lg border border-line bg-paper p-4" aria-labelledby="media-options-title"><h3 id="media-options-title" className="font-bold">Images by outlet</h3><p className="mt-1 text-sm text-muted">Your company logo is required for our records. Choose which outlets receive it and your additional pictures. Any media fees are included in the total before payment.</p><ul className="mt-4 max-h-80 space-y-4 overflow-y-auto pr-1">{outlets.map(o => <li key={o.id} className="rounded-lg border border-line bg-white p-3"><h4 className="font-semibold">{o.name}</h4><p className="mt-1 text-xs text-muted">{mediaPolicy(o)}</p><div className="mt-3 flex flex-col gap-3 text-sm">{o.media_policy_configured !== false && o.accepts_logo !== false && <label className="flex min-h-10 items-center gap-2"><input type="checkbox" checked={draft.media_options?.[o.id]?.include_logo !== false} onChange={e => update(o.id, "include_logo", e.target.checked)} />Include logo for {o.name}</label>}{o.media_policy_configured !== false && o.accepts_images !== false && <label className="flex min-h-10 items-center gap-2"><input type="checkbox" checked={draft.media_options?.[o.id]?.include_pictures !== false} onChange={e => update(o.id, "include_pictures", e.target.checked)} />Include additional pictures for {o.name} ({draft.picture_keys.length} uploaded)</label>}</div></li>)}</ul></section>;
}

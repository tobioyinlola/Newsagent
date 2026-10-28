import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";

// Choose which AI presenter reads the news. The house presenters come first (the first is the default); search finds others.
const AVAILABLE = 3; // the house presenters people can pick today; more are shown, blurred, as coming soon
const PREVIEWED = 5;

export function PresenterPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const list = useQuery({
    queryKey: ["presenters"],
    queryFn: () => unwrap(api.GET("/v1/presenters", { params: { query: { q: "", gender: "", limit: AVAILABLE + PREVIEWED } } })),
    retry: false,
  });
  const items = list.data ?? [];
  if (list.isSuccess && items.length === 0) return null; // this provider has no catalogue to choose from
  const ready = items.slice(0, AVAILABLE);
  const soon = items.slice(AVAILABLE, AVAILABLE + PREVIEWED);
  return (
    <fieldset className="space-y-2 rounded-md border-2 border-ink p-3">
      <legend className="px-1 text-sm font-semibold">Your presenter</legend>
      <p className="text-sm text-muted">Our news-desk presenter is selected for you. Pick another if you prefer.</p>
      {list.isError && <p className="text-sm text-muted">The presenter list isn't available right now. The default presenter will be used.</p>}
      <div role="radiogroup" aria-label="Presenters" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {ready.map((p, i) => {
          const picked = value === p.id || (!value && i === 0); // nothing chosen = the default (listed first)
          return (
            <button key={p.id} type="button" role="radio" aria-checked={picked} onClick={() => onChange(i === 0 ? "" : p.id)}
              className={`overflow-hidden rounded-sm border-2 text-left text-sm ${picked ? "border-brand-purple bg-lilac" : "border-ink bg-white"}`}>
              {p.preview_image_url ? <img src={p.preview_image_url} alt="" className="aspect-video w-full object-cover" loading="lazy" /> : <div className="aspect-video w-full bg-paper" aria-hidden />}
              <span className="block p-1 font-medium">{p.name}{i === 0 ? " (default)" : ""}</span>
            </button>
          );
        })}
        {soon.map((p) => (
          <div key={p.id} aria-disabled="true" className="relative overflow-hidden rounded-sm border-2 border-line bg-white text-left text-sm" title="Coming soon">
            <div className="pointer-events-none select-none blur-[6px] grayscale" aria-hidden>
              {p.preview_image_url ? <img src={p.preview_image_url} alt="" className="aspect-video w-full object-cover" loading="lazy" /> : <div className="aspect-video w-full bg-paper" />}
              <span className="block p-1 font-medium">Presenter</span>
            </div>
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="rounded-sm bg-ink px-2 py-1 font-mono text-xs font-bold uppercase tracking-wider text-brand-green">Coming soon</span>
            </span>
          </div>
        ))}
      </div>
    </fieldset>
  );
}

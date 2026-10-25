import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { inputCls } from "./ui";

// Choose which AI presenter reads the news. Searchable, because a real catalogue has hundreds of looks.
export function PresenterPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [gender, setGender] = useState("");
  const list = useQuery({
    queryKey: ["presenters", q, gender],
    queryFn: () => unwrap(api.GET("/v1/presenters", { params: { query: { q, gender, limit: 12 } } })),
    retry: false,
  });
  const items = list.data ?? [];
  if (list.isSuccess && items.length === 0 && !q && !gender) return null; // this provider has no catalogue to choose from
  return (
    <fieldset className="space-y-2 rounded-md border-2 border-ink p-3">
      <legend className="px-1 text-sm font-semibold">Choose your presenter</legend>
      <div className="flex flex-wrap gap-2">
        <input aria-label="Search presenters" className={inputCls + " max-w-xs"} placeholder="Search by name" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Presenter gender" className={inputCls + " max-w-[10rem]"} value={gender} onChange={(e) => setGender(e.target.value)}>
          <option value="">Any</option><option value="female">Female</option><option value="male">Male</option>
        </select>
      </div>
      {list.isError && <p className="text-sm text-muted">The presenter list isn't available right now. The default presenter will be used.</p>}
      <div role="radiogroup" aria-label="Presenters" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {items.map((p) => (
          <button key={p.id} type="button" role="radio" aria-checked={value === p.id} onClick={() => onChange(value === p.id ? "" : p.id)}
            className={`overflow-hidden rounded-sm border-2 text-left text-sm ${value === p.id ? "border-brand-purple bg-lilac" : "border-ink bg-white"}`}>
            {p.preview_image_url ? <img src={p.preview_image_url} alt="" className="aspect-video w-full object-cover" loading="lazy" /> : <div className="aspect-video w-full bg-paper" aria-hidden />}
            <span className="block p-1 font-medium">{p.name}</span>
          </button>
        ))}
      </div>
      {items.length === 12 && <p className="text-xs text-muted">Showing the first 12. Search to narrow the list.</p>}
    </fieldset>
  );
}

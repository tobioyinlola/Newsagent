import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type Schemas, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "../components/ui";
import { contrastRatio, isHex } from "../lib/contrast";

const FONTS = ["Inter", "Poppins", "Montserrat", "Roboto", "Lato", "Open Sans", "Playfair Display"];
const TONES = ["confident", "friendly", "authoritative", "playful", "serious"];

function ColorField({ label, value, onChange, textOn }: { label: string; value: string; onChange: (v: string) => void; textOn: string }) {
  const ok = isHex(value);
  const ratio = ok ? contrastRatio(value, textOn) : 0;
  return (
    <Field label={label} hint={ok ? `Contrast with ${textOn === "#FFFFFF" ? "white" : "dark"} text: ${ratio}:1 ${ratio >= 4.5 ? "(passes)" : "(too low to read comfortably, try a darker or lighter shade)"}` : "Enter a color like #0B3D91"}>
      {(id) => (
        <div className="flex gap-2">
          <input aria-label={`${label} picker`} type="color" className="h-10 w-12 rounded border border-slate-300" value={ok ? value : "#000000"} onChange={(e) => onChange(e.target.value.toUpperCase())} />
          <input id={id} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)} maxLength={7} />
        </div>
      )}
    </Field>
  );
}

export function Brand() {
  const qc = useQueryClient();
  const kit = useQuery({ queryKey: ["brand"], queryFn: () => unwrap(api.GET("/v1/brand-kit")) });
  const [form, setForm] = useState<Schemas["BrandKitIn"] | null>(null);
  const [glossary, setGlossary] = useState<{ term: string; say: string }[]>([]);
  const [site, setSite] = useState("");
  const [draft, setDraft] = useState<Schemas["BrandDraft"] | null>(null);

  useEffect(() => {
    if (!kit.data) return;
    const k = kit.data;
    setForm({ primary_color: k.primary_color, accent_color: k.accent_color, secondary_colors: k.secondary_colors, fonts: k.fonts, pronunciation_glossary: k.pronunciation_glossary, tone: k.tone, logo_light_key: k.logo_light_key, logo_dark_key: k.logo_dark_key, source_url: k.source_url });
    setGlossary(Object.entries(k.pronunciation_glossary).map(([term, say]) => ({ term, say })));
  }, [kit.data]);

  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/v1/brand-kit", { body: { ...form!, pronunciation_glossary: Object.fromEntries(glossary.filter((g) => g.term.trim() && g.say.trim()).map((g) => [g.term.trim(), g.say.trim()])) } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brand"] }),
  });
  const imp = useMutation({ mutationFn: () => unwrap(api.POST("/v1/brand-kit/import", { body: { url: site } })), onSuccess: setDraft });

  if (!form || !kit.data) return kit.error ? <ErrorBox error={kit.error} /> : <p aria-busy="true">Loading…</p>;
  const set = (patch: Partial<Schemas["BrandKitIn"]>) => setForm({ ...form, ...patch });
  const valid = isHex(form.primary_color) && isHex(form.accent_color);

  return (
    <>
      <h1 className="text-2xl font-bold">Brand kit <span className="text-base font-normal text-slate-600">version {kit.data.version}</span></h1>
      <Notice>Your colors, fonts and tone style the graphics. The news-channel look and the “Featured” and “AI-generated anchor” labels are fixed for every video.</Notice>

      <Card title="Import from your website">
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); imp.mutate(); }}>
          <input aria-label="Website address" type="url" required placeholder="https://yourstartup.com" className={inputCls} value={site} onChange={(e) => setSite(e.target.value)} />
          <Button type="submit" variant="secondary" disabled={imp.isPending}>{imp.isPending ? "Reading…" : "Import"}</Button>
        </form>
        <ErrorBox error={imp.error} />
        {draft && (
          <div className="mt-4 space-y-2 text-sm">
            <p className="font-semibold">Here is what we found. Choose what to use:</p>
            {draft.primary_color && <div className="flex items-center gap-2"><span className="inline-block h-5 w-5 rounded border" style={{ background: draft.primary_color }} />Primary {draft.primary_color}<Button variant="secondary" onClick={() => set({ primary_color: draft.primary_color! })}>Use</Button></div>}
            {draft.accent_color && <div className="flex items-center gap-2"><span className="inline-block h-5 w-5 rounded border" style={{ background: draft.accent_color }} />Accent {draft.accent_color}<Button variant="secondary" onClick={() => set({ accent_color: draft.accent_color!, source_url: draft.source_url })}>Use</Button></div>}
            {!draft.primary_color && !draft.accent_color && <p>We couldn't find colors on that site. Enter them below.</p>}
          </div>
        )}
      </Card>

      <Card title="Colors">
        <div className="grid gap-4 sm:grid-cols-2">
          <ColorField label="Primary color" value={form.primary_color} onChange={(v) => set({ primary_color: v })} textOn="#FFFFFF" />
          <ColorField label="Accent color" value={form.accent_color} onChange={(v) => set({ accent_color: v })} textOn="#111111" />
        </div>
        {kit.data.accent_alternatives.length > 0 && (
          <div className="mt-4"><p className="mb-2 text-sm font-medium">Accent options</p>
            <div className="flex flex-wrap gap-2">{kit.data.accent_alternatives.map((c) => (
              <button key={c} type="button" aria-label={`Use accent ${c}`} onClick={() => set({ accent_color: c })} className="flex items-center gap-2 rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50"><span className="inline-block h-5 w-5 rounded border" style={{ background: c }} />{c}</button>
            ))}</div></div>
        )}
        {kit.data.contrast.some((c) => !c.passes) && (
          <div className="mt-4"><Notice tone="warn">Some saved colors are hard to read: {kit.data.contrast.filter((c) => !c.passes).map((c) => `${c.background} (${c.ratio}:1, try ${c.suggested_background})`).join("; ")}</Notice></div>
        )}
      </Card>

      <Card title="Fonts and tone">
        <div className="grid gap-4 sm:grid-cols-3">
          {(["heading", "body"] as const).map((k) => (
            <Field key={k} label={`${k[0].toUpperCase()}${k.slice(1)} font`}>{(id) => <select id={id} className={inputCls} value={form.fonts?.[k] ?? "Inter"} onChange={(e) => set({ fonts: { ...form.fonts, [k]: e.target.value } })}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select>}</Field>
          ))}
          <Field label="Tone">{(id) => <select id={id} className={inputCls} value={form.tone} onChange={(e) => set({ tone: e.target.value })}>{TONES.map((t) => <option key={t}>{t}</option>)}</select>}</Field>
        </div>
      </Card>

      <Card title="Pronunciation">
        <p className="mb-3 text-sm text-slate-700">Names the anchor might get wrong: your startup, product and founders.</p>
        <div className="space-y-2">
          {glossary.map((g, i) => (
            <div key={i} className="flex gap-2">
              <input aria-label={`Word ${i + 1}`} placeholder="Written as" className={inputCls} value={g.term} onChange={(e) => setGlossary(glossary.map((x, j) => (j === i ? { ...x, term: e.target.value } : x)))} />
              <input aria-label={`Pronounced ${i + 1}`} placeholder="Pronounced like (e.g. oh-yin-LOH-lah)" className={inputCls} value={g.say} onChange={(e) => setGlossary(glossary.map((x, j) => (j === i ? { ...x, say: e.target.value } : x)))} />
              <Button variant="secondary" aria-label={`Remove word ${i + 1}`} onClick={() => setGlossary(glossary.filter((_, j) => j !== i))}>Remove</Button>
            </div>
          ))}
          <Button variant="secondary" onClick={() => setGlossary([...glossary, { term: "", say: "" }])}>Add a word</Button>
        </div>
      </Card>

      <ErrorBox error={save.error} />
      {save.isSuccess && <Notice tone="ok">Saved as version {save.data.version}.</Notice>}
      <Button onClick={() => save.mutate()} disabled={!valid || save.isPending}>Save brand kit</Button>
    </>
  );
}

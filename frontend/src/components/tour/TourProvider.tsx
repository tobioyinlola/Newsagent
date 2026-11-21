import { createContext, type ReactNode, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { type TourBackend, type TourDef, type TourProgressMap, stepsSeen } from "./tourTypes";

type Ctx = {
  tours: TourDef[];
  progress: TourProgressMap;
  loaded: boolean;
  activeId: string | null;
  start: (id: string, fromStart?: boolean) => void;
};
const TourCtx = createContext<Ctx | null>(null);
export const useTours = () => useContext(TourCtx);

type Props = {
  backend: TourBackend;
  tours: TourDef[];
  autoStart?: string; // a tour to open by itself, once, for someone who has not seen or dismissed it
  autoReady?: boolean; // ...and only when it is a good moment (not while the first-run questions are on screen)
  children: ReactNode;
};

type Box = { top: number; left: number; width: number; height: number };
const PAD = 8;

const tidy = (p: unknown): TourProgressMap => (p && typeof p === "object" && !Array.isArray(p) ? (p as TourProgressMap) : {}); // a stubbed or odd reply must never break a page

export function TourProvider({ backend, tours, autoStart, autoReady = true, children }: Props) {
  const nav = useNavigate();
  const [progress, setProgress] = useState<TourProgressMap>({});
  const [loaded, setLoaded] = useState(false);
  const [active, setActive] = useState<{ id: string; index: number } | null>(null);
  const tried = useRef(false);

  useEffect(() => {
    let live = true;
    backend.load().then((p) => { if (live) { setProgress(tidy(p)); setLoaded(true); } }).catch(() => { if (live) setLoaded(true); }); // tours are never worth breaking a page over
    return () => { live = false; };
  }, [backend]);

  const save = useCallback((id: string, patch: Parameters<TourBackend["save"]>[1]) => {
    setProgress((p) => ({ ...p, [id]: { ...(p[id] ?? {}), ...(patch.reset ? { step: 0, done: false, dismissed: false } : patch) } })); // the screen moves on at once
    backend.save(id, patch).then((p) => setProgress(tidy(p))).catch(() => undefined);
  }, [backend]);

  const start = useCallback((id: string, fromStart = false) => {
    const def = tours.find((t) => t.id === id);
    if (!def) return;
    const p = progress[id];
    const seen = p?.step ?? 0;
    const resume = !fromStart && !!p && !p.done && seen > 0 && seen < def.steps.length;
    setActive({ id, index: resume ? seen : 0 });
    if (fromStart) save(id, { reset: true }); // a replay begins again, and counts as unfinished until it is
    else if (p?.dismissed) save(id, { dismissed: false });
  }, [tours, progress, save]);

  useEffect(() => {
    if (tried.current || !loaded || !autoReady || !autoStart || active) return;
    const def = tours.find((t) => t.id === autoStart);
    const p = progress[autoStart];
    if (!def) return;
    tried.current = true;
    if (!p?.done && !p?.dismissed) setActive({ id: autoStart, index: Math.min(p?.step ?? 0, def.steps.length - 1) });
  }, [loaded, autoReady, autoStart, tours, progress, active]);

  const def = active ? tours.find((t) => t.id === active.id) : undefined;
  const ctx = useMemo<Ctx>(() => ({ tours, progress, loaded, activeId: active?.id ?? null, start }), [tours, progress, loaded, active, start]);

  const go = (index: number) => {
    if (!def || !active) return;
    if (index >= def.steps.length) { save(def.id, { step: def.steps.length, done: true, dismissed: false }); setActive(null); return; }
    const next = Math.max(0, index);
    setActive({ id: def.id, index: next });
    save(def.id, { step: next });
  };
  const pause = () => { setActive(null); }; // Esc: stop for now, pick up here next time
  const skip = () => { if (def) save(def.id, { step: active?.index ?? 0, dismissed: true }); setActive(null); };

  return (
    <TourCtx.Provider value={ctx}>
      {children}
      {def && active && <TourStepView key={`${def.id}-${active.index}`} def={def} index={active.index} onBack={() => go(active.index - 1)} onNext={() => go(active.index + 1)} onPause={pause} onSkip={skip} navigate={nav} />}
    </TourCtx.Provider>
  );
}

function TourStepView({ def, index, onBack, onNext, onPause, onSkip, navigate }: { def: TourDef; index: number; onBack: () => void; onNext: () => void; onPause: () => void; onSkip: () => void; navigate: (to: string) => void }) {
  const step = def.steps[index];
  const last = index === def.steps.length - 1;
  const [box, setBox] = useState<Box | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const card = useRef<HTMLDivElement>(null);
  const next = useRef<HTMLButtonElement>(null);

  // On a phone the menu is a drawer that is closed. A step that points at a menu item opens it, and any other step closes it again.
  useEffect(() => {
    const inMenu = !!step.target?.startsWith("nav-") && window.innerWidth < 768;
    window.dispatchEvent(new CustomEvent("cf:menu", { detail: inMenu }));
    return () => { window.dispatchEvent(new CustomEvent("cf:menu", { detail: false })); };
  }, [step.target]);
  useEffect(() => { if (step.route && !window.location.pathname.replace(/^\/admin/, "").startsWith(step.route)) navigate(step.route); }, [step.route, navigate]);

  // find the thing to point at (it may take a moment to appear after a page change), and follow it as the page moves
  useEffect(() => {
    if (!step.target) { setBox(null); return; }
    let tries = 0;
    let scrolled = false;
    const find = () => document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`);
    const measure = () => {
      const el = find();
      if (!el || el.getClientRects().length === 0) { setBox(null); return false; }
      if (!scrolled) { scrolled = true; el.scrollIntoView?.({ block: "center", behavior: "auto" }); }
      const r = el.getBoundingClientRect();
      setBox({ top: r.top, left: r.left, width: r.width, height: r.height });
      return true;
    };
    const timer = window.setInterval(() => { tries += 1; if (measure() || tries > 20) { if (tries > 20) window.clearInterval(timer); } }, 150);
    measure();
    const onMove = () => measure();
    window.addEventListener("resize", onMove);
    window.addEventListener("scroll", onMove, true);
    return () => { window.clearInterval(timer); window.removeEventListener("resize", onMove); window.removeEventListener("scroll", onMove, true); };
  }, [step.target]);

  useLayoutEffect(() => { if (card.current) setSize({ w: card.current.offsetWidth, h: card.current.offsetHeight }); }, [box, index]);
  useEffect(() => { next.current?.focus(); }, [index]);

  // the card sits beside the highlighted thing when there is room, otherwise above or below it; with nothing to point at it is centred
  const vw = typeof window === "undefined" ? 1024 : window.innerWidth;
  const vh = typeof window === "undefined" ? 768 : window.innerHeight;
  const cw = Math.min(380, vw - 24);
  let style: React.CSSProperties = { left: Math.max(12, (vw - cw) / 2), top: Math.max(12, (vh - (size.h || 240)) / 2), width: cw };
  if (box) {
    const h = size.h || 240;
    const room = { right: vw - (box.left + box.width), below: vh - (box.top + box.height) };
    if (room.right > cw + 28) style = { left: box.left + box.width + PAD + 12, top: clamp(box.top + box.height / 2 - h / 2, 12, vh - h - 12), width: cw };
    else if (room.below > h + 24) style = { left: clamp(box.left, 12, vw - cw - 12), top: box.top + box.height + PAD + 12, width: cw };
    else style = { left: clamp(box.left, 12, vw - cw - 12), top: Math.max(12, box.top - h - PAD - 12), width: cw };
  }

  return (
    <div className="fixed inset-0 z-[60]" onKeyDown={(e) => { if (e.key === "Escape") onPause(); }}>
      {box ? <div aria-hidden="true" className="pointer-events-none fixed rounded-md border-2 border-brand-green" style={{ top: box.top - PAD, left: box.left - PAD, width: box.width + PAD * 2, height: box.height + PAD * 2, boxShadow: "0 0 0 9999px rgba(10,10,10,0.62)" }} /> : <div aria-hidden="true" className="fixed inset-0 bg-ink/60" />}
      <div ref={card} role="dialog" aria-modal="true" aria-label={`${def.title}: step ${index + 1} of ${def.steps.length}`} className="fixed max-h-[calc(100dvh-1.5rem)] overflow-y-auto rounded-sm border-2 border-ink bg-white p-4 text-ink shadow-xl" style={style}>
        <div className="flex items-center justify-between gap-2 text-xs font-bold uppercase tracking-wide text-muted"><span>{def.title}</span><span>Step {index + 1} of {def.steps.length}</span></div>
        <div className="mt-2 h-1.5 w-full rounded bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={def.steps.length} aria-valuenow={index + 1} aria-label="Tour progress"><div className="h-full rounded bg-brand-green" style={{ width: `${((index + 1) / def.steps.length) * 100}%` }} /></div>
        <h2 className="mt-3 text-lg font-bold">{step.title}</h2>
        <p className="mt-1 text-sm leading-relaxed">{step.body}</p>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <button type="button" className="text-sm font-semibold underline" onClick={onSkip}>Skip tour</button>
          <div className="flex gap-2">
            {index > 0 && <button type="button" className="min-h-10 rounded-sm border-2 border-ink px-3 py-1.5 text-sm font-bold hover:bg-paper" onClick={onBack}>Back</button>}
            <button ref={next} type="button" className="min-h-10 rounded-sm border-2 border-ink bg-brand-green px-4 py-1.5 text-sm font-bold hover:bg-ink hover:text-brand-green" onClick={onNext}>{last ? "Finish" : "Next"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

const clamp = (n: number, lo: number, hi: number) => Math.min(Math.max(n, lo), Math.max(lo, hi));

/** The "Guided tours" button and its list: every tour with how far along it is, and a way to start, resume or replay it. */
export function TourMenu({ className = "", label }: { className?: string; label?: ReactNode }) {
  const t = useTours();
  const [open, setOpen] = useState(false);
  if (!t || t.tours.length === 0) return null;
  const finished = t.tours.filter((d) => t.progress[d.id]?.done).length;
  return (
    <div className="relative">
      <button type="button" aria-haspopup="dialog" aria-expanded={open} data-tour="tours-menu" className={className || "min-h-11 rounded-sm border-2 border-ink px-3 py-2 text-sm font-bold hover:bg-paper"} onClick={() => setOpen((o) => !o)}>{label ?? <><span className="sm:hidden">Tours</span><span className="max-sm:hidden">Guided tours</span></>} <span className="text-xs font-semibold opacity-80">{finished}/{t.tours.length}</span></button>
      {open && (
        <div role="dialog" aria-label="Guided tours" className="absolute right-0 z-50 mt-2 w-[min(92vw,26rem)] rounded-sm border-2 border-ink bg-white p-3 text-ink shadow-xl" onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
          <div className="flex items-center justify-between"><p className="font-bold">Guided tours</p><button type="button" className="text-sm font-semibold underline" onClick={() => setOpen(false)}>Close</button></div>
          <p className="mt-1 text-xs text-muted">{finished} of {t.tours.length} finished. Your progress is saved, so you can stop and carry on any time.</p>
          <ul className="mt-3 max-h-[60vh] space-y-2 overflow-y-auto">
            {t.tours.map((d) => {
              const p = t.progress[d.id]; const seen = stepsSeen(d, p); const done = !!p?.done;
              return (
                <li key={d.id} className="rounded-sm border border-line p-3">
                  <div className="flex items-start justify-between gap-2"><div><p className="text-sm font-bold">{done && <span aria-hidden="true">✓ </span>}{d.title}</p><p className="text-xs text-muted">{d.summary}</p></div><span className="shrink-0 text-xs font-semibold">{done ? "Done" : `${seen}/${d.steps.length}`}</span></div>
                  <div className="mt-2 h-1.5 w-full rounded bg-line"><div className="h-full rounded bg-brand-green" style={{ width: `${(seen / d.steps.length) * 100}%` }} /></div>
                  <button type="button" className="mt-2 min-h-9 rounded-sm border-2 border-ink px-3 py-1 text-xs font-bold hover:bg-paper" onClick={() => { setOpen(false); t.start(d.id, done); }}>{done ? "Replay" : seen > 0 ? "Resume" : "Start"}</button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

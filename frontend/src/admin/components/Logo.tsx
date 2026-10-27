import { CF_PATHS, CF_SYMBOL_VIEWBOX, CF_VIEWBOX } from "./cf-paths";

// Primary Cover Founder logo (brand guideline p.12-13): web minimum width is 200px for the primary logo, so below
// that use the symbol (see `CFSymbol`). Only approved colourways: green on ink, ink on white/green, white on purple/red.
// No gradients, shadows or transparency on the mark.
export function Logo({ className = "", title = "Cover Founder" }: { className?: string; title?: string }) {
  return (
    <svg viewBox={CF_VIEWBOX} role="img" aria-label={title} className={className} fill="currentColor">
      {CF_PATHS.map((p, i) => <path key={i} fillRule={p.rule} d={p.d} />)}
    </svg>
  );
}

// The CF symbol (no name bar) is reserved for small sizes, under 200px wide (guideline p.13).
export function CFSymbol({ className = "", title = "Cover Founder" }: { className?: string; title?: string }) {
  return (
    <svg viewBox={CF_SYMBOL_VIEWBOX} role="img" aria-label={title} className={className} fill="currentColor">
      {CF_PATHS.slice(1, 4).map((p, i) => <path key={i} fillRule={p.rule} d={p.d} />)}
    </svg>
  );
}

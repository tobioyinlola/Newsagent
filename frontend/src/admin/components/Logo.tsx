import { CF_COVER_D, CF_FOUNDER_D, CF_PATHS, CF_SYMBOL_VIEWBOX, CF_VIEWBOX } from "./cf-paths";

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

// Secondary (horizontal) logo for headers and navigation bars, where the brand is introduced at a small height.
// Geometry: the symbol's frame is 5.8 units thick and 79 tall; the two word boxes share its right edge and middle line.
const T = 5.8, K = 2.9; // frame thickness; letter enlargement
const X0 = 1352.8; // inner right edge of the symbol's frame, where the word boxes start
const COVER_W = 34.6 * K + 16 + T, FOUNDER_W = 50.1 * K + 16 + T;
const frame = (x: number, y: number, w: number, h: number) => `M${x} ${y}h${w}v${h}h${-w}Z M${x + T} ${y + T}v${h - 2 * T}h${w - 2 * T}v${-(h - 2 * T)}Z`;

export function SecondaryLogo({ className = "", title = "Cover Founder" }: { className?: string; title?: string }) {
  const right = X0 + FOUNDER_W;
  return (
    <svg viewBox={`1250.6875 81 ${right - 1250.6875} 79.2`} role="img" aria-label={title} className={className} fill="currentColor">
      {CF_PATHS.slice(1, 4).map((p, i) => <path key={i} fillRule={p.rule} d={p.d} />)}
      <path fillRule="evenodd" d={frame(X0, 81, COVER_W, 39.6 + T / 2)} />
      <path fillRule="evenodd" d={frame(X0, 120.6 - T / 2, FOUNDER_W, 39.6 + T / 2)} />
      <path d={CF_COVER_D} transform={`translate(${X0 + T + 8} ${100.8 - 4.2 * K}) scale(${K}) translate(-1260.4 -167)`} />
      <path d={CF_FOUNDER_D} transform={`translate(${X0 + T + 8} ${140.2 - 4.2 * K}) scale(${K}) translate(-1299.5 -167)`} />
    </svg>
  );
}

// Favicon / app icon (guideline "Favicon"): the symbol inside a second frame, for very small sizes.
export function CFIcon({ className = "", title = "Cover Founder" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="1240.7 71 127.9 98.8" role="img" aria-label={title} className={className} fill="currentColor">
      <path fillRule="evenodd" d="M1240.7 71h127.9v98.8h-127.9Z M1245.2 75.5v89.8h118.9v-89.8Z" />
      {CF_PATHS.slice(1, 4).map((p, i) => <path key={i} fillRule={p.rule} d={p.d} />)}
    </svg>
  );
}

import { DEFAULT_PAGE_SIZE, PAGE_SIZES, pageCount, pageWindow, rangeText } from "../lib/paging";

type Props = {
  total: number;
  page: number; // zero-based
  size: number;
  onPage: (page: number) => void;
  onSize?: (size: number) => void; // when given, people can choose how many rows to see
  noun?: string; // "customers"
  busy?: boolean;
  className?: string;
};

const btn = "min-h-10 min-w-10 rounded-sm border-2 px-3 py-1.5 text-sm font-bold focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brand-purple disabled:cursor-not-allowed disabled:opacity-40";

/** "Showing 26 to 50 of 112", Previous / numbers / Next, and an optional rows-per-page choice. Shows nothing when everything fits on one page. */
export function Pager({ total, page, size, onPage, onSize, noun = "results", busy = false, className = "" }: Props) {
  const pages = pageCount(total, size);
  const smallest = onSize ? Math.min(...PAGE_SIZES) : size;
  if (total <= smallest && page === 0) return null;
  const last = pages - 1;
  return (
    <nav aria-label="Pagination" className={`mt-4 flex flex-wrap items-center justify-between gap-3 text-sm ${className}`}>
      <p className="text-muted" aria-live="polite">{rangeText(total, page, size, noun)}</p>
      <div className="flex flex-wrap items-center gap-2">
        {onSize && (
          <label className="flex items-center gap-2 text-muted">Rows
            <select aria-label="Rows per page" className="min-h-10 rounded-sm border-2 border-ink bg-white px-2 text-ink" value={size} onChange={(e) => { onSize(Number(e.target.value)); onPage(0); }}>
              {[...new Set([...PAGE_SIZES, size, DEFAULT_PAGE_SIZE])].sort((a, b) => a - b).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
        <button type="button" className={`${btn} border-ink bg-white hover:bg-paper`} disabled={busy || page <= 0} onClick={() => onPage(page - 1)} aria-label="Previous page">Previous</button>
        <ol className="hidden items-center gap-1 sm:flex">
          {pageWindow(page, pages).map((n, i) => n === "…"
            ? <li key={`gap-${i}`} aria-hidden="true" className="px-1 text-muted">…</li>
            : <li key={n}><button type="button" className={`${btn} ${n === page ? "border-ink bg-ink text-white" : "border-line bg-white hover:border-ink"}`} aria-label={`Page ${n + 1}`} aria-current={n === page ? "page" : undefined} disabled={busy} onClick={() => onPage(n)}>{n + 1}</button></li>)}
        </ol>
        <span className="font-semibold sm:hidden">Page {page + 1} of {pages}</span>
        <button type="button" className={`${btn} border-ink bg-brand-green hover:bg-ink hover:text-brand-green`} disabled={busy || page >= last} onClick={() => onPage(page + 1)} aria-label="Next page">Next</button>
      </div>
    </nav>
  );
}

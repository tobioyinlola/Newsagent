// Paging, the same everywhere. The server takes `limit` and `offset` and reports how many rows there are in all: in the
// `X-Total-Count` header for a list, or as `total` beside the items for an object.
export type Paged<T> = { items: T[]; total: number };

export const PAGE_SIZES = [10, 25, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 25;

/** The total from a reply: the header if there is one, else the body's `total`, else how many rows came back. */
export function totalOf(headers: Headers | undefined, body: unknown, rows: number, offset = 0): number {
  const h = Number(headers?.get("x-total-count"));
  if (headers?.has("x-total-count") && Number.isFinite(h)) return h;
  const t = Number((body as { total?: unknown } | null)?.total);
  return Number.isFinite(t) && (body as { total?: unknown } | null)?.total !== undefined ? t : offset + rows;
}

export const pageCount = (total: number, size: number) => Math.max(1, Math.ceil(total / Math.max(1, size)));

/** "Showing 26 to 50 of 112" */
export function rangeText(total: number, page: number, size: number, noun = "results"): string {
  if (total === 0) return `No ${noun}`;
  const from = page * size + 1;
  const to = Math.min(total, (page + 1) * size);
  return `Showing ${from.toLocaleString("en")} to ${to.toLocaleString("en")} of ${total.toLocaleString("en")} ${noun}`;
}

/** Page numbers to show, zero-based, with gaps as "…": the first, the last, and a few around the current one. */
export function pageWindow(page: number, pages: number, around = 1): (number | "…")[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i); // a few pages: show them all
  const keep = new Set<number>([0, pages - 1]);
  for (let i = page - around; i <= page + around; i++) if (i >= 0 && i < pages) keep.add(i);
  const sorted = [...keep].sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  sorted.forEach((n, i) => {
    if (i > 0 && n - sorted[i - 1] > 1) out.push(n - sorted[i - 1] === 2 ? n - 1 : "…");
    out.push(n);
  });
  return out;
}

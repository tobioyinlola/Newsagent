import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE, type Paged, pageCount } from "./paging";

type Options = { size?: number; refetchInterval?: number; enabled?: boolean };

/** One page of a list at a time. Changing the filters (`key`) goes back to page one, a page that no longer exists (the last row
 *  of the last page was removed) steps back, and the page already on screen stays until the next one arrives. */
export function usePaged<T, X extends object = object>(key: readonly unknown[], fetcher: (limit: number, offset: number) => Promise<Paged<T> & X>, opts: Options = {}) {
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(opts.size ?? DEFAULT_PAGE_SIZE);
  const filters = JSON.stringify(key);
  useEffect(() => { setPage(0); }, [filters, size]);
  const query = useQuery({
    queryKey: [...key, "page", page, size],
    queryFn: () => fetcher(size, page * size),
    placeholderData: keepPreviousData,
    refetchInterval: opts.refetchInterval,
    enabled: opts.enabled,
  });
  const total = query.data?.total ?? 0;
  const pages = pageCount(total, size);
  useEffect(() => { if (query.data && page > pages - 1) setPage(pages - 1); }, [query.data, page, pages]);
  return { items: query.data?.items ?? [], total, page, setPage, size, setSize, pages, query };
}

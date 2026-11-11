import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

// Which item is open or being edited lives in the address (?edit=…, ?open=…), so the browser's Back button, a refresh and a
// shared link all land where the person was. `set({ edit: "new", example: null })` changes several at once; null removes one.
export function useUrlState() {
  const [params, setParams] = useSearchParams();
  const get = useCallback((key: string) => params.get(key), [params]);
  const set = useCallback(
    (changes: Record<string, string | null>) =>
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(changes)) {
          if (v === null) next.delete(k);
          else next.set(k, v);
        }
        return next;
      }),
    [setParams],
  );
  return { get, set };
}

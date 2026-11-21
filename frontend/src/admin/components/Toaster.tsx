import { useEffect, useRef, useState } from "react";
import { subscribe } from "../lib/notify";

let showing: symbol | null = null; // only one pop-up is ever drawn, even if two Toasters are mounted

/** Shows the pop-up for a few seconds whenever something is saved. A newer message replaces the older one. */
export function Toaster() {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    const me = Symbol("toaster");
    if (showing === null) showing = me;
    const off = subscribe((m) => {
      if (showing !== me) return;
      setMessage(m);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setMessage(null), 3500);
    });
    return () => { off(); if (showing === me) showing = null; window.clearTimeout(timer.current); };
  }, []);
  // a quiet live region (not role="status", which pages already use for their own messages) so screen readers hear it without clashing
  return (
    <div aria-live="polite" aria-atomic="true" className="pointer-events-none fixed inset-x-0 top-4 z-50 flex justify-center px-4">
      {message && <div className="max-w-md rounded-sm border-2 border-ink bg-brand-green px-5 py-3 text-sm font-bold text-ink shadow-lg">{message === "Saved" ? "✓ Saved" : message}</div>}
    </div>
  );
}

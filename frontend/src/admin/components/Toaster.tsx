import { useEffect, useRef, useState } from "react";
import { subscribe } from "../lib/notify";
import { Toast } from "./ui";

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
  return message ? <Toast>{message === "Saved" ? "✓ Saved" : message}</Toast> : null;
}

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "./ui";

// "You're out of credits" popup. Shown when a video can't be started (a 402 from the API raises the event) or, with `forced`,
// as soon as the page is opened with no credit left.
export function OutOfCredits({ forced = false }: { forced?: boolean }) {
  const [open, setOpen] = useState(forced);
  const nav = useNavigate();
  useEffect(() => {
    const on = () => setOpen(true);
    window.addEventListener("cf:out-of-credits", on);
    return () => window.removeEventListener("cf:out-of-credits", on);
  }, []);
  if (!open) return null;
  const close = () => { setOpen(false); if (forced) nav("/dashboard"); };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4" onKeyDown={(e) => e.key === "Escape" && close()}>
      <div role="dialog" aria-modal="true" aria-labelledby="ooc-title" className="w-full max-w-md rounded-md border-2 border-ink bg-white p-6 shadow-xl">
        <h2 id="ooc-title" className="text-xl font-bold">You're out of credits</h2>
        <p className="mt-2 text-muted">Your free video has been used. Buy credits to create more videos. One video costs 1 credit.</p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link to="/billing" onClick={() => setOpen(false)} className="rounded-sm border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green">Buy credits</Link>
          <Button variant="secondary" autoFocus onClick={close}>Not now</Button>
        </div>
      </div>
    </div>
  );
}

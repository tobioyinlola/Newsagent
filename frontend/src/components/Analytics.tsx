import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { type Consent, getConsent, browserOptOut, onConsentChange, onOpenCookieSettings, setConsent } from "../lib/consent";
import { gaConfigured, isMeasurable, startAnalytics, stopAnalytics, trackPageView } from "../lib/ga";
import { recordVisit } from "../lib/visits";

// Counts visits, asks once about cookies, and then does what was chosen. Mount it once, inside the router.
export function TrackingConsent() {
  const loc = useLocation();
  const [consent, setChoice] = useState<Consent | null>(getConsent);
  useEffect(() => onConsentChange(setChoice), []);
  // Google Analytics: cookie-free until they accept, and off after a decline.
  useEffect(() => {
    if (!gaConfigured) return;
    if (consent === "denied") stopAnalytics();
    else if (isMeasurable(loc.pathname)) startAnalytics();
  }, [consent, loc.pathname]);
  // the app is one page, so each move to a new screen is reported by hand: to our own cookie-free counter, and to Google if allowed
  useEffect(() => {
    recordVisit(loc.pathname, loc.search);
    trackPageView(loc.pathname, loc.search);
  }, [loc.pathname, loc.search]);
  return gaConfigured && isMeasurable(loc.pathname) ? <CookieBanner consent={consent} /> : null;
}

function CookieBanner({ consent }: { consent: Consent | null }) {
  const [reopened, setReopened] = useState(false);
  useEffect(() => onOpenCookieSettings(() => setReopened(true)), []);
  if (browserOptOut()) return reopened ? <Notice onClose={() => setReopened(false)} /> : null; // their browser already said no
  if (consent !== null && !reopened) return null;
  const choose = (c: Consent) => { setConsent(c); setReopened(false); };
  return (
    <section role="region" aria-label="Cookie choices" className="fixed inset-x-0 bottom-0 z-50 border-t-2 border-ink bg-white p-4 text-ink shadow-[0_-8px_30px_rgba(0,0,0,0.18)] sm:p-5" style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-8 gap-y-3">
        <div className="min-w-0 flex-1 basis-80 text-sm">
          <p className="font-bold">Can we use analytics cookies?</p>
          <p className="mt-1 text-ink/80">We count visits to Cover Founder without cookies, so we know how many people use it. Until you choose, Google Analytics counts your visit without cookies too. If you accept, it also uses cookies to recognise returning visitors and see how people move around; if you decline, it’s switched off for you. We never send your name, email or company, and we don’t use advertising cookies. Change your mind any time in Cookie settings. <Link to="/privacy#storage" className="font-semibold underline">Read how we use cookies</Link>.</p>
        </div>
        <div className="flex shrink-0 gap-3">
          <button type="button" onClick={() => choose("denied")} className="min-h-11 min-w-28 rounded-lg border-2 border-ink bg-white px-5 py-2.5 text-sm font-bold hover:bg-paper focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brand-purple">{reopened && consent === "denied" ? "Keep declined" : "Decline"}</button>
          <button type="button" onClick={() => choose("granted")} className="min-h-11 min-w-28 rounded-lg border-2 border-ink bg-brand-green px-5 py-2.5 text-sm font-bold hover:bg-ink hover:text-brand-green focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brand-purple">{reopened && consent === "granted" ? "Keep accepted" : "Accept"}</button>
        </div>
      </div>
    </section>
  );
}

function Notice({ onClose }: { onClose: () => void }) {
  return (
    <section role="region" aria-label="Cookie choices" className="fixed inset-x-0 bottom-0 z-50 border-t-2 border-ink bg-white p-4 text-sm text-ink">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3"><p>Your browser is sending a “Do Not Track” or Global Privacy Control signal, so we don’t use analytics cookies for you.</p><button type="button" onClick={onClose} className="min-h-11 rounded-lg border-2 border-ink px-5 py-2.5 font-bold">OK</button></div>
    </section>
  );
}

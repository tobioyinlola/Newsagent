import { useEffect, useState } from "react";
import { Card } from "./ui";
import { browserOptOut, getConsent, onConsentChange, setConsent } from "../lib/consent";
import { trackingConfigured } from "../lib/ga";

// Settings > Profile: change the analytics choice without hunting for the footer link.
export function AnalyticsPreference() {
  const [choice, setChoice] = useState(getConsent);
  useEffect(() => onConsentChange(setChoice), []);
  if (!trackingConfigured) return null;
  const blocked = browserOptOut();
  return (
    <Card title="Analytics cookies">
      <label className="flex items-start gap-3 text-sm">
        <input type="checkbox" className="mt-1 h-4 w-4" checked={choice === "granted"} disabled={blocked} onChange={(e) => setConsent(e.target.checked ? "granted" : "denied")} />
        <span><b>Allow Google Analytics cookies</b><span className="block text-muted">Lets Google Analytics recognise you when you come back and see how people move around the site. It never receives your name, email or company, and we don’t use advertising cookies.</span></span>
      </label>
      <p className="mt-3 text-sm text-muted">{choice === "granted" ? "On: Google Analytics uses cookies." : choice === "denied" ? "Off: Google Analytics is switched off for you." : "Not chosen yet: Google Analytics counts your visit without cookies."} Separately, we count visits without any cookies, anonymously; that can’t be switched off here because it stores nothing on your device.</p>
      {blocked && <p className="mt-3 text-sm text-muted">Your browser is sending a “Do Not Track” or Global Privacy Control signal, so Google Analytics stays off and we don’t count your visits.</p>}
    </Card>
  );
}

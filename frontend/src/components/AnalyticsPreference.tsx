import { useEffect, useState } from "react";
import { Card } from "./ui";
import { browserOptOut, getConsent, onConsentChange, setConsent } from "../lib/consent";
import { gaConfigured } from "../lib/ga";

// Settings > Profile: change the analytics choice without hunting for the footer link.
export function AnalyticsPreference() {
  const [choice, setChoice] = useState(getConsent);
  useEffect(() => onConsentChange(setChoice), []);
  if (!gaConfigured) return null;
  const blocked = browserOptOut();
  return (
    <Card title="Analytics cookies">
      <label className="flex items-start gap-3 text-sm">
        <input type="checkbox" className="mt-1 h-4 w-4" checked={choice === "granted"} disabled={blocked} onChange={(e) => setConsent(e.target.checked ? "granted" : "denied")} />
        <span><b>Help us improve Cover Founder</b><span className="block text-muted">Lets us use Google Analytics to see which pages people use. It never receives your name, email or company, and we don’t use advertising cookies. Off by default; you can change it any time.</span></span>
      </label>
      {blocked && <p className="mt-3 text-sm text-muted">Your browser is sending a “Do Not Track” or Global Privacy Control signal, so analytics stay off.</p>}
    </Card>
  );
}

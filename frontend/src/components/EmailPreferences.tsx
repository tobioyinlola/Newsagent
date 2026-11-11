import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Card, ErrorBox, Notice } from "./ui";

type Pref = { subscribed: boolean; blocked: boolean };

// Whether this person gets product tips and offers by email. Account emails (sign-in codes, receipts, video updates) always arrive.
export function EmailPreferences() {
  const qc = useQueryClient();
  const pref = useQuery({ queryKey: ["marketing-pref"], queryFn: () => unwrap(api.GET("/v1/me/marketing")) as unknown as Promise<Pref> });
  const [choice, setChoice] = useState<boolean | null>(null); // what they just chose, shown at once while it saves
  const save = useMutation({
    mutationFn: (subscribed: boolean) => unwrap(api.PUT("/v1/me/marketing", { body: { subscribed } })) as unknown as Promise<Pref>,
    onSuccess: (p) => qc.setQueryData(["marketing-pref"], p),
    onSettled: () => setChoice(null), // saved: show the real answer; failed: go back to it
  });
  const p = pref.data;
  const subscribed = choice ?? p?.subscribed ?? true;
  return (
    <Card title="Emails from us">
      <ErrorBox error={pref.error ?? save.error} />
      {!p ? <p aria-busy="true" className="text-sm text-muted">Loading…</p> : (
        <div className="space-y-3 text-sm">
          <label className="flex items-start gap-3">
            <input type="checkbox" className="mt-1 h-4 w-4" checked={subscribed} onChange={(e) => { setChoice(e.target.checked); save.mutate(e.target.checked); }} />
            <span><b>Product tips and offers</b><span className="block text-muted">Occasional emails about getting more from Cover Founder. You can switch this off at any time, or use the unsubscribe link in any of them.</span></span>
          </label>
          <p className="text-muted">Emails about your account, like sign-in codes, receipts and your video updates, always arrive.</p>
          {p.blocked && <Notice tone="warn">We can’t deliver email to your address right now (it bounced or was reported as spam), so you won’t get product emails or other messages. If that’s a mistake, contact support.</Notice>}
        </div>
      )}
    </Card>
  );
}

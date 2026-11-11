import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { Card, ErrorBox, Notice } from "./ui";

type Pref = { subscribed: boolean; blocked: boolean };

// Whether this person gets product tips and offers by email. Account emails (sign-in codes, receipts, video updates) always arrive.
export function EmailPreferences() {
  const qc = useQueryClient();
  const pref = useQuery({ queryKey: ["marketing-pref"], queryFn: () => unwrap(api.GET("/v1/me/marketing")) as unknown as Promise<Pref> });
  const save = useMutation({
    mutationFn: (subscribed: boolean) => unwrap(api.PUT("/v1/me/marketing", { body: { subscribed } })) as unknown as Promise<Pref>,
    onSuccess: (p) => qc.setQueryData(["marketing-pref"], p),
  });
  const p = save.data ?? pref.data;
  return (
    <Card title="Emails from us">
      <ErrorBox error={pref.error ?? save.error} />
      {!p ? <p aria-busy="true" className="text-sm text-muted">Loading…</p> : (
        <div className="space-y-3 text-sm">
          <label className="flex items-start gap-3">
            <input type="checkbox" className="mt-1 h-4 w-4" checked={p.subscribed} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span><b>Product tips and offers</b><span className="block text-muted">Occasional emails about getting more from Cover Founder. You can switch this off at any time, or use the unsubscribe link in any of them.</span></span>
          </label>
          <p className="text-muted">Emails about your account, like sign-in codes, receipts and your video updates, always arrive.</p>
          {p.blocked && <Notice tone="warn">We can’t deliver email to your address right now (it bounced or was reported as spam), so you won’t get product emails or other messages. If that’s a mistake, contact support.</Notice>}
        </div>
      )}
    </Card>
  );
}

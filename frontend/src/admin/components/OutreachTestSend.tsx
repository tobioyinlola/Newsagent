import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { distributionApi } from "../../lib/distribution";
import { getToken } from "../lib/auth";
import { Button, ErrorBox, Notice, inputCls } from "./ui";

// A sample outreach email to an address of the operator's own, sent exactly the way real ones go out.
export function TestSend({ canManage }: { canManage: boolean }) {
  const [to, setTo] = useState("");
  const send = useMutation({ mutationFn: () => distributionApi("admin/outreach/test-send", getToken(), "POST", { to: to.trim() }) });
  if (!canManage) return null;
  return (
    <div className="mt-4 rounded-lg border border-line p-3">
      <label className="block text-sm font-semibold">Send a test email to yourself<input className={inputCls} type="email" value={to} onChange={(e) => { setTo(e.target.value); send.reset(); }} placeholder="you@example.com" /></label>
      <p className="mt-1 text-xs text-muted">It goes out exactly like a real one. Check that it lands in your inbox (not spam) before the first real send.</p>
      <div className="mt-2"><Button type="button" variant="secondary" disabled={!to.trim() || send.isPending} onClick={() => send.mutate()}>{send.isPending ? "Sending…" : "Send test email"}</Button></div>
      <ErrorBox error={send.error} />
      {send.isSuccess && <div className="mt-2"><Notice tone="ok">Sent. Look in your inbox, and in spam too.</Notice></div>}
    </div>
  );
}

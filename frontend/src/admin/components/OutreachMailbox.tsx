import { useState } from "react";
import { ApiError } from "../../api/client";
import { distributionApi } from "../../lib/distribution";
import { getToken } from "../lib/auth";
import { TestSend } from "./OutreachTestSend";
import { Button, Card, Notice, inputCls } from "./ui";

export type MailboxStatus = {
  connected: boolean; address: string | null; source: "back office" | "environment" | null; mode: "smtp" | "relay" | null; sends_via: string | null;
  connected_by: string | null; connected_at: string | null; last_polled_at: string | null; last_error: string; ready: boolean; outreach_on: boolean;
};
type Tried = { ok: boolean; mode: "smtp" | "relay" | null; message: string; steps: string[] };
type Problem = { message: string; steps: string[] };

const request = <T,>(path: string, method = "GET", body?: unknown) => distributionApi<T>(path, getToken(), method, body);
const when = (v: string | null) => (v ? new Date(v).toLocaleString() : "not yet");
const problem = (e: unknown): Problem => {
  const d = e instanceof ApiError ? (e.detail as { message?: string; steps?: string[] } | string | undefined) : undefined;
  if (d && typeof d === "object") return { message: d.message ?? "That did not work. Please try again.", steps: d.steps ?? [] };
  return { message: e instanceof Error ? e.message : "That did not work. Please try again.", steps: [] };
};

const STEPS: { text: string; link?: { href: string; label: string } }[] = [
  { text: "In the Google account you will use, turn on 2-step verification.", link: { href: "https://myaccount.google.com/signinoptions/two-step-verification", label: "Open 2-step verification" } },
  { text: "Create an app password (a 16-letter password just for this app) and copy it.", link: { href: "https://myaccount.google.com/apppasswords", label: "Open app passwords" } },
  { text: "In Gmail, make sure IMAP is switched on, so we can read the replies.", link: { href: "https://mail.google.com/mail/u/0/#settings/fwdandpop", label: "Open Gmail settings" } },
  { text: "Paste the Gmail address and the app password below, then press Connect." },
];

// Connect the Gmail that outreach is sent from and replies are read from. The password is encrypted on our side and never shown again.
export function OutreachMailbox({ status, canManage, onChanged }: { status: MailboxStatus; canManage: boolean; onChanged: () => void }) {
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<"" | "test" | "connect" | "disconnect">("");
  const [tried, setTried] = useState<Tried | null>(null);
  const [fail, setFail] = useState<Problem | null>(null);
  const [done, setDone] = useState("");
  const [changing, setChanging] = useState(false);
  const [sure, setSure] = useState(false);
  const form = !status.connected || changing;
  const body = { address: address.trim(), app_password: password };
  const check = async () => { setBusy("test"); setFail(null); setTried(null); setDone(""); try { setTried(await request<Tried>("admin/outreach/mailbox/test", "POST", body)); } catch (e) { setFail(problem(e)); } finally { setBusy(""); } };
  const connect = async () => {
    setBusy("connect"); setFail(null); setTried(null); setDone("");
    try { await request("admin/outreach/mailbox", "PUT", body); setPassword(""); setChanging(false); setDone("Connected. Emails that were waiting for a mailbox are now on their way."); onChanged(); } catch (e) { setFail(problem(e)); } finally { setBusy(""); }
  };
  const disconnect = async () => { setBusy("disconnect"); setFail(null); try { await request("admin/outreach/mailbox", "DELETE"); setSure(false); setDone("Disconnected. Nothing will be sent until a mailbox is connected again."); onChanged(); } catch (e) { setFail(problem(e)); } finally { setBusy(""); } };
  return (
    <div className="space-y-4">
      {!status.outreach_on && <Notice tone="warn">Outreach is switched off on the server (<code>OUTREACH_AI</code>). You can connect a mailbox now; nothing is sent until it is switched on.</Notice>}
      {status.connected && (
        <Card title="Connected">
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            <div><dt className="text-xs text-muted">Gmail address</dt><dd className="font-semibold">{status.address}</dd></div>
            <div><dt className="text-xs text-muted">Emails are sent through</dt><dd className="font-semibold">{status.sends_via ?? "unknown"}</dd></div>
            <div><dt className="text-xs text-muted">Connected by</dt><dd>{status.connected_by ?? "unknown"} · {when(status.connected_at)}</dd></div>
            <div><dt className="text-xs text-muted">Inbox last checked</dt><dd>{when(status.last_polled_at)}</dd></div>
          </dl>
          {status.mode === "relay" && <p className="mt-3 text-sm text-muted">Our hosting does not allow sending straight through Gmail, so emails go out through our email service with this Gmail as the reply address, and a copy is sent to it. Replies and copies still land in this Gmail.</p>}
          {status.last_error && <div className="mt-3" role="alert"><Notice tone="warn">{status.last_error}</Notice></div>}
          {canManage && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button type="button" variant="secondary" disabled={!!busy} onClick={() => { setChanging(!changing); setFail(null); setTried(null); }}>{changing ? "Keep this Gmail" : "Use a different Gmail or password"}</Button>
              {!sure ? <Button type="button" variant="secondary" disabled={!!busy} onClick={() => setSure(true)}>Disconnect</Button>
                : <><span className="text-sm font-semibold">Stop sending and reading replies?</span><Button type="button" variant="danger" disabled={!!busy} onClick={() => void disconnect()}>{busy === "disconnect" ? "Disconnecting…" : "Yes, disconnect"}</Button><Button type="button" variant="secondary" onClick={() => setSure(false)}>Cancel</Button></>}
            </div>
          )}
        </Card>
      )}
      {status.source === "environment" && !status.connected && <Notice tone="ok">Outreach is using the mailbox set on the server ({status.address ?? "no address"}). You can connect a Gmail here instead.</Notice>}
      {form && (
        <Card title={status.connected ? "Use a different Gmail" : "Connect your Gmail"}>
          <p className="text-sm text-muted">Outreach emails are sent from this Gmail and the outlets' replies come back to it, so you see everything in Gmail as well as here. Google needs an <strong>app password</strong> for this:</p>
          <ol className="mt-3 space-y-2 text-sm">
            {STEPS.map((s, i) => <li key={s.text} className="flex gap-2"><span className="font-bold">{i + 1}.</span><span>{s.text}{s.link && <> <a className="font-semibold underline" href={s.link.href} target="_blank" rel="noreferrer">{s.link.label}</a></>}</span></li>)}
          </ol>
          <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void connect(); }}>
            <label className="block text-sm font-semibold">Gmail address<input className={inputCls} type="email" autoComplete="off" placeholder="name@gmail.com" value={address} onChange={(e) => { setAddress(e.target.value); setTried(null); }} disabled={!canManage} /></label>
            <label className="block text-sm font-semibold">App password<input className={inputCls} type="password" autoComplete="new-password" placeholder="abcd efgh ijkl mnop" value={password} onChange={(e) => { setPassword(e.target.value); setTried(null); }} disabled={!canManage} /></label>
            {canManage ? (
              <div className="flex flex-wrap gap-2 sm:col-span-2">
                <Button type="button" variant="secondary" disabled={!address.trim() || !password.trim() || !!busy} onClick={() => void check()}>{busy === "test" ? "Checking…" : "Check connection"}</Button>
                <Button type="submit" disabled={!address.trim() || !password.trim() || !!busy}>{busy === "connect" ? "Connecting…" : "Connect Gmail"}</Button>
              </div>
            ) : <p className="text-sm text-muted sm:col-span-2">You can see this page but not change the mailbox.</p>}
          </form>
          <p className="mt-3 text-xs text-muted">The password is encrypted and cannot be seen again, here or anywhere else. You can remove it any time in your Google account or by pressing Disconnect.</p>
          <div role="status" aria-live="polite" className="mt-3">
            {tried && <Notice tone={tried.ok ? "ok" : "warn"}>{tried.message}</Notice>}
          </div>
          {(fail || (tried && !tried.ok)) && (
            <div role="alert" className="mt-3 space-y-2">
              {fail && <Notice tone="warn">{fail.message}</Notice>}
              {((fail?.steps ?? tried?.steps) ?? []).length > 0 && <ul className="list-disc pl-5 text-sm">{(fail?.steps ?? tried?.steps ?? []).map((s) => <li key={s}>{s}</li>)}</ul>}
            </div>
          )}
        </Card>
      )}
      <div role="status" aria-live="polite">{done && <Notice tone="ok">{done}</Notice>}</div>
      {status.ready && <Card title="Try it"><p className="text-sm text-muted">Send yourself a sample outreach email, exactly the way a real one goes out, and check it arrives (and not in spam).</p><TestSend canManage={canManage} /></Card>}
    </div>
  );
}

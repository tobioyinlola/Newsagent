import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Logo } from "../components/Logo";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "../components/ui";
import { setToken } from "../lib/auth";

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="cf-stripes flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md space-y-6">
        <Logo className="w-52 text-brand-green" />
        {children}
      </div>
    </div>
  );
}

// An invited team member's side: open the emailed link, choose a password, confirm the emailed code.
export function Join() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const nav = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const preview = useQuery({ queryKey: ["staff-invite", token], queryFn: () => unwrap(api.POST("/v1/auth/staff/invite", { body: { token } })), enabled: token.length >= 10, retry: false });
  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/staff/accept/start", { body: { token, password, name } })),
    onSuccess: () => setSent(true),
  });
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/staff/accept/verify", { body: { token, code: code.trim() } })),
    onSuccess: (s) => { setToken(s.token); qc.clear(); nav("/", { replace: true }); },
  });

  if (!token || preview.isError) {
    return <Shell><Notice tone="warn">This invitation link isn't valid or has expired. Ask the person who invited you to send a new one.</Notice></Shell>;
  }
  const p = preview.data;
  return (
    <Shell>
      <Card title="Join the Cover Founder team">
        {!p ? <p aria-busy="true">Checking your invitation…</p> : sent ? (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); verify.mutate(); }}>
            <Notice tone="ok">We emailed a 6-digit code to {p.email_hint}. Enter it to finish joining.</Notice>
            <Field label="6-digit code">{(id) => <input id={id} required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} />}</Field>
            <ErrorBox error={verify.error} />
            <Button type="submit" disabled={verify.isPending}>Join the team</Button>
          </form>
        ) : (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); start.mutate(); }}>
            <p className="text-sm">{p.invited_by} invited <strong>{p.email_hint}</strong> to join as <strong>{p.role_label}</strong>.</p>
            <Field label="Your name">{(id) => <input id={id} required autoComplete="name" className={inputCls} defaultValue={p.name} onChange={(e) => setName(e.target.value)} />}</Field>
            <Field label="Choose a password" hint="At least 10 characters.">{(id) => <input id={id} type="password" required autoComplete="new-password" className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
            <ErrorBox error={start.error} />
            <Button type="submit" disabled={start.isPending}>Email me a code</Button>
          </form>
        )}
      </Card>
    </Shell>
  );
}

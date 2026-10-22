import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Schemas, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "../components/ui";
import { getToken, setToken } from "../lib/auth";

type Session = Schemas["SessionOut"];

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-md space-y-4 p-6">
      <h1 className="text-2xl font-extrabold text-blue-900">Newsagent</h1>
      {children}
    </div>
  );
}

function useFinish(first: boolean) {
  const nav = useNavigate();
  const qc = useQueryClient();
  return (s: Session) => {
    setToken(s.token);
    qc.clear();
    if (s.mfa_required) nav("/mfa", { replace: true });
    else if (s.mfa_enrolment_required) nav("/security?setup=1", { replace: true });
    else nav(first ? "/brand" : "/projects", { replace: true });
  };
}

function CodeStep({ sent, onSubmit, pending, error, onBack }: { sent: string; onSubmit: (code: string) => void; pending: boolean; error: unknown; onBack: () => void }) {
  const [code, setCode] = useState("");
  return (
    <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); onSubmit(code.trim()); }}>
      <Notice tone="ok">If {sent} can sign in, we have emailed a 6-digit code. It expires in 10 minutes.</Notice>
      <Field label="Sign-in code">
        {(id) => <input id={id} required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} />}
      </Field>
      <ErrorBox error={error} />
      <div className="flex gap-3">
        <Button type="submit" disabled={pending}>Sign in</Button>
        <Button type="button" variant="secondary" onClick={onBack}>Use a different email</Button>
      </div>
    </form>
  );
}

export function Login() {
  const [params] = useSearchParams();
  const invite = params.get("invite");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const finish = useFinish(false);
  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/login/start", { body: { email } })),
    onSuccess: () => setSent(email.trim()),
  });
  const verify = useMutation({
    mutationFn: (code: string) => unwrap(api.POST("/v1/auth/login/verify", { body: { email: sent ?? email, code } })),
    onSuccess: finish,
  });
  if (invite) return <Navigate to={`/signup?code=${encodeURIComponent(invite)}`} replace />;
  if (getToken()) return <Navigate to="/projects" replace />;
  return (
    <Shell>
      <Card title="Sign in">
        {sent ? (
          <CodeStep sent={sent} onSubmit={(c) => verify.mutate(c)} pending={verify.isPending} error={verify.error} onBack={() => { setSent(null); verify.reset(); }} />
        ) : (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); start.mutate(); }}>
            <Field label="Email">{(id) => <input id={id} type="email" required autoComplete="email" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
            <ErrorBox error={start.error} />
            <Button type="submit" disabled={start.isPending}>Email me a code</Button>
          </form>
        )}
      </Card>
      <p className="text-sm text-slate-600">Invite-only pilot. Have an invite link? Open it to create your workspace.</p>
    </Shell>
  );
}

export function Signup() {
  const [params] = useSearchParams();
  const inviteCode = params.get("code") ?? "";
  const [sent, setSent] = useState(false);
  const finish = useFinish(true);
  const preview = useQuery({
    queryKey: ["invite", inviteCode],
    queryFn: () => unwrap(api.GET("/v1/auth/invite/{code}", { params: { path: { code: inviteCode } } })),
    enabled: inviteCode.length > 0,
    retry: false,
  });
  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/signup/start", { body: { invite_code: inviteCode } })),
    onSuccess: () => setSent(true),
  });
  const verify = useMutation({
    mutationFn: (code: string) => unwrap(api.POST("/v1/auth/signup/verify", { body: { invite_code: inviteCode, code } })),
    onSuccess: finish,
  });
  return (
    <Shell>
      <Card title="Create your workspace">
        {!inviteCode || preview.isError ? (
          <Notice tone="warn">This invite link is not valid or has expired. Ask us for a new one, or <Link className="underline" to="/login">sign in</Link>.</Notice>
        ) : preview.isLoading ? (
          <p aria-busy="true">Loading…</p>
        ) : sent && preview.data ? (
          <CodeStep sent={preview.data.email_hint} onSubmit={(c) => verify.mutate(c)} pending={verify.isPending} error={verify.error} onBack={() => { setSent(false); verify.reset(); }} />
        ) : (
          <div className="space-y-4">
            <p>You have been invited to set up <strong>{preview.data?.workspace_name}</strong>. We will email a code to <strong>{preview.data?.email_hint}</strong> to confirm it is you.</p>
            <ErrorBox error={start.error} />
            <Button onClick={() => start.mutate()} disabled={start.isPending}>Email me a code</Button>
          </div>
        )}
      </Card>
    </Shell>
  );
}

export function MfaChallenge() {
  const [code, setCode] = useState("");
  const nav = useNavigate();
  const qc = useQueryClient();
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/mfa/verify", { body: { code: code.trim() } })),
    onSuccess: () => { qc.clear(); nav("/projects", { replace: true }); },
  });
  if (!getToken()) return <Navigate to="/login" replace />;
  return (
    <Shell>
      <Card title="Two-step verification">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); verify.mutate(); }}>
          <Field label="Authenticator code" hint="The 6-digit code from your authenticator app, or one of your recovery codes.">
            {(id) => <input id={id} required autoComplete="one-time-code" className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} />}
          </Field>
          <ErrorBox error={verify.error} />
          <div className="flex gap-3">
            <Button type="submit" disabled={verify.isPending}>Verify</Button>
            <Button type="button" variant="secondary" onClick={() => { setToken(null); nav("/login"); }}>Cancel</Button>
          </div>
        </form>
      </Card>
    </Shell>
  );
}

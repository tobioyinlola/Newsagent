import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Schemas, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice, Toast } from "../components/ui";
import { Logo } from "../components/Logo";
import { getToken, setToken } from "../lib/auth";

type Session = Schemas["SessionOut"];

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

function PasswordField({ label = "Password", value, onChange, autoComplete, hint }: { label?: string; value: string; onChange: (v: string) => void; autoComplete: string; hint?: string }) {
  return (
    <Field label={label} hint={hint}>
      {(id) => <input id={id} type="password" required autoComplete={autoComplete} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

function CodeField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Field label="6-digit code">
      {(id) => <input id={id} required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

function useFinish() {
  const nav = useNavigate();
  const qc = useQueryClient();
  return (s: Session) => {
    setToken(s.token);
    qc.clear();
    nav(s.otp_required ? "/otp" : "/", { replace: true });
  };
}

export function Login() {
  const [params] = useSearchParams();
    const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const finish = useFinish();
  const login = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/login", { body: { email, password } })),
    onSuccess: finish,
  });
  if (getToken()) return <Navigate to="/" replace />;
  return (
    <Shell>
      <Card title="Back office sign-in">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); login.mutate(); }}>
          {params.get("expired") && <Notice tone="info">You were signed out (sessions end after an hour without activity). Please sign in again.</Notice>}
          <Field label="Email">{(id) => <input id={id} type="email" required autoComplete="email" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
          <PasswordField value={password} onChange={setPassword} autoComplete="current-password" />
          <ErrorBox error={login.error} />
          <Button type="submit" disabled={login.isPending}>Sign in</Button>
        </form>
        <p className="mt-3 text-sm"><Link className="underline" to="/forgot">Forgot your password?</Link></p>
      </Card>
      <p className="text-sm text-white">For Cover Founder operators only. A code is emailed to you each time you sign in.</p>
    </Shell>
  );
}

// Operators confirm each sign-in with a code we email them.
export function OtpChallenge() {
  const [code, setCode] = useState("");
  const nav = useNavigate();
  const qc = useQueryClient();
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/login/otp", { body: { code: code.trim() } })),
    onSuccess: () => { qc.clear(); nav("/", { replace: true }); },
  });
  const resend = useMutation({ mutationFn: () => unwrap(api.POST("/v1/auth/login/otp/resend")) });
  if (!getToken()) return <Navigate to="/login" replace />;
  return (
    <Shell>
      <Card title="Check your email">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); verify.mutate(); }}>
          <Notice tone="ok">We emailed you a 6-digit code to finish signing in.</Notice>
          <CodeField value={code} onChange={setCode} />
          <ErrorBox error={verify.error ?? resend.error} />
          {resend.isSuccess && <Notice tone="ok">A new code is on its way.</Notice>}
          <div className="flex gap-3">
            <Button type="submit" disabled={verify.isPending}>Verify</Button>
            <Button type="button" variant="secondary" onClick={() => resend.mutate()} disabled={resend.isPending}>Send a new code</Button>
            <Button type="button" variant="secondary" onClick={() => { setToken(null); nav("/login"); }}>Cancel</Button>
          </div>
        </form>
      </Card>
    </Shell>
  );
}

export function Forgot() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/password/forgot", { body: { email } })),
    onSuccess: () => setSent(true),
  });
  const [done, setDone] = useState(false);
  const reset = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/password/reset", { body: { email, code: code.trim(), new_password: password } })),
    onSuccess: () => { setDone(true); window.setTimeout(() => nav("/login", { replace: true }), 2200); },
  });
  return (
    <Shell>
      {done && <Toast>Password updated. Taking you to sign in…</Toast>}
      <Card title="Reset your password">
        {sent ? (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); reset.mutate(); }}>
            <Notice tone="ok">If {email} has an account, we have emailed a 6-digit code. It expires in 10 minutes; if you ask for more than one, use the newest.</Notice>
            <CodeField value={code} onChange={setCode} />
            <PasswordField label="New password" value={password} onChange={setPassword} autoComplete="new-password" hint="At least 10 characters." />
            <ErrorBox error={reset.error} />
            <Button type="submit" disabled={reset.isPending}>Set new password</Button>
          </form>
        ) : (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); start.mutate(); }}>
            <Field label="Email">{(id) => <input id={id} type="email" required autoComplete="email" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
            <ErrorBox error={start.error} />
            <Button type="submit" disabled={start.isPending}>Email me a code</Button>
          </form>
        )}
        <p className="mt-3 text-sm"><Link className="underline" to="/login">Back to sign in</Link></p>
      </Card>
    </Shell>
  );
}

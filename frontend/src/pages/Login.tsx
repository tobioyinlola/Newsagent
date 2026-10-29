import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Schemas, unwrap } from "../api/client";
import { Combobox } from "../components/Combobox";
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
    nav(s.otp_required ? "/otp" : "/dashboard", { replace: true });
  };
}

export function Login() {
  const [params] = useSearchParams();
  const invite = params.get("invite");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const finish = useFinish();
  const login = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/login", { body: { email, password } })),
    onSuccess: finish,
  });
  if (invite) return <Navigate to={`/signup?code=${encodeURIComponent(invite)}`} replace />;
  if (getToken()) return <Navigate to="/dashboard" replace />;
  return (
    <Shell>
      <Card title="Sign in">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); login.mutate(); }}>
          {params.get("expired") && <Notice tone="info">You were signed out (sessions end after an hour without activity). Please sign in again.</Notice>}
          <Field label="Email">{(id) => <input id={id} type="email" required autoComplete="email" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
          <PasswordField value={password} onChange={setPassword} autoComplete="current-password" />
          <ErrorBox error={login.error} />
          <Button type="submit" disabled={login.isPending}>Sign in</Button>
        </form>
        <p className="mt-3 text-sm"><Link className="underline" to="/forgot">Forgot your password?</Link></p>
      </Card>
      <p className="text-sm text-white">New here? <Link className="underline" to="/signup">Create your free account</Link>. Have an invite link? Open it to join your workspace.</p>
    </Shell>
  );
}

type Industry = NonNullable<Schemas["SignupStartIn"]["industry"]>;
const INDUSTRIES: [Industry, string, string][] = [
  ["energy", "Energy", "oil, gas, fuels, energy equipment, chemicals, materials, metals and mining"],
  ["industrials", "Industrials", "aerospace, defense, machinery, transportation, commercial services"],
  ["consumer", "Consumer", "retail, apparel, automotive, leisure goods, beverages, tobacco, personal care"],
  ["agriculture", "Agriculture", "food and farming"],
  ["health_care", "Health Care", "pharmaceuticals, biotechnology, medical equipment"],
  ["financials", "Financials", "banks, insurance, capital markets"],
  ["real_estate", "Real Estate", "REITs and development"],
  ["technology", "Technology", "AI, software, hardware, semiconductors, IT services"],
  ["government", "Government", "politics and public institutions"],
  ["entertainment", "Entertainment", "arts, music and sports"],
  ["education", "Education", "schools, universities and learning"],
  ["other", "Others", "none of the above: tell us your industry"],
];

export function Signup() {
  const [params] = useSearchParams();
  const inviteCode = params.get("code") ?? "";
  const [business, setBusiness] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [industry, setIndustry] = useState("");
  const [industryOther, setIndustryOther] = useState("");
  const [countries, setCountries] = useState<{ code: string; name: string }[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  useEffect(() => { fetch("/geo/countries.json").then((r) => r.json()).then(setCountries).catch(() => setCountries([])); }, []);
  const countryCode = countries.find((c) => c.name === country)?.code;
  useEffect(() => { // the cities of the country that was picked (one small file each); any city can still be typed
    setCities([]);
    if (countryCode) fetch(`/geo/${countryCode}.json`).then((r) => (r.ok ? r.json() : [])).then(setCities).catch(() => setCities([]));
  }, [countryCode]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [sent, setSent] = useState(false);
  const [hint, setHint] = useState("");
  const [code, setCode] = useState("");
  const [created, setCreated] = useState(false);
  const finish = useFinish();
  const preview = useQuery({
    queryKey: ["invite", inviteCode],
    queryFn: () => unwrap(api.GET("/v1/auth/invite/{code}", { params: { path: { code: inviteCode } } })),
    enabled: inviteCode.length > 0,
    retry: false,
  });
  const body = inviteCode ? { invite_code: inviteCode } : { email: email.trim(), business_name: business.trim(), city: city.trim(), country: country.trim(), industry: industry as Industry, industry_other: industry === "other" ? industryOther.trim() : undefined };
  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/signup/start", { body: { ...body, password } })),
    onSuccess: (r) => { setHint(r.email_hint ?? email); setSent(true); },
  });
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/signup/verify", { body: { ...(inviteCode ? { invite_code: inviteCode } : { email: email.trim() }), code: code.trim() } })),
    onSuccess: (s) => { setCreated(true); window.setTimeout(() => finish(s), 1800); },
  });
  const mismatch = confirm.length > 0 && confirm !== password;
  if (getToken() && !created) return <Navigate to="/dashboard" replace />;
  return (
    <Shell>
      {created && <Toast>Account created. Taking you to your dashboard…</Toast>}
      <Card title={inviteCode ? "Create your workspace" : "Publish your story free"}>
        {inviteCode && preview.isError ? (
          <Notice tone="warn">This invite link is not valid or has expired. You can <Link className="underline" to="/signup">sign up here</Link> instead, or <Link className="underline" to="/login">sign in</Link>.</Notice>
        ) : inviteCode && preview.isLoading ? (
          <p aria-busy="true">Loading…</p>
        ) : sent ? (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); verify.mutate(); }}>
            <Notice tone="ok">We emailed a 6-digit code to {hint}. Enter it to confirm your email. It expires in 10 minutes; if you ask for more than one, use the newest.</Notice>
            <CodeField value={code} onChange={setCode} />
            <ErrorBox error={verify.error ?? start.error} />
            <div className="flex flex-wrap gap-3">
              <Button type="submit" disabled={verify.isPending}>Verify and create workspace</Button>
              <Button type="button" variant="secondary" onClick={() => start.mutate()} disabled={start.isPending}>Send a new code</Button>
            </div>
          </form>
        ) : (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (!mismatch) start.mutate(); }}>
            {inviteCode ? (
              <p>You have been invited to set up <strong>{preview.data?.workspace_name}</strong> as <strong>{preview.data?.email_hint}</strong>. Choose a password; then we will email a code to confirm it is you.</p>
            ) : (
              <>
                <p>Create a free workspace for your business. We'll email you a 6-digit code to confirm your email before you get in.</p>
                <Field label="Business name">{(id) => <input id={id} required minLength={2} maxLength={200} autoComplete="organization" className={inputCls} value={business} onChange={(e) => setBusiness(e.target.value)} />}</Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Country">{(id) => <Combobox id={id} required strict autoComplete="country-name" placeholder="Start typing, or pick" options={countries.map((c) => c.name)} value={country} onChange={(v) => { setCountry(v); if (v !== country) setCity(""); }} />}</Field>
                  <Field label="City">{(id) => <Combobox id={id} required autoComplete="address-level2" placeholder={country ? "Start typing, or pick" : "Pick a country first"} options={cities} value={city} onChange={setCity} />}</Field>
                </div>
                <Field label="Industry">{(id) => (
                  <select id={id} required className={inputCls} value={industry} onChange={(e) => setIndustry(e.target.value)}>
                    <option value="" disabled>Choose your industry</option>
                    {INDUSTRIES.map(([key, label, about]) => <option key={key} value={key}>{label} — {about}</option>)}
                  </select>
                )}</Field>
                {industry === "other" && (
                  <Field label="Your industry" hint="In a few words, for example “Marine salvage”.">{(id) => <input id={id} required minLength={2} maxLength={100} autoFocus className={inputCls} value={industryOther} onChange={(e) => setIndustryOther(e.target.value)} />}</Field>
                )}
                <Field label="Work email">{(id) => <input id={id} type="email" required autoComplete="email" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
              </>
            )}
            <PasswordField value={password} onChange={setPassword} autoComplete="new-password" hint="At least 10 characters." />
            <PasswordField label="Confirm password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
            {mismatch && <Notice tone="warn">The passwords don’t match.</Notice>}
            <ErrorBox error={start.error} />
            <Button type="submit" disabled={start.isPending || mismatch}>Continue</Button>
          </form>
        )}
        <p className="mt-3 text-sm">Already have an account? <Link className="underline" to="/login">Sign in</Link></p>
      </Card>
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
    onSuccess: () => { qc.clear(); nav("/dashboard", { replace: true }); },
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
  const reset = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/password/reset", { body: { email, code: code.trim(), new_password: password } })),
    onSuccess: () => { setDone(true); window.setTimeout(() => nav("/login", { replace: true }), 2200); },
  });
  const [done, setDone] = useState(false);
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

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import qrcode from "qrcode-generator";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "../components/ui";
import { setToken } from "../lib/auth";
import { useMe } from "../components/Layout";

function Qr({ value }: { value: string }) {
  const svg = useMemo(() => {
    const q = qrcode(0, "M");
    q.addData(value);
    q.make();
    return q.createDataURL(4, 8);
  }, [value]);
  return <img src={svg} alt="QR code for your authenticator app" width={176} height={176} />;
}

function RecoveryCodes({ codes }: { codes: string[] }) {
  return (
    <Notice tone="warn">
      <p className="font-semibold">Save these recovery codes now. Each works once, and they will not be shown again.</p>
      <ul className="mt-2 grid grid-cols-2 gap-1 font-mono text-sm">{codes.map((c) => <li key={c}>{c}</li>)}</ul>
    </Notice>
  );
}

function Mfa() {
  const me = useMe();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const setup = useMutation({ mutationFn: () => unwrap(api.POST("/v1/auth/mfa/setup")) });
  const done = () => { setCode(""); qc.invalidateQueries({ queryKey: ["me"] }); };
  const enable = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/mfa/enable", { body: { code: code.trim() } })),
    onSuccess: (r) => { setCodes(r.recovery_codes); setup.reset(); done(); },
  });
  const disable = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/mfa/disable", { body: { code: code.trim() } })),
    onSuccess: () => { setCodes(null); done(); },
  });
  const regen = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/mfa/recovery-codes", { body: { code: code.trim() } })),
    onSuccess: (r) => { setCodes(r.recovery_codes); done(); },
  });
  const on = me.data?.mfa_enabled;
  const codeField = (
    <Field label="Authenticator code">{(id) => <input id={id} required inputMode="numeric" autoComplete="one-time-code" className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} />}</Field>
  );
  return (
    <Card title="Two-step verification">
      {params.get("setup") && !on && <Notice tone="warn">Operator accounts must turn this on before the admin console opens.</Notice>}
      {codes && <RecoveryCodes codes={codes} />}
      {on ? (
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <p>Two-step verification is <strong>on</strong>. Enter a current code to change it.</p>
          {codeField}
          <ErrorBox error={disable.error ?? regen.error} />
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="secondary" onClick={() => regen.mutate()} disabled={regen.isPending}>New recovery codes</Button>
            {!me.data?.is_operator && <Button type="button" variant="danger" onClick={() => disable.mutate()} disabled={disable.isPending}>Turn off</Button>}
          </div>
        </form>
      ) : setup.data ? (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); enable.mutate(); }}>
          <p>Scan this with an authenticator app (1Password, Authy, Google Authenticator), then enter the code it shows.</p>
          <Qr value={setup.data.otpauth_uri} />
          <p className="text-sm">Can’t scan? Enter this key: <code className="break-all">{setup.data.secret}</code></p>
          {codeField}
          <ErrorBox error={enable.error} />
          <Button type="submit" disabled={enable.isPending}>Turn on</Button>
        </form>
      ) : (
        <div className="space-y-4">
          <p>Add a second step: a code from an authenticator app each time you sign in. Turning it on signs out your other devices.</p>
          <ErrorBox error={setup.error} />
          <Button onClick={() => setup.mutate()} disabled={setup.isPending}>Set up</Button>
        </div>
      )}
    </Card>
  );
}

function Sessions() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const list = useQuery({ queryKey: ["sessions"], queryFn: () => unwrap(api.GET("/v1/auth/sessions")) });
  const revoke = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/v1/auth/sessions/{session_id}", { params: { path: { session_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
  const all = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/logout-all")),
    onSuccess: () => { setToken(null); qc.clear(); nav("/login"); },
  });
  return (
    <Card title="Where you’re signed in">
      <ErrorBox error={list.error ?? revoke.error ?? all.error} />
      <ul className="divide-y divide-slate-200">
        {list.data?.map((s) => (
          <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-sm">
            <span>
              {s.user_agent?.slice(0, 60) ?? "Unknown device"}{s.current && <strong> (this device)</strong>}
              <br /><span className="text-slate-600">Last used {new Date(s.last_used_at).toLocaleString()}</span>
            </span>
            {!s.current && <Button variant="secondary" onClick={() => revoke.mutate(s.id)}>Sign out</Button>}
          </li>
        ))}
      </ul>
      <div className="pt-3"><Button variant="danger" onClick={() => all.mutate()} disabled={all.isPending}>Sign out everywhere</Button></div>
    </Card>
  );
}

export function Security() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Security</h1>
      <Mfa />
      <Sessions />
    </div>
  );
}

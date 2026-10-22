import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "../components/ui";
import { setToken } from "../lib/auth";

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/password/change", { body: { current_password: current, new_password: next } })),
    onSuccess: () => { setCurrent(""); setNext(""); },
  });
  return (
    <Card title="Change password">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); change.mutate(); }}>
        <Field label="Current password">{(id) => <input id={id} type="password" required autoComplete="current-password" className={inputCls} value={current} onChange={(e) => setCurrent(e.target.value)} />}</Field>
        <Field label="New password" hint="At least 10 characters. Changing it signs out your other devices.">{(id) => <input id={id} type="password" required autoComplete="new-password" className={inputCls} value={next} onChange={(e) => setNext(e.target.value)} />}</Field>
        <ErrorBox error={change.error} />
        {change.isSuccess && <Notice tone="ok">Password changed. Your other devices were signed out.</Notice>}
        <Button type="submit" disabled={change.isPending}>Change password</Button>
      </form>
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
      <ChangePassword />
      <Sessions />
    </div>
  );
}

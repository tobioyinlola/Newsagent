import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, Notice, inputCls } from "../components/ui";
import { useMe } from "../components/Layout";
import { signOut } from "../lib/auth";
import { downloadAuthed } from "../lib/download";

export function Account() {
  const me = useMe();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const name = me.data?.workspace_name ?? "";
  const del = useMutation({
    mutationFn: () => unwrap(api.DELETE("/v1/account", { body: { confirm } })),
    onSuccess: () => { signOut(); qc.clear(); nav("/login"); },
  });
  return (
    <>
      <h1 className="text-2xl font-bold">Your data</h1>
      <Card title="Download your data">
        <p className="mb-3 text-sm text-muted">Everything we hold about your workspace as a JSON file: your videos' scripts, founder interview details, credit history and links to your finished files.</p>
        <Button variant="secondary" onClick={() => downloadAuthed("/v1/account/export", "my-data.json").catch((e) => setErr(e.message))}>Download my data</Button>
        {err && <div className="mt-2"><ErrorBox error={new Error(err)} /></div>}
      </Card>
      <Card title="Delete your workspace">
        <Notice tone="warn">This permanently deletes every video, recording, brand file and account in <strong>{name}</strong>. We keep only billing records, as the law requires. It can't be undone.</Notice>
        <form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); del.mutate(); }}>
          <Field label={`Type "DELETE ${name}" to confirm`}>{(id) => <input id={id} className={inputCls} value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />}</Field>
          <ErrorBox error={del.error} />
          <Button type="submit" variant="danger" disabled={del.isPending || confirm !== `DELETE ${name}`}>Delete everything</Button>
        </form>
      </Card>
    </>
  );
}

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls } from "../components/ui";

export function Redeem() {
  const [params] = useSearchParams();
  const [code, setCode] = useState(params.get("code") ?? "");
  const nav = useNavigate();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/redeem", { body: { code } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["me"] }); nav("/brand"); },
  });
  return (
    <div className="mx-auto max-w-md space-y-4 p-6">
      <Card title="Redeem your invite">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label="Invite code">{(id) => <input id={id} required className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} />}</Field>
          <ErrorBox error={m.error} />
          <Button type="submit" disabled={m.isPending}>Create my workspace</Button>
        </form>
      </Card>
    </div>
  );
}

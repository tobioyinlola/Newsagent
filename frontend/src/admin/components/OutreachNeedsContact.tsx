import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { distributionApi } from "../../lib/distribution";
import { getToken } from "../lib/auth";
import { Button, Card, ErrorBox, Notice, inputCls } from "./ui";

type Item = { placement_id: string; request_id: string; outlet_id: string; outlet_name: string; headline: string; requester: string; paid_at: string | null; state: string };
type Todo = { needs_contact: Item[]; waiting_mailbox: number };

const request = <T,>(path: string, method = "GET", body?: unknown) => distributionApi<T>(path, getToken(), method, body);
/** One or several emails, separated by commas, semicolons, spaces or new lines. The first is the main contact; the rest are copied. */
export const splitEmails = (text: string) => [...new Set(text.toLowerCase().split(/[\s,;]+/).filter(Boolean))];

function Row({ item, canManage, onSaved }: { item: Item; canManage: boolean; onSaved: (state: string) => void }) {
  const [name, setName] = useState("");
  const [emails, setEmails] = useState("");
  const list = splitEmails(emails);
  const save = useMutation({
    mutationFn: () => request<{ state: string }>(`admin/outreach/needs-contact/${item.placement_id}`, "PUT", { contact_name: name.trim(), emails: list }),
    onSuccess: (r) => onSaved(r.state),
  });
  return (
    <li className="rounded-lg border border-line p-3">
      <p className="font-semibold">{item.outlet_name}</p>
      <p className="text-xs text-muted">For “{item.headline || "a paid request"}” · {item.requester}{item.paid_at ? ` · paid ${new Date(item.paid_at).toLocaleDateString()}` : ""}</p>
      {canManage && (
        <form className="mt-2 grid gap-3 sm:grid-cols-[12rem_minmax(0,1fr)_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); if (list.length) save.mutate(); }}>
          <label className="block text-sm font-semibold">Contact name (optional)<input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada" /></label>
          <label className="block text-sm font-semibold">Email (one or several)<input className={inputCls} value={emails} onChange={(e) => setEmails(e.target.value)} placeholder="ada@outlet.com, news@outlet.com" /></label>
          <Button type="submit" disabled={!list.length || save.isPending}>{save.isPending ? "Saving…" : "Save and email them"}</Button>
        </form>
      )}
      {list.length > 1 && <p className="mt-1 text-xs text-muted">{list[0]} is the main contact; the other {list.length - 1} {list.length === 2 ? "is" : "are"} copied on every email.</p>}
      <ErrorBox error={save.error} />
    </li>
  );
}

// Paid requests where an outlet has no contact yet. Adding one saves it on the outlet (so every later request uses it) and starts the email.
export function OutreachNeedsContact({ canManage, onGoMailbox }: { canManage: boolean; onGoMailbox: () => void }) {
  const qc = useQueryClient();
  const todo = useQuery({ queryKey: ["outreach-needs-contact"], queryFn: () => request<Todo>("admin/outreach/needs-contact"), refetchInterval: 30000 });
  const [message, setMessage] = useState("");
  const items = todo.data?.needs_contact ?? [];
  const waiting = todo.data?.waiting_mailbox ?? 0;
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["outreach-needs-contact"] }); void qc.invalidateQueries({ queryKey: ["outreach-config"] }); void qc.invalidateQueries({ queryKey: ["outreach-threads"] }); };
  return (
    <div className="space-y-3" aria-live="polite">
      {waiting > 0 && <Notice tone="warn">{waiting} {waiting === 1 ? "outlet has" : "outlets have"} a contact but {waiting === 1 ? "is" : "are"} waiting for Gmail to be connected. <button type="button" className="font-semibold underline" onClick={onGoMailbox}>Connect Gmail</button></Notice>}
      {message && <Notice tone="ok">{message}</Notice>}
      {items.length > 0 && (
        <Card title={`Waiting for a contact (${items.length})`}>
          <p className="mb-3 text-sm text-muted">These outlets are on paid requests, but nobody has been written to because they have no contact email yet. Add one or several. It is saved on the outlet for next time, and the email goes out straight away.</p>
          <ul className="space-y-3">
            {items.map((i) => <Row key={i.placement_id} item={i} canManage={canManage} onSaved={(state) => { setMessage(state === "started" ? `Saved. We have started emailing ${i.outlet_name}.` : `Saved for ${i.outlet_name}. It will be emailed as soon as Gmail is connected.`); refresh(); }} />)}
          </ul>
        </Card>
      )}
      <ErrorBox error={todo.error} />
    </div>
  );
}

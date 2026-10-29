import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Schemas, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, Field, inputCls, Notice } from "../components/ui";
import { ago } from "../lib/format";

type Team = Schemas["TeamOut"];
type Member = Schemas["StaffOut"];

const STATUS: Record<string, string> = { owner: "bg-brand-purple text-white", active: "bg-lime-tint", invited: "bg-peach-tint", suspended: "bg-brand-red" };
const CUSTOM = "custom";

// Which permissions a role gives, and (for a custom role) tick-boxes for the rest. A box the signed-in person doesn't hold
// themselves is disabled: nobody can hand out more than they have (the server enforces it too).
function PermissionPicker({ team, role, value, onChange }: { team: Team; role: string; value: string[]; onChange: (v: string[]) => void }) {
  const preset = team.roles.find((r) => r.key === role);
  const shown = role === CUSTOM ? value : preset?.permissions ?? [];
  const mine = new Set(team.your_permissions);
  const groups = [...new Set(team.permissions.map((p) => p.group))];
  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-medium text-ink">{role === CUSTOM ? "Choose what they can do" : "What this role can do"}</legend>
      {groups.map((g) => (
        <div key={g}>
          <p className="font-mono text-[11px] font-bold uppercase tracking-widest text-muted">{g}</p>
          <ul className="mt-1 grid gap-1 sm:grid-cols-2">
            {team.permissions.filter((p) => p.group === g).map((p) => {
              const on = shown.includes(p.key);
              const locked = role !== CUSTOM || !mine.has(p.key);
              return (
                <li key={p.key}>
                  <label className={`flex items-start gap-2 text-sm ${locked && role === CUSTOM ? "text-muted" : ""}`} title={role === CUSTOM && !mine.has(p.key) ? "You can't give a permission you don't have yourself" : undefined}>
                    <input type="checkbox" className="mt-1" checked={on} disabled={locked} onChange={(e) => onChange(e.target.checked ? [...value, p.key] : value.filter((x) => x !== p.key))} />
                    <span>{p.label}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </fieldset>
  );
}

function RolePicker({ team, role, onChange }: { team: Team; role: string; onChange: (r: string) => void }) {
  const desc = role === CUSTOM ? "Pick exactly the permissions you want." : team.roles.find((r) => r.key === role)?.description;
  return (
    <div className="space-y-1">
      <Field label="Role">{(id) => (
        <select id={id} className={inputCls} value={role} onChange={(e) => onChange(e.target.value)}>
          {team.roles.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          <option value={CUSTOM}>Custom…</option>
        </select>
      )}</Field>
      {desc && <p className="text-xs text-muted">{desc}</p>}
    </div>
  );
}

function InviteForm({ team, onDone }: { team: Team; onDone: (m: Schemas["StaffInviteOut"], email: string) => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("support");
  const [perms, setPerms] = useState<string[]>([]);
  const invite = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/staff", { body: { email, name, role, permissions: role === CUSTOM ? perms : [] } })),
    onSuccess: (m) => { onDone(m, email); setEmail(""); setName(""); setPerms([]); },
  });
  return (
    <Card title="Invite a team member">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Email">{(id) => <input id={id} type="email" required autoComplete="off" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
          <Field label="Name (optional)">{(id) => <input id={id} autoComplete="off" className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        </div>
        <RolePicker team={team} role={role} onChange={setRole} />
        <PermissionPicker team={team} role={role} value={perms} onChange={setPerms} />
        <ErrorBox error={invite.error} />
        <Button type="submit" disabled={invite.isPending || (role === CUSTOM && perms.length === 0)}>Send invitation</Button>
      </form>
    </Card>
  );
}

function EditPanel({ team, member, onClose }: { team: Team; member: Member; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(member.name);
  const [role, setRole] = useState(member.role);
  const [perms, setPerms] = useState<string[]>(member.permissions);
  const save = useMutation({
    mutationFn: () => unwrap(api.PATCH("/v1/admin/staff/{staff_id}", { params: { path: { staff_id: member.id } }, body: { name, role, permissions: role === CUSTOM ? perms : undefined } })),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["team"] }); onClose(); },
  });
  return (
    <Card title={`Change access for ${member.name || member.email}`}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label="Name">{(id) => <input id={id} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        <RolePicker team={team} role={role} onChange={setRole} />
        <PermissionPicker team={team} role={role} value={perms} onChange={setPerms} />
        <p className="text-xs text-muted">Changes apply straight away, even if they're signed in.</p>
        <ErrorBox error={save.error} />
        <div className="flex gap-3">
          <Button type="submit" disabled={save.isPending || (role === CUSTOM && perms.length === 0)}>Save</Button>
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

export function TeamPage() {
  const qc = useQueryClient();
  const team = useQuery({ queryKey: ["team"], queryFn: () => unwrap(api.GET("/v1/admin/staff")) });
  const [editing, setEditing] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const [note, setNote] = useState<{ tone: "ok" | "warn"; text: string } | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["team"] });
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => { void refresh(); },
  });
  const t = team.data;
  const sent = (m: Schemas["StaffInviteOut"], email: string) => {
    void refresh();
    setNote(m.emailed
      ? { tone: "ok", text: `We emailed an invitation to ${email}. The link works once.` }
      : { tone: "warn", text: `We couldn't email ${email}, so send them this link yourself (it works once): ${m.join_url}` });
  };
  const editingMember = t?.members.find((m) => m.id === editing);

  return (
    <>
      <h1 className="text-2xl font-bold">Team</h1>
      <p className="text-sm text-muted">People who can use this back office, and exactly what each of them can do. Owners always have full access.</p>
      <ErrorBox error={team.error ?? act.error} />
      {note && <Notice tone={note.tone}>{note.text}</Notice>}
      {t && <InviteForm team={t} onDone={sent} />}
      {t && editingMember && <EditPanel team={t} member={editingMember} onClose={() => setEditing(null)} />}
      <Card title="Members">
        {team.isLoading ? <p aria-busy="true">Loading…</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm"><caption className="sr-only">Back-office team</caption>
              <thead><tr className="text-left text-muted"><th className="py-1">Person</th><th>Role</th><th>Status</th><th>Last sign-in</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{t?.members.map((m) => (
                <tr key={m.id} className="border-t border-line align-top">
                  <td className="py-2"><div className="font-bold">{m.name || m.email}{m.is_you && <span className="ml-2 font-normal text-muted">(you)</span>}</div>{m.name && <div className="text-muted">{m.email}</div>}</td>
                  <td>{m.role_label}{m.role === CUSTOM && <div className="text-xs text-muted">{m.permissions.length} permissions</div>}</td>
                  <td><span className={`rounded-sm px-1.5 py-0.5 text-xs font-bold ${STATUS[m.status] ?? ""}`}>{m.status}</span>{m.status === "invited" && m.invite_expires_at && <div className="text-xs text-muted">link valid until {new Date(m.invite_expires_at).toLocaleDateString()}</div>}</td>
                  <td>{m.status === "invited" ? "Not yet" : ago(m.last_login_at)}</td>
                  <td>
                    {m.editable ? (
                      <span className="flex flex-wrap justify-end gap-2">
                        <Button variant="secondary" onClick={() => { setEditing(m.id); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Change access</Button>
                        {m.status === "invited" && <Button variant="secondary" onClick={() => act.mutate(async () => { const r = await unwrap(api.POST("/v1/admin/staff/{staff_id}/resend", { params: { path: { staff_id: m.id } } })); sent(r, m.email); })}>Resend</Button>}
                        {m.status === "active" && <Button variant="secondary" onClick={() => act.mutate(() => unwrap(api.PATCH("/v1/admin/staff/{staff_id}", { params: { path: { staff_id: m.id } }, body: { status: "suspended" } })))}>Suspend</Button>}
                        {m.status === "suspended" && <Button variant="secondary" onClick={() => act.mutate(() => unwrap(api.PATCH("/v1/admin/staff/{staff_id}", { params: { path: { staff_id: m.id } }, body: { status: "active" } })))}>Restore</Button>}
                        <Button variant="danger" onClick={() => setRemoving(m)}>{m.status === "invited" ? "Cancel invite" : "Remove"}</Button>
                      </span>
                    ) : <span className="block text-right text-xs text-muted" title={m.is_you ? "You can't change your own access" : m.status === "owner" ? "Owners are set by the system" : "They have access you don't"}>{m.status === "owner" ? "Set by the system" : m.is_you ? "You" : "Beyond your access"}</span>}
                  </td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </Card>
      {removing && (
        <ConfirmDialog
          title={removing.status === "invited" ? "Cancel this invitation?" : `Remove ${removing.name || removing.email}?`}
          confirmLabel={removing.status === "invited" ? "Cancel invitation" : "Remove"}
          cancelLabel="Keep"
          onCancel={() => setRemoving(null)}
          onConfirm={() => { const m = removing; setRemoving(null); act.mutate(() => unwrap(api.DELETE("/v1/admin/staff/{staff_id}", { params: { path: { staff_id: m.id } } }))); }}
        >
          {removing.status === "invited" ? "The link in their email will stop working." : "They're signed out everywhere straight away and can't sign in again unless you invite them back."}
        </ConfirmDialog>
      )}
    </>
  );
}

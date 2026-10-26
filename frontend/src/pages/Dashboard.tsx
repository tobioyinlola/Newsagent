import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Schemas, unwrap } from "../api/client";
import { Card, ErrorBox } from "../components/ui";
import { useMe } from "../components/Layout";
import { nextAction } from "../lib/states";

type Project = Schemas["ProjectOut"];

const DONE = "final_ready";
const NEEDS_ATTENTION = ["failed", "limit_reached"];
const linkBtn = "inline-block rounded-sm border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green";

function Stat({ label, value, hint, tone = "" }: { label: string; value: string | number; hint?: string; tone?: string }) {
  return (
    <div className={`rounded-md border-2 border-ink p-4 ${tone || "bg-white"}`}>
      <p className="text-sm font-medium text-muted">{label}</p>
      <p className="font-mono text-3xl font-bold text-ink">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

const when = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });

export function Dashboard() {
  const me = useMe();
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/v1/projects")), refetchInterval: 20000 });
  // a missing brand kit is an expected answer here, not an error
  const brand = useQuery({ queryKey: ["brand-kit"], queryFn: async () => { try { return await unwrap(api.GET("/v1/brand-kit")); } catch { return null; } }, retry: false });

  const all: Project[] = projects.data ?? [];
  const finished = all.filter((p) => p.state === DONE);
  const attention = all.filter((p) => NEEDS_ATTENTION.includes(p.state));
  const open = all.filter((p) => p.state !== DONE && p.state !== "cancelled" && !NEEDS_ATTENTION.includes(p.state));
  const todo = [...attention, ...open];
  const balance = me.data ? Number(me.data.credit_balance) : null;
  const first = (me.data?.workspace_name ?? "").trim();
  const brandDone = !!(brand.data && (brand.data.logo_light_key || brand.data.logo_dark_key || brand.data.source_url));
  const lowCredits = balance !== null && balance < 5;

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{first ? `Welcome back, ${first}` : "Welcome back"}</h1>
          <p className="text-sm text-muted">Everything about your videos in one place.</p>
        </div>
        <Link to="/projects/new" className={linkBtn}>New video</Link>
      </div>

      <ErrorBox error={projects.error} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Videos ready" value={finished.length} hint={finished.length ? "Download or share them" : "Your first one is minutes away"} tone="bg-lime-tint" />
        <Stat label="In progress" value={open.length} />
        <Stat label="Need attention" value={attention.length} tone={attention.length ? "bg-peach-tint" : "bg-white"} />
        <Stat label="Credits" value={balance === null ? "…" : balance.toFixed(0)} hint={lowCredits ? "Running low" : undefined} tone={lowCredits ? "bg-peach-tint" : "bg-white"} />
      </div>

      {lowCredits && (
        <div role="note" className="flex flex-wrap items-center justify-between gap-2 rounded-sm border-2 border-brand-peach bg-peach-tint p-3 text-sm text-ink">
          <span>You have {balance?.toFixed(0)} credits left. Top up so your next video doesn't pause.</span>
          <Link to="/billing" className="font-bold underline">Get credits</Link>
        </div>
      )}

      <Card title="Pick up where you left off">
        {projects.isLoading ? <p aria-busy="true">Loading…</p> : todo.length ? (
          <ul className="divide-y divide-line">
            {todo.map((p) => {
              const a = nextAction(p.state);
              return (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="truncate font-bold">{p.title || `Video ${p.id.slice(0, 6)}`}</p>
                    <p className="text-sm text-muted">{a.status} · started {when(p.created_at)}</p>
                  </div>
                  <Link to={`/projects/${p.id}`} className={a.urgent ? linkBtn : "inline-block rounded-sm border-2 border-ink bg-white px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-white"}>{a.cta}</Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="space-y-3">
            <p className="text-muted">Nothing waiting on you. Paste your next announcement and we'll write the script, interview you and make the video.</p>
            <Link to="/projects/new" className={linkBtn}>Start a video</Link>
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card title="Your videos" actions={all.length > 0 ? <Link to="/projects" className="text-sm font-bold underline">See all</Link> : undefined}>
          {finished.length ? (
            <ul className="grid gap-3 sm:grid-cols-2">
              {finished.slice(0, 4).map((p) => (
                <li key={p.id}>
                  <Link to={`/projects/${p.id}`} className="block rounded-md border-2 border-ink p-3 hover:bg-paper">
                    <span className="block font-mono text-xs font-bold uppercase text-muted">Ready · {when(p.completed_at ?? p.created_at)}</span>
                    <span className="block truncate font-bold">{p.title || `Video ${p.id.slice(0, 6)}`}</span>
                    <span className="text-sm underline">Watch and download</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : <p className="text-muted">Finished videos appear here with their download and share links.</p>}
        </Card>

        <Card title="Get set up">
          <ul className="space-y-3 text-sm">
            <Step done={brandDone} to="/brand" title="Add your brand" text="Your logo and colours on every video. Paste your website and we fill it in." />
            <Step done={all.length > 0} to="/projects/new" title="Make your first video" text="Paste your news. AI writes the script and the interview questions." />
            <Step done={finished.length > 0} to="/projects" title="Share a finished video" text="Every finished video gets a download and a share link." />
          </ul>
        </Card>
      </div>
    </>
  );
}

function Step({ done, to, title, text }: { done: boolean; to: string; title: string; text: string }) {
  return (
    <li className="flex gap-3">
      <span aria-hidden className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border-2 border-ink text-xs font-bold ${done ? "bg-brand-green" : "bg-white"}`}>{done ? "✓" : ""}</span>
      <span>
        <Link to={to} className="font-bold underline">{title}</Link>
        <span className="sr-only">{done ? " (done)" : " (to do)"}</span>
        <span className="block text-muted">{text}</span>
      </span>
    </li>
  );
}

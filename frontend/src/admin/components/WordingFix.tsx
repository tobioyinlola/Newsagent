import { useMutation } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, unwrap } from "../api/client";
import { Button, ErrorBox, inputCls } from "./ui";

type Report = { found: Record<string, number>; total: number; kept: Record<string, number>; applied: boolean; rerendering: boolean; version: number | null; note: string };

const WHERE: Record<string, string> = {
  story: "Written story: title, summary, press release, About and social post",
  presenter_lines: "The presenter's spoken lines",
  ticker: "Ticker lines",
  lower_thirds: "Lower thirds",
  name_card_role: "Name card role",
  interview_questions: "Interview questions already asked (kept as they are)",
};

// A pop-up in the middle of the page. The browser's own dialog is used, so Escape closes it and focus stays inside it.
// (The page's base styles remove a dialog's automatic margins, so it is centred explicitly with m-auto.)
function Modal({ open, onClose, title, subtitle, children, footer, size = "lg", id }: { open: boolean; onClose: () => void; title: string; subtitle?: string; children: ReactNode; footer: ReactNode; size?: "md" | "lg"; id: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  // Drawn straight into the page body: inside a table cell it would inherit the cell's "no wrapping" and right-aligned text.
  return createPortal(
    <dialog
      ref={ref}
      aria-labelledby={`${id}-title`}
      onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }} // a click on the dimmed area outside closes it
      className={`m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] ${size === "md" ? "max-w-md" : "max-w-xl"} overflow-hidden whitespace-normal rounded-2xl border border-line bg-white p-0 text-left text-ink shadow-2xl backdrop:bg-ink/60 backdrop:backdrop-blur-sm`}
    >
      <div className="flex max-h-[calc(100dvh-2rem)] flex-col">
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
          <div>
            <h2 id={`${id}-title`} className="text-lg font-bold leading-snug sm:text-xl">{title}</h2>
            {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="-mr-2 -mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xl text-muted hover:bg-paper hover:text-ink focus-visible:outline-3 focus-visible:outline-brand-purple">×</button>
        </header>
        <div className="space-y-4 overflow-y-auto px-5 py-5 sm:px-6">{children}</div>
        <footer className="flex flex-col-reverse gap-2 border-t border-line bg-paper px-5 py-4 sm:flex-row sm:justify-end sm:px-6 [&>button]:w-full sm:[&>button]:w-auto">{footer}</footer>
      </div>
    </dialog>,
    document.body,
  );
}

// Correct a name or phrase across a finished video: check first (nothing changes), change the words, and optionally make the video again.
export function WordingFix({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [confirmAgain, setConfirmAgain] = useState(false);
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const run = useMutation({
    mutationFn: (mode: { apply: boolean; rerender: boolean }) =>
      unwrap(api.POST("/v1/admin/projects/{project_id}/wording", { params: { path: { project_id: projectId } }, body: { find: find.trim(), replace: replace.trim(), ...mode } })) as Promise<Report>,
    onSuccess: (r, mode) => { setReport(r); setConfirmAgain(false); if (mode.apply) onDone(); },
  });
  const ready = find.trim().length > 0 && replace.trim().length > 0 && find.trim() !== replace.trim();
  const close = () => { if (run.isPending) return; setOpen(false); setConfirmAgain(false); setReport(null); run.reset(); };
  const check = () => { if (ready && !run.isPending) run.mutate({ apply: false, rerender: false }); };
  const found = report && !report.applied && report.total > 0;
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>Fix wording</Button>

      <Modal
        id={`${id}-main`}
        open={open}
        onClose={close}
        title="Correct a name in this video"
        subtitle="Replace a name or phrase in the story, the presenter's lines, the ticker and the lower thirds."
        footer={report?.applied ? (
          <Button type="button" onClick={close}>Done</Button>
        ) : (
          <>
            <Button type="button" variant="secondary" onClick={close} disabled={run.isPending}>Cancel</Button>
            {found ? (
              <>
                <Button type="button" variant="secondary" disabled={run.isPending} onClick={() => run.mutate({ apply: true, rerender: false })}>Change the words only</Button>
                <Button type="button" disabled={run.isPending} onClick={() => setConfirmAgain(true)}>Change and make the video again</Button>
              </>
            ) : (
              <Button type="button" disabled={!ready || run.isPending} onClick={check}>{run.isPending ? "Checking…" : "Check"}</Button>
            )}
          </>
        )}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm font-semibold">Find
            <input className={`${inputCls} mt-1`} value={find} disabled={!!report?.applied} onChange={(e) => { setFind(e.target.value); setReport(null); }} placeholder="WIRE Africa" autoComplete="off" onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); check(); } }} />
          </label>
          <label className="block text-sm font-semibold">Replace with
            <input className={`${inputCls} mt-1`} value={replace} disabled={!!report?.applied} onChange={(e) => { setReplace(e.target.value); setReport(null); }} placeholder="Womenovate" autoComplete="off" onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); check(); } }} />
          </label>
        </div>
        <p className="text-sm text-muted">Capitals and lower case are matched too. The founder&apos;s own recorded answers are never changed.</p>
        <ErrorBox error={run.error} />
        {report && (
          <div role="status" className={`rounded-xl border p-4 text-sm ${report.applied ? "border-ink bg-lime-tint" : report.total === 0 ? "border-line bg-paper" : "border-brand-purple bg-lilac"}`}>
            {report.total === 0 ? (
              <p className="font-semibold">That wording was not found, so there is nothing to change.</p>
            ) : (
              <>
                <p className="font-bold">{report.applied ? `Changed in ${report.total} place${report.total === 1 ? "" : "s"}` : `Found in ${report.total} place${report.total === 1 ? "" : "s"}`}</p>
                <ul className="mt-2 divide-y divide-ink/10">
                  {Object.entries(report.found).map(([k, n]) => (
                    <li key={k} className="flex items-baseline justify-between gap-4 py-1.5"><span>{WHERE[k] ?? k}</span><span className="font-mono font-bold tabular-nums">{n}</span></li>
                  ))}
                </ul>
              </>
            )}
            {Object.entries(report.kept).map(([k, n]) => <p key={k} className="mt-2 text-muted">{WHERE[k] ?? k}: {n}</p>)}
            <p className="mt-2 text-muted">{report.note}</p>
            {report.applied && (
              <p className="mt-3 font-semibold">
                {report.rerendering ? "The video is being made again. It will be ready in a few minutes, and the current one stays live until then." : "The new words are saved. The video file still shows the old wording until it is made again."}
              </p>
            )}
          </div>
        )}
      </Modal>

      <Modal
        id={`${id}-confirm`}
        open={confirmAgain}
        onClose={() => { if (!run.isPending) setConfirmAgain(false); }}
        size="md"
        title="Make this video again?"
        footer={
          <>
            <Button type="button" variant="secondary" disabled={run.isPending} onClick={() => setConfirmAgain(false)}>Go back</Button>
            <Button type="button" disabled={run.isPending} onClick={() => run.mutate({ apply: true, rerender: true })}>{run.isPending ? "Starting…" : "Yes, make it again"}</Button>
          </>
        }
      >
        <p className="text-sm">You are about to replace <strong>“{find.trim()}”</strong> with <strong>“{replace.trim()}”</strong> and make the video again.</p>
        <ul className="list-disc space-y-1.5 pl-5 text-sm">
          <li>Presenter parts whose words changed are made again and use <strong>presenter-video credits</strong>.</li>
          <li>The current video stays live until the new one is ready, usually a few minutes.</li>
          <li>The founder&apos;s own recorded answers are not changed.</li>
        </ul>
        <ErrorBox error={confirmAgain ? run.error : null} />
      </Modal>
    </>
  );
}

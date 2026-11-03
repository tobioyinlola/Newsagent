import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, ErrorBox, inputCls } from "./ui";

type Report = { found: Record<string, number>; total: number; kept: Record<string, number>; applied: boolean; rerendering: boolean; version: number | null; note: string };

const WHERE: Record<string, string> = {
  story: "Written story (title, summary, press release, About, social post)",
  presenter_lines: "The presenter's spoken lines",
  ticker: "Ticker lines",
  lower_thirds: "Lower thirds",
  name_card_role: "Name card role",
  interview_questions: "Interview questions already asked (kept as they are)",
};

// Correct a name or phrase across a finished video. Check first (nothing changes), then change the words, and optionally make the video again.
export function WordingFix({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const run = useMutation({
    mutationFn: (mode: { apply: boolean; rerender: boolean }) =>
      unwrap(api.POST("/v1/admin/projects/{project_id}/wording", { params: { path: { project_id: projectId } }, body: { find: find.trim(), replace: replace.trim(), ...mode } })) as Promise<Report>,
    onSuccess: (r, mode) => { setReport(r); if (mode.apply) onDone(); },
  });
  const ready = find.trim().length > 0 && replace.trim().length > 0 && find.trim() !== replace.trim();
  const close = () => { dialog.current?.close(); setReport(null); run.reset(); };
  return (
    <>
      <Button variant="secondary" onClick={() => dialog.current?.showModal()}>Fix wording</Button>
      <dialog ref={dialog} aria-labelledby={`wf-${projectId}`} className="w-[calc(100%-2rem)] max-w-xl rounded-md border-2 border-ink bg-white p-0 text-left text-ink backdrop:bg-ink/60">
        <form method="dialog" className="space-y-4 p-6" onSubmit={(e) => e.preventDefault()}>
          <h2 id={`wf-${projectId}`} className="text-xl font-bold">Correct a name in this video</h2>
          <p className="text-sm text-muted">Replaces the wording in the written story, the presenter&apos;s lines, the ticker and the lower thirds. The founder&apos;s own recorded answers are never changed.</p>
          <label className="block text-sm font-semibold">Find<input className={inputCls} value={find} onChange={(e) => { setFind(e.target.value); setReport(null); }} placeholder="WIRE Africa" /></label>
          <label className="block text-sm font-semibold">Replace with<input className={inputCls} value={replace} onChange={(e) => { setReplace(e.target.value); setReport(null); }} placeholder="Womenovate" /></label>
          <ErrorBox error={run.error} />
          {report && (
            <div role="status" className="rounded-sm border border-line bg-paper p-3 text-sm">
              {report.total === 0 ? <p>That wording was not found, so there is nothing to change.</p> : <>
                <p className="font-semibold">{report.applied ? "Changed" : "Found"} {report.total} time{report.total === 1 ? "" : "s"}:</p>
                <ul className="mt-1 list-disc pl-5">{Object.entries(report.found).map(([k, n]) => <li key={k}>{WHERE[k] ?? k}: {n}</li>)}</ul>
              </>}
              {Object.entries(report.kept).map(([k, n]) => <p key={k} className="mt-1 text-muted">{WHERE[k] ?? k}: {n}</p>)}
              <p className="mt-1 text-muted">{report.note}</p>
              {report.applied && <p className="mt-2 font-semibold">{report.rerendering ? "The video is being made again. It will be ready in a few minutes." : "The words are saved. The video file still shows the old wording until it is made again."}</p>}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {!report?.applied && <Button type="button" disabled={!ready || run.isPending} onClick={() => run.mutate({ apply: false, rerender: false })}>Check</Button>}
            {report && !report.applied && report.total > 0 && <>
              <Button type="button" variant="secondary" disabled={run.isPending} onClick={() => run.mutate({ apply: true, rerender: false })}>Change the words only</Button>
              <Button type="button" disabled={run.isPending} onClick={() => { if (confirm("Change the words and make the video again? Presenter clips whose words changed are made again and use presenter-video credits. The current video stays until the new one is ready.")) run.mutate({ apply: true, rerender: true }); }}>Change and make the video again</Button>
            </>}
            <Button type="button" variant="secondary" onClick={close}>{report?.applied ? "Close" : "Cancel"}</Button>
          </div>
        </form>
      </dialog>
    </>
  );
}

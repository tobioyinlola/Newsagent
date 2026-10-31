import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

export function DistributionReadyPrompt({ projectId, workspaceId }: { projectId: string; workspaceId: string }) {
  const key = `cf.distribution-ready.${workspaceId}.${projectId}`;
  const [dismissed, setDismissed] = useState(() => { try { return localStorage.getItem(key) === "seen"; } catch { return false; } });
  const dialog = useRef<HTMLDialogElement>(null);
  const navigate = useNavigate();
  const close = () => { setDismissed(true); try { localStorage.setItem(key, "seen"); } catch { /* dismissal lasts for this visit */ } };
  useEffect(() => {
    const element = dialog.current;
    if (!dismissed && element && !element.open) element.showModal();
    return () => { if (element?.open) element.close(); };
  }, [dismissed]);
  if (dismissed) return null;
  return <dialog ref={dialog} role="alertdialog" aria-labelledby="distribution-ready-title" aria-describedby="distribution-ready-description" onCancel={event => { event.preventDefault(); close(); }} className="m-auto w-[calc(100%_-_2rem)] max-w-lg rounded-2xl border border-line bg-white p-0 text-ink shadow-2xl backdrop:bg-ink/60">
    <div className="border-b border-line bg-lime-tint px-6 py-5 sm:px-8"><div className="flex items-center gap-3"><span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-full border border-ink bg-brand-green text-xl">✓</span><div><p className="text-xs font-bold uppercase tracking-wider text-muted">Ready for a wider audience</p><p className="mt-1 font-bold">Your video is ready.</p></div></div></div>
    <div className="p-6 sm:p-8"><h2 id="distribution-ready-title" className="text-2xl font-bold leading-snug">Take your story to over 25,000 media outlets?</h2><p id="distribution-ready-description" className="mt-4 text-sm leading-relaxed text-muted">Choose your publications, pair your video with an announcement and see each outlet’s credit cost before submitting.</p><p className="mt-3 text-xs leading-relaxed text-muted">Available outlets and coverage are shown in the selection. No credits are charged by opening distribution.</p><div className="mt-6 flex flex-col gap-3 sm:flex-row-reverse"><button type="button" className="min-h-12 rounded-lg border border-ink bg-brand-green px-5 py-3 text-sm font-bold" onClick={() => { close(); navigate(`/distribution/request?project=${encodeURIComponent(projectId)}`); }}>Yes, choose outlets</button><button type="button" autoFocus className="min-h-12 rounded-lg border border-line px-5 py-3 text-sm font-bold hover:bg-paper" onClick={close}>Maybe later</button></div><p className="mt-4 text-xs text-muted">You can also return to distribution from your dashboard.</p></div>
  </dialog>;
}

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getToken } from "../lib/auth";
import { distributionApi } from "../lib/distribution";
import { savePick } from "../lib/distributionFilters";
import { credits, featuredPlan, outletSummary, planBody, planIds, planRef, trackPlan, type PlanResult } from "../lib/outletPlanner";

// Shown twice per video, each dismissed on its own: once while the video is being made ("making"), and again when it is finished ("ready").
export function DistributionReadyPrompt({ projectId, workspaceId, stage = "ready" }: { projectId: string; workspaceId: string; stage?: "making" | "ready" }) {
  const making = stage === "making";
  const key = `cf.distribution-${making ? "making" : "ready"}.${workspaceId}.${projectId}`;
  const [dismissed, setDismissed] = useState(() => { try { return localStorage.getItem(key) === "seen"; } catch { return false; } });
  const dialog = useRef<HTMLDialogElement>(null);
  const navigate = useNavigate();
  const [rec, setRec] = useState<PlanResult | null>(null); // a plan made for this business, when we know enough to make one
  useEffect(() => {
    if (making || dismissed) return;
    let live = true;
    distributionApi<PlanResult>("distribution/plan", getToken(), "POST", planBody({ budget: "", countries: [], goal: "credibility", source: "ready_prompt", auto: true })).then((r) => { if (live) setRec(r); }).catch(() => undefined); // no plan is not an error: the prompt simply stays as it was
    return () => { live = false; };
  }, [making, dismissed]);
  const featured = rec ? featuredPlan(rec) : null;
  const close = () => { setDismissed(true); try { localStorage.setItem(key, "seen"); } catch { /* dismissal lasts for this visit */ } };
  useEffect(() => {
    const element = dialog.current;
    if (!dismissed && element && !element.open) element.showModal();
    return () => { if (element?.open) element.close(); };
  }, [dismissed]);
  if (dismissed) return null;
  return <dialog ref={dialog} role="alertdialog" aria-labelledby="distribution-ready-title" aria-describedby="distribution-ready-description" onCancel={event => { event.preventDefault(); close(); }} className="m-auto w-[calc(100%_-_2rem)] max-w-lg rounded-2xl border border-line bg-white p-0 text-ink shadow-2xl backdrop:bg-ink/60">
    <div className="border-b border-line bg-lime-tint px-6 py-5 sm:px-8"><div className="flex items-center gap-3"><span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-full border border-ink bg-brand-green text-xl">✓</span><div><p className="text-xs font-bold uppercase tracking-wider text-muted">Ready for a wider audience</p><p className="mt-1 font-bold">{making ? "Your video is being made." : "Your video is ready."}</p></div></div></div>
    <div className="p-6 sm:p-8"><h2 id="distribution-ready-title" className="text-2xl font-bold leading-snug">Take your story to over 2,500 media outlets?</h2><p id="distribution-ready-description" className="mt-4 text-sm leading-relaxed text-muted">{making ? "While we make your video, you can start your distribution. " : ""}Choose your publications, pair your video with an announcement and see each outlet’s credit cost before submitting.</p><p className="mt-3 text-xs leading-relaxed text-muted">Available outlets and coverage are shown in the selection. No credits are charged by opening distribution.</p>{featured && <div className="mt-5 rounded-xl border-2 border-ink bg-paper p-4" aria-labelledby="distribution-recommended"><p id="distribution-recommended" className="text-xs font-bold uppercase tracking-wider text-muted">Recommended for you</p><p className="mt-1 font-bold">{featured.plan.name} plan: {featured.plan.outlets.length} {featured.plan.outlets.length === 1 ? "outlet" : "outlets"} for {credits(featured.plan.total_credits)}</p><p className="mt-1 text-sm text-muted">{outletSummary(featured.plan)}.</p><p className={`mt-1 text-sm font-bold ${featured.fits ? "" : "text-red-800"}`}>{featured.fits ? `You have ${credits(featured.balance)}, so it fits.` : `You have ${credits(featured.balance)}. You need ${credits(featured.missing)} more for this plan.`}</p><button type="button" className="mt-3 min-h-12 w-full rounded-lg border-2 border-ink bg-brand-green px-5 py-3 text-sm font-bold hover:bg-ink hover:text-brand-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple" onClick={() => { savePick(planIds(featured.plan), { key: featured.plan.key, ids: planIds(featured.plan) }); trackPlan("used", "ready_prompt", planRef(featured.plan), getToken()); close(); navigate(`/distribution/request?project=${encodeURIComponent(projectId)}&pick=1`); }}>Start with this plan</button><p className="mt-2 text-xs text-muted">Nothing is charged yet. You can change any outlet before you submit.</p></div>}<div className="mt-6 flex flex-col gap-3 sm:flex-row-reverse"><button type="button" className={`min-h-12 rounded-lg border px-5 py-3 text-sm font-bold ${featured ? "border-line bg-white hover:bg-paper" : "border-ink bg-brand-green"}`} onClick={() => { close(); navigate(making ? "/distribution/request" : `/distribution/request?project=${encodeURIComponent(projectId)}`); }}>Yes, choose outlets</button><button type="button" autoFocus className="min-h-12 rounded-lg border border-line px-5 py-3 text-sm font-bold hover:bg-paper" onClick={close}>{making ? "Not now" : "Maybe later"}</button></div><p className="mt-4 text-xs text-muted">You can also return to distribution from your dashboard.</p></div>
  </dialog>;
}

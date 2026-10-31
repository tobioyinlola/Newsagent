import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

const credits = (value: number) => `${value.toLocaleString(undefined, { maximumFractionDigits: 4 })} ${value === 1 ? "credit" : "credits"}`;
export function DistributionFundingDialog({ balance, required, billingUrl, onClose }: { balance: number; required: number; billingUrl: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.showModal();
    return () => { document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return <dialog ref={dialog} aria-labelledby="distribution-funding-title" aria-describedby="distribution-funding-help" onCancel={e => { e.preventDefault(); onClose(); }} className="m-auto w-[calc(100%_-_2rem)] max-w-md rounded-2xl border border-line bg-white p-0 text-ink shadow-2xl backdrop:bg-ink/60"><div className="p-6 sm:p-8"><p className="text-xs font-bold uppercase tracking-widest text-muted">One more step</p><h2 id="distribution-funding-title" className="mt-3 text-2xl font-bold">Not enough credits</h2><p id="distribution-funding-help" className="mt-3 text-sm leading-relaxed text-muted">Top up your wallet to pay for these outlets. Your distribution draft is saved, so you can return and finish.</p><dl className="my-5 space-y-3 rounded-xl border border-line bg-paper p-4 text-sm"><div className="flex justify-between gap-3"><dt>Required</dt><dd className="font-semibold">{credits(required)}</dd></div><div className="flex justify-between gap-3"><dt>Your balance</dt><dd className="font-semibold">{credits(balance)}</dd></div><div className="flex justify-between gap-3 border-t border-line pt-3"><dt>Credits to add</dt><dd className="font-bold">{credits(Math.max(0, required - balance))}</dd></div></dl><p className="text-xs text-muted">No credits have been deducted.</p><div className="mt-6 flex flex-wrap gap-3"><Link to={billingUrl} className="inline-flex min-h-12 flex-1 items-center justify-center rounded-lg border-2 border-ink bg-brand-green px-4 py-3 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green">Buy credits</Link><button autoFocus type="button" onClick={onClose} className="min-h-12 rounded-lg border-2 border-line px-4 py-3 text-sm font-bold">Keep editing</button></div></div></dialog>;
}

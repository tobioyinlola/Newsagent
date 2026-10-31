import { Link } from "react-router-dom";

export function DistributionReturnLink() {
  let target: string | null = null;
  try { target = sessionStorage.getItem("distribution-return"); } catch { /* billing remains available */ }
  if (!target?.startsWith("/distribution/request?")) return null;
  return <div className="rounded-xl border border-ink bg-lime-tint p-5"><p className="text-sm">Your distribution draft is waiting. Return to review your selection and submit it with your updated balance.</p><Link className="mt-3 inline-flex min-h-11 items-center rounded-lg border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold" to={target}>Return to your distribution request</Link></div>;
}

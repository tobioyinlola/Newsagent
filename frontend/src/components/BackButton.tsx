import { useLocation, useNavigate } from "react-router-dom";

/** Use this app's history when available; direct/email links return to a useful parent. */
export function BackButton({ fallback = "/dashboard", className = "" }: { fallback?: string; className?: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  const hasPrevious = typeof window.history.state?.idx === "number" && window.history.state.idx > 0;
  if (!hasPrevious && location.pathname === fallback) return null;
  return <button type="button" className={`inline-flex min-h-11 items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors hover:bg-brand-green hover:text-ink ${className}`} onClick={() => { if (hasPrevious) navigate(-1); else navigate(fallback); }} aria-label="Go back">
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m10 5-7 7 7 7M3 12h18" /></svg>Back
  </button>;
}

export function workspaceBackFallback(path: string) {
  if (path.startsWith("/billing/")) return "/settings/billing";
  if (path.startsWith("/ai-newsroom/") && path !== "/ai-newsroom/videos") return "/ai-newsroom/videos";
  if (path.startsWith("/settings/") && path !== "/settings/profile") return "/settings/profile";
  return path === "/dashboard" ? "/" : "/dashboard";
}
